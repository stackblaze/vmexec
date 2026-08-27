"""
cbt_transport.py — CBT incremental backup orchestration (Phases 1–4).
"""

import datetime
import os
import shutil
import tempfile

import backup_manifest as bm
import cbt_core
import delta_store
import vsphere_context
from logger_util import log_info, log_warn, log_error


def cbt_supported_storage(storage):
    base = storage.get_base_path() if storage else ""
    return not str(base).startswith("s3://")


def plan_backup_dest(vm_name, use_cbt):
    if use_cbt:
        point_id = bm.new_point_id()
        return bm.point_rel(vm_name, point_id), point_id
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    return f"{vm_name}/{date_str}", None


def export_cbt_backup(
    si,
    vm_name,
    storage,
    config,
    vm_record,
    host_ip,
    host_user,
    host_password,
    progress_callback=None,
    speed_callback=None,
    is_cancelled_func=None,
    connection_type=vsphere_context.CONN_AUTO,
    create_snapshot_func=None,
    remove_snapshot_func=None,
    download_http_func=None,
    download_http_range_func=None,
    action_callback=None,
):
    """
    Run a CBT-aware backup (full or incremental) into the chain layout.
    Returns (ok, message, dest_rel_dir).
    """
    from backup_engine import _find_snapshot_by_name, _get_vm

    if not cbt_supported_storage(storage):
        return False, "CBT requires local or NFS backup storage", None

    ok, msg = cbt_core.enable_cbt(si, vm_name)
    if not ok:
        log_warn(f"[CBT] {msg}; continuing without CBT enable")

    chain = bm.load_chain(storage, vm_name) or bm.create_empty_chain(vm_name)
    take_full, reason = cbt_core.should_take_full_backup(config, vm_record, chain, storage)
    backup_type = "full" if take_full else "incremental"
    log_info(f"[CBT] Backup type={backup_type} ({reason})")
    if action_callback:
        action_callback(f"CBT {backup_type} backup...")

    dest_rel_dir, point_id = plan_backup_dest(vm_name, use_cbt=True)
    parent_id = None if take_full else (chain.get("latest") if chain.get("points") else None)
    if backup_type == "incremental" and not parent_id:
        backup_type = "full"
        take_full = True
        log_info("[CBT] No parent for incremental; forcing full")

    vm = _get_vm(si, vm_name)
    if not vm:
        return False, f"VM {vm_name} not found", None

    disks = cbt_core.collect_cbt_disks(vm)
    if not disks:
        return False, f"No disks found for {vm_name}", None

    is_off = getattr(vm.runtime, "powerState", "poweredOff") == "poweredOff"

    if not take_full and not is_off:
        import vddk_transport
        if not vddk_transport.is_available(config) and vsphere_context.count_vm_snapshots(vm) > 0:
            log_info(
                "[CBT] VM carries pre-existing snapshots and VDDK is unavailable; "
                "the HTTP incremental path would read stale data — forcing full "
                "(streams via NFC)"
            )
            take_full = True
            backup_type = "full"
            parent_id = None

    snap_obj = None
    snap_name = None

    try:
        if progress_callback:
            progress_callback(2)

        if not is_off:
            if not create_snapshot_func:
                return False, "Snapshot function required for live CBT backup", None
            snap_obj, snap_name = create_snapshot_func(si, vm_name)
            if not snap_obj:
                return False, f"Snapshot failed: {snap_name}", None
            if snap_name and not getattr(snap_obj, "_moId", None):
                vm_ref = _get_vm(si, vm_name)
                resolved = _find_snapshot_by_name(vm_ref, snap_name)
                if resolved:
                    snap_obj = resolved

        storage.makedirs(dest_rel_dir)
        disk_keys = [d["device_key"] for d in disks]
        change_ids = cbt_core.get_snapshot_change_ids(snap_obj, disk_keys) if snap_obj else {}

        if backup_type == "incremental" and snap_obj:
            prev_manifest = bm.load_manifest(storage, vm_name, parent_id)
            if not prev_manifest:
                backup_type = "full"
                take_full = True
                parent_id = None

        disk_manifest_entries = []
        total_disks = len(disks)
        progress_bands = _disk_progress_bands(disks)

        for idx, disk in enumerate(disks):
            if is_cancelled_func and is_cancelled_func():
                return False, "Backup cancelled by user", None

            disk_basename = os.path.basename(disk["rel_path"])
            flat_basename = disk_basename.replace(".vmdk", "-flat.vmdk")
            desc_rel = f"{dest_rel_dir}/{disk_basename}"
            flat_rel = f"{dest_rel_dir}/{flat_basename}"
            step_base, step_end = progress_bands[idx]

            if download_http_func:
                download_http_func(
                    si, disk["ds_name"], disk["rel_path"], storage, desc_rel,
                    progress_callback=progress_callback,
                    progress_base=step_base,
                    progress_total=2,
                    speed_callback=speed_callback,
                    is_cancelled_func=is_cancelled_func,
                    vm=vm,
                    connection_type=connection_type,
                )

            device_key = disk["device_key"]
            capacity = disk["capacity_bytes"]
            change_id = change_ids.get(device_key)

            if take_full or is_off:
                log_info(f"[CBT] Full disk {idx + 1}/{total_disks}: {flat_basename}")
                if is_off:
                    flat_ds_path = disk["rel_path"].replace(".vmdk", "-flat.vmdk")
                    download_http_func(
                        si, disk["ds_name"], flat_ds_path, storage, flat_rel,
                        progress_callback=progress_callback,
                        progress_base=step_base + 2,
                        progress_total=max(step_end - step_base - 2, 1),
                        speed_callback=speed_callback,
                        is_cancelled_func=is_cancelled_func,
                        vm=vm,
                        connection_type=connection_type,
                    )
                else:
                    import vddk_transport

                    def _stream_full_nfc():
                        import nfc_transport
                        nfc_transport.stream_snapshot_disk_nfc(
                            si, snap_obj, disk, storage, flat_rel,
                            disk_index=idx,
                            progress_callback=progress_callback,
                            progress_base=step_base + 2,
                            progress_total=max(step_end - step_base - 2, 1),
                            speed_callback=speed_callback,
                            is_cancelled_func=is_cancelled_func,
                            connection_type=connection_type,
                        )

                    nfc_ok = vsphere_context.supports_nfc_export(si, connection_type)
                    if not vddk_transport.is_available(config) and nfc_ok:
                        # VDDK not installed: NFC is the normal transport,
                        # not a degraded fallback — dispatch directly, no
                        # warning per disk.
                        log_info(
                            f"[CBT] VDDK not installed; streaming full disk "
                            f"via NFC ExportSnapshot"
                        )
                        _stream_full_nfc()
                    else:
                        try:
                            vddk_transport.stream_snapshot_disk(
                                si, vm, snap_obj, disk,
                                host_ip, host_user, host_password,
                                storage, flat_rel, config=config,
                                connection_type=connection_type,
                                is_cancelled_func=is_cancelled_func,
                                progress_callback=progress_callback,
                                progress_base=step_base + 2,
                                progress_total=max(step_end - step_base - 2, 1),
                                speed_callback=speed_callback,
                            )
                        except Exception as nbd_err:
                            # A user cancel surfaces as an exception from the
                            # progress callback — propagate it, don't retry
                            # the cancelled work over NFC.
                            if is_cancelled_func and is_cancelled_func():
                                raise
                            if nfc_ok:
                                # An installed VDDK failing at runtime is a
                                # real fault worth surfacing before we degrade.
                                log_warn(
                                    f"[CBT] NBD full disk failed ({str(nbd_err)[:200]}); "
                                    "trying NFC ExportSnapshot"
                                )
                                _stream_full_nfc()
                            else:
                                raise
                disk_manifest_entries.append(bm.build_disk_entry(
                    device_key, disk_basename, flat_basename, capacity,
                    change_id, "full",
                ))
                comp_level = 0
                if config:
                    from compression_util import effective_level, compress_storage_file
                    comp_level = effective_level(config)
                    if comp_level > 0:
                        flat_rel = compress_storage_file(storage, flat_rel, comp_level)
                        if flat_rel.endswith(".gz"):
                            disk_manifest_entries[-1]["flat_basename"] = flat_basename + ".gz"
                            disk_manifest_entries[-1]["storage_flat"] = flat_rel.split("/")[-1]
            else:
                prev_disk = _find_prev_disk_entry(storage, vm_name, parent_id, device_key)
                prev_change_id = prev_disk.get("change_id") if prev_disk else "*"
                areas = cbt_core.query_changed_areas(
                    vm, snap_obj, device_key, prev_change_id, capacity,
                )
                log_info(
                    f"[CBT] Incremental disk {idx + 1}/{total_disks}: "
                    f"{len(areas)} changed area(s), {flat_basename}"
                )
                delta_name = f"{flat_basename}.delta.nvbd"
                delta_rel = f"{dest_rel_dir}/{delta_name}"
                extents = _capture_changed_extents(
                    si, vm, snap_obj, disk, areas, is_off,
                    host_ip, host_user, host_password, storage, config,
                    connection_type, download_http_range_func,
                    is_cancelled_func,
                    progress_callback=progress_callback,
                    progress_base=step_base + 2,
                    progress_total=max(step_end - step_base - 2, 1),
                )
                _write_delta_storage(storage, delta_rel, extents, config)
                disk_manifest_entries.append(bm.build_disk_entry(
                    device_key, disk_basename, flat_basename, capacity,
                    change_id, "incremental", delta_file=delta_name,
                ))
                if progress_callback:
                    progress_callback(step_end)

        if progress_callback:
            progress_callback(93)

        if remove_snapshot_func and snap_name:
            remove_snapshot_func(si, vm_name, snap_name, timeout_mins=60)
            snap_name = None

        vmx_file = None
        from backup_engine import _collect_vm_disk_layout
        _, _, vmx_ds, vmx_rel = _collect_vm_disk_layout(vm)
        if vmx_ds and vmx_rel and download_http_func:
            vmx_file = os.path.basename(vmx_rel)
            try:
                download_http_func(
                    si, vmx_ds, vmx_rel, storage, f"{dest_rel_dir}/{vmx_file}",
                    is_cancelled_func=is_cancelled_func, vm=vm,
                    connection_type=connection_type,
                )
            except Exception as e:
                log_warn(f"[CBT] VMX download warning: {e}")
                vmx_file = None

        manifest = bm.build_manifest(
            point_id, backup_type, parent_id, disk_manifest_entries, vmx_file=vmx_file,
        )
        bm.save_manifest(storage, vm_name, point_id, manifest)

        import datetime as dt
        chain = bm.add_point_to_chain(chain, {
            "id": point_id,
            "type": backup_type,
            "parent": parent_id,
            "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        })
        bm.save_chain(storage, vm_name, chain)

        if progress_callback:
            progress_callback(100)

        return True, f"CBT {backup_type} backup completed: {dest_rel_dir}", dest_rel_dir

    except Exception as e:
        if remove_snapshot_func and snap_name:
            try:
                remove_snapshot_func(si, vm_name, snap_name, timeout_mins=30)
            except Exception:
                pass
        log_error(f"[CBT] Backup failed: {e}")
        return False, str(e), None


def _find_prev_disk_entry(storage, vm_name, parent_id, device_key):
    man = bm.load_manifest(storage, vm_name, parent_id)
    if not man:
        return None
    return next((d for d in man["disks"] if d["device_key"] == device_key), None)


def _write_delta_storage(storage, delta_rel, extents, config=None):
    from compression_util import effective_level
    level = effective_level(config) if config else 0
    local = _resolve_local(storage, delta_rel)
    if local:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        delta_store.write_delta_file(local, extents, compression_level=level)
        return
    import io
    buf = io.BytesIO()
    delta_store.write_delta_file(buf, extents, compression_level=level)
    with storage.open_write(delta_rel) as f:
        f.write(buf.getvalue())


def _resolve_local(storage, rel_path):
    base = storage.get_base_path()
    if base.startswith("s3://"):
        return None
    if hasattr(storage, "base_path"):
        return os.path.join(storage.base_path, rel_path)
    return None


# Upper bound per HTTP range request on the VDDK-free incremental path. CBT can
# report very large contiguous dirty areas (a fresh full has one the size of
# the disk); unbounded requests would buffer the whole area in one response.
HTTP_EXTENT_CHUNK = 64 * 1024 * 1024


def _disk_progress_bands(disks, start=5, span=85):
    """Progress-bar band (base, end) per disk, weighted by capacity.

    Equal per-disk bands make the bar lie on mixed-size VMs: one 100 GB disk
    plus two 5 GB disks would give 91% of the bytes a third of the bar, so it
    crawls through the big disk and sprints through the rest. Weighting by
    capacity keeps the bar proportional to bytes moved. Falls back to equal
    bands if capacities are missing.
    """
    total = sum(int(d.get("capacity_bytes") or 0) for d in disks)
    n = max(len(disks), 1)
    if total <= 0:
        return [
            (start + span * i // n, start + span * (i + 1) // n)
            for i in range(len(disks))
        ]
    bands = []
    cum = 0
    for d in disks:
        base = start + span * cum // total
        cum += int(d.get("capacity_bytes") or 0)
        bands.append((base, start + span * cum // total))
    return bands


def _read_extents_http_frozen_base(
    si, vm, disk, areas, download_http_range_func, connection_type, is_cancelled_func,
    progress_callback=None, progress_base=0, progress_total=1,
):
    """Read changed areas of a LIVE VM without VDDK.

    Valid only while the backup snapshot is the VM's sole snapshot: the base
    disk's -flat file is then frozen (all guest writes go to the snapshot
    delta), so ranged datastore HTTP reads against it return the exact
    point-in-time data the snapshot captured — the same mechanism the
    powered-off path has always used. The caller enforces the guard.
    """
    extents = []
    total_bytes = sum(int(l) for _, l in areas) or 1
    read_bytes = 0
    for start, length in areas:
        offset, remaining = int(start), int(length)
        while remaining > 0:
            if is_cancelled_func and is_cancelled_func():
                raise RuntimeError("Backup cancelled by user")
            chunk = min(remaining, HTTP_EXTENT_CHUNK)
            data = _read_range_http(
                si, disk, offset, chunk, download_http_range_func, vm, connection_type,
            )
            if not data:
                raise RuntimeError(
                    f"Empty HTTP range read at offset {offset} of {disk['rel_path']}"
                )
            extents.append((offset, data))
            offset += len(data)
            remaining -= len(data)
            read_bytes += len(data)
            if progress_callback:
                progress_callback(
                    progress_base + int(progress_total * read_bytes / total_bytes)
                )
    return extents


def _capture_changed_extents(
    si, vm, snap_obj, disk, areas, is_off,
    host_ip, host_user, host_password, storage, config,
    connection_type, download_http_range_func, is_cancelled_func,
    progress_callback=None, progress_base=0, progress_total=1,
):
    """Read changed block ranges and return list of (offset, data) for delta file.

    progress_callback (with progress_base/progress_total) reports byte-level
    progress on the HTTP read paths; the VDDK extent read is a single blocking
    subprocess, so it only reports its band boundaries.
    """
    if is_off:
        extents = []
        total_bytes = sum(int(l) for _, l in areas if int(l) > 0) or 1
        read_bytes = 0
        for start, length in areas:
            if is_cancelled_func and is_cancelled_func():
                raise RuntimeError("Backup cancelled by user")
            if length <= 0:
                continue
            data = _read_range_http(
                si, disk, start, length, download_http_range_func, vm, connection_type,
            )
            extents.append((start, data))
            read_bytes += len(data)
            if progress_callback:
                progress_callback(
                    progress_base + int(progress_total * read_bytes / total_bytes)
                )
        return extents

    import vddk_transport
    if is_cancelled_func and is_cancelled_func():
        raise RuntimeError("Backup cancelled by user")
    filtered = [(int(s), int(l)) for s, l in areas if int(l) > 0]
    single_snapshot = vsphere_context.count_vm_snapshots(vm) == 1
    if vddk_transport.is_available(config):
        try:
            if progress_callback:
                progress_callback(progress_base)
            return vddk_transport.read_snapshot_extents(
                si, vm, snap_obj, disk, filtered,
                host_ip, host_user, host_password, config, connection_type,
            )
        except Exception as vddk_err:
            # A user cancel must propagate, not degrade to another transport.
            if is_cancelled_func and is_cancelled_func():
                raise
            # An installed VDDK can still fail at runtime — a version outside
            # the vSphere support matrix (e.g. VDDK 9.x against vCenter 7),
            # missing transport, thumbprint drift. When the chain is provably
            # safe, degrade to the HTTP path instead of failing the backup.
            if not single_snapshot:
                raise
            log_warn(
                f"[CBT] VDDK extent read failed ({str(vddk_err)[:160]}); "
                "falling back to datastore HTTP range reads (frozen base disk)"
            )
    # VDDK-free path. Safe only when our backup snapshot is the ONLY snapshot:
    # then disk["rel_path"] (collected pre-snapshot) is the base disk and its
    # -flat file is frozen for the snapshot's lifetime.
    if single_snapshot:
        log_info(
            f"[CBT] VDDK unavailable; reading {len(filtered)} changed area(s) "
            f"via datastore HTTP range requests (frozen base disk)"
        )
        return _read_extents_http_frozen_base(
            si, vm, disk, filtered, download_http_range_func,
            connection_type, is_cancelled_func,
            progress_callback=progress_callback,
            progress_base=progress_base,
            progress_total=progress_total,
        )
    raise RuntimeError(
        "Incremental read needs VDDK when the VM has other snapshots: the top "
        "of the disk chain is a delta, so a -flat range read would return "
        "stale data. Remove pre-existing snapshots or install VDDK."
    )


def _read_range_http(si, disk, start, length, download_http_range_func, vm, connection_type):
    if not download_http_range_func:
        from backup_engine import _download_file_http_range
        download_http_range_func = _download_file_http_range
    flat_rel_path = disk["rel_path"].replace(".vmdk", "-flat.vmdk")
    return download_http_range_func(
        si, disk["ds_name"], flat_rel_path, start, length, vm=vm,
        connection_type=connection_type,
    )


def _read_range_nbd(
    si, vm, snap_obj, disk, start, length,
    host_ip, host_user, host_password, config, connection_type,
):
    import vddk_transport
    return vddk_transport.read_snapshot_extent(
        si, vm, snap_obj, disk, start, length,
        host_ip, host_user, host_password, config, connection_type,
    )

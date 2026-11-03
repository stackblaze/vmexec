"""
chain_restore.py — Materialize CBT backup chains for restore.
"""

import json
import os
import shutil

from delta_store import apply_extents_to_file, read_delta_file
from backup_manifest import (
    load_chain,
    load_manifest,
    point_rel,
    walk_chain_to_point,
)
from logger_util import log_info


def is_chain_point(storage, source_rel_dir):
    manifest_path = f"{source_rel_dir.rstrip('/')}/manifest.json"
    return storage.exists(manifest_path)


def resolve_restore_source(storage, source_rel_dir):
    """Materialize chain points; return (rel_dir_for_import, temp_dir_or_none)."""
    if not is_chain_point(storage, source_rel_dir):
        return source_rel_dir, None
    out_rel = materialize_chain_point(storage, source_rel_dir)
    return out_rel, out_rel


def materialize_chain_point(storage, point_rel_dir):
    """Build flat restore folder from full + delta chain. Returns output rel path."""
    manifest_path = f"{point_rel_dir.rstrip('/')}/manifest.json"
    manifest = _load_json(storage, manifest_path)
    if not manifest:
        raise RuntimeError(f"No manifest at {point_rel_dir}")

    vm_name = point_rel_dir.split("/")[0]
    point_id = manifest["point_id"]
    chain = load_chain(storage, vm_name)
    point_path = walk_chain_to_point(chain, point_id) if chain else []

    if not point_path:
        point_path = [{
            "id": point_id,
            "type": manifest["type"],
            "parent": manifest.get("parent_id"),
        }]
    # A restore must start from a full. If a parent was pruned, walking the
    # chain stops early and the disk would be built from zeros plus deltas:
    # a corrupt disk with no error. Refuse instead.
    if point_path[0].get("type") not in ("full", "synthetic_full"):
        raise RuntimeError(
            f"Restore point {point_id} of {vm_name} is unusable: its chain does not "
            f"start at a full backup (missing parent {point_path[0].get('parent')})."
        )

    out_rel = f"{point_rel_dir.rstrip('/')}/_materialized"
    storage.makedirs(out_rel)

    for disk in manifest["disks"]:
        device_key = disk["device_key"]
        flat_name = disk["flat_basename"]
        desc_name = disk["descriptor_basename"]
        capacity = disk["capacity_bytes"]
        out_flat = f"{out_rel}/{flat_name}"

        _materialize_disk(storage, vm_name, point_path, device_key, flat_name, capacity, out_flat)

        for pt in reversed(point_path):
            pt_dir = point_rel(vm_name, pt["id"])
            desc_src = f"{pt_dir}/{desc_name}"
            if storage.exists(desc_src):
                _copy_storage_file(storage, desc_src, f"{out_rel}/{desc_name}")
                break

    vmx_name = manifest.get("vmx_file")
    if vmx_name:
        for pt in reversed(point_path):
            pt_dir = point_rel(vm_name, pt["id"])
            vmx_src = f"{pt_dir}/{vmx_name}"
            if storage.exists(vmx_src):
                _copy_storage_file(storage, vmx_src, f"{out_rel}/{vmx_name}")
                break

    log_info(f"[CBT] Materialized chain point {point_id} → {out_rel}")
    return out_rel


def _materialize_disk(storage, vm_name, point_path, device_key, flat_name, capacity, out_flat):
    base_local = _resolve_local_path(storage, out_flat)
    if not base_local:
        raise RuntimeError("Chain materialize requires local/NFS storage")

    os.makedirs(os.path.dirname(base_local) or ".", exist_ok=True)
    with open(base_local, "wb") as out_f:
        if capacity > 0:
            out_f.seek(capacity - 1)
            out_f.write(b"\x00")

    for pt in point_path:
        pt_dir = point_rel(vm_name, pt["id"])
        man = _load_json(storage, f"{pt_dir}/manifest.json")
        if not man:
            continue
        disk = next((d for d in man["disks"] if d["device_key"] == device_key), None)
        if not disk:
            continue

        if disk["file_type"] in ("full", "synthetic_full"):
            storage_flat = disk.get("storage_flat") or disk["flat_basename"]
            full_src = f"{pt_dir}/{storage_flat}"
            if not storage.exists(full_src) and storage_flat.endswith(".gz"):
                full_src = f"{pt_dir}/{disk['flat_basename']}"
            if storage.exists(full_src):
                _copy_flat_full(storage, full_src, base_local)
        elif disk["file_type"] == "incremental":
            delta_file = disk.get("delta_file") or f"{flat_name}.delta.nvbd"
            delta_src = f"{pt_dir}/{delta_file}"
            if storage.exists(delta_src):
                _apply_delta(storage, delta_src, base_local, capacity)


def _copy_flat_full(storage, src_rel, dest_local):
    from compression_util import gunzip_to_path
    src_local = _resolve_local_path(storage, src_rel)
    if src_rel.endswith(".gz") or (src_local and src_local.endswith(".gz")):
        if src_local and os.path.isfile(src_local):
            gunzip_to_path(src_local, dest_local)
            return
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gz") as tmp:
            tmp_path = tmp.name
        try:
            with storage.open_read(src_rel) as src, open(tmp_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            gunzip_to_path(tmp_path, dest_local)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return
    if src_local and os.path.isfile(src_local):
        shutil.copy2(src_local, dest_local)
        return
    with storage.open_read(src_rel) as src, open(dest_local, "wb") as dst:
        shutil.copyfileobj(src, dst)


def _apply_delta(storage, delta_rel, dest_local, capacity):
    delta_local = _resolve_local_path(storage, delta_rel)
    if delta_local and os.path.isfile(delta_local):
        extents = read_delta_file(delta_local)
    else:
        with storage.open_read(delta_rel) as f:
            extents = read_delta_file(f)
    with open(dest_local, "r+b") as out_f:
        apply_extents_to_file(out_f, extents, capacity)


def _copy_storage_file(storage, src_rel, dst_rel):
    dst_local = _resolve_local_path(storage, dst_rel)
    src_local = _resolve_local_path(storage, src_rel)
    if dst_local and src_local:
        os.makedirs(os.path.dirname(dst_local) or ".", exist_ok=True)
        shutil.copy2(src_local, dst_local)
        return
    with storage.open_read(src_rel) as src, storage.open_write(dst_rel) as dst:
        shutil.copyfileobj(src, dst)


def _resolve_local_path(storage, rel_path):
    base = storage.get_base_path()
    if base.startswith("s3://"):
        return None
    if hasattr(storage, "base_path"):
        return os.path.join(storage.base_path, rel_path)
    if os.path.isabs(rel_path):
        return rel_path
    if os.path.isdir(base.rstrip("/")):
        return os.path.join(base.rstrip("/"), rel_path)
    return None


def _load_json(storage, rel_path):
    if not storage.exists(rel_path):
        return None
    with storage.open_read(rel_path) as f:
        raw = f.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def create_synthetic_full(storage, vm_name, chain):
    """Merge latest chain into a new synthetic full point and trim old points."""
    from backup_manifest import (
        build_disk_entry,
        build_manifest,
        new_point_id,
        point_rel,
        save_chain,
        save_manifest,
    )
    import datetime

    if not chain or not chain.get("latest"):
        return chain

    latest_id = chain["latest"]
    latest_rel = point_rel(vm_name, latest_id)
    latest_manifest = _load_json(storage, f"{latest_rel}/manifest.json")
    if not latest_manifest:
        return chain

    mat_rel = materialize_chain_point(storage, latest_rel)
    new_id = new_point_id()
    new_rel = point_rel(vm_name, new_id)

    # Move the materialized folder into place when the storage is a local
    # path (ZeroFS/NFS): a rename, not a second full copy of every disk.
    mat_local = _resolve_local_path(storage, mat_rel)
    new_local = _resolve_local_path(storage, new_rel)
    if mat_local and new_local and not os.path.exists(new_local):
        os.makedirs(os.path.dirname(new_local), exist_ok=True)
        os.rename(mat_local, new_local)
    else:
        storage.makedirs(new_rel)
        for fn in storage.list_files(mat_rel):
            _copy_storage_file(storage, f"{mat_rel}/{fn}", f"{new_rel}/{fn}")
        storage.delete_dir(mat_rel)

    new_disks = []
    for d in latest_manifest["disks"]:
        new_disks.append(build_disk_entry(
            d["device_key"],
            d["descriptor_basename"],
            d["flat_basename"],
            d["capacity_bytes"],
            d.get("change_id"),
            "synthetic_full",
        ))

    manifest = build_manifest(
        new_id,
        "synthetic_full",
        None,
        new_disks,
        vmx_file=latest_manifest.get("vmx_file"),
        synthetic_from=latest_id,
    )
    save_manifest(storage, vm_name, new_id, manifest)

    # Older points stay: they are restore points the retention policy may
    # still want (it used to delete them all here, so "keep 7" or a weekly
    # / monthly point could never survive past the next synthetic full).
    # Retention prunes them, never this function.
    new_chain = dict(chain)
    new_chain["points"] = list(chain.get("points", [])) + [{
        "id": new_id,
        "type": "synthetic_full",
        "parent": None,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }]
    new_chain["latest"] = new_id
    save_chain(storage, vm_name, new_chain)
    log_info(f"[CBT] Synthetic full created: {new_id} (from {latest_id}); older points kept for retention")
    return new_chain


def with_ancestors(points, keep_ids):
    """keep_ids plus every point they depend on (parent links back to a full)."""
    by_id = {p["id"]: p for p in points}
    closed = set()
    for pid in keep_ids:
        cur = by_id.get(pid)
        while cur and cur["id"] not in closed:
            closed.add(cur["id"])
            parent = cur.get("parent")
            cur = by_id.get(parent) if parent else None
    return closed


def select_points_to_remove(points, retention_count=7, gfs=None, now=None):
    """Points retention may delete.

    gfs = (daily, weekly, monthly) keeps one point per day/week/month;
    otherwise the newest `retention_count` points are kept. Either way every
    point a kept point depends on is kept too, so no restore is ever broken.
    """
    if not points:
        return []
    if gfs:
        from gfs_retention import classify_gfs_keepers
        daily, weekly, monthly = gfs
        keep = classify_gfs_keepers(points, daily=daily, weekly=weekly, monthly=monthly, now=now)
    else:
        n = max(1, int(retention_count or 1))
        keep = {p["id"] for p in points[-n:]}
    keep.add(points[-1]["id"])  # the newest point always stays
    keep = with_ancestors(points, keep)
    return [p for p in points if p["id"] not in keep]


def apply_chain_retention(storage, vm_name, chain, retention_count, full_interval, config=None, gfs=None):
    """Optionally rotate to a synthetic full, then prune old chain points.

    gfs (daily, weekly, monthly) comes from the VM's backup policy; without
    it the config's retention_mode decides (gfs_* keeps, or retention_count).
    """
    from backup_manifest import point_rel, save_chain
    from backup_manifest import count_incrementals_since_full

    if not chain or not chain.get("points"):
        return chain

    if count_incrementals_since_full(chain) >= full_interval:
        chain = create_synthetic_full(storage, vm_name, chain)

    points = chain.get("points", [])
    if gfs is None and config is not None and getattr(config, "retention_mode", "count") == "gfs":
        gfs = (
            getattr(config, "gfs_daily_keep", 7) or 7,
            getattr(config, "gfs_weekly_keep", 4) or 0,
            getattr(config, "gfs_monthly_keep", 6) or 0,
        )
    to_remove = select_points_to_remove(points, retention_count=retention_count, gfs=gfs)

    if not to_remove:
        return chain

    # Index first, folders second: a crash in between leaves unreferenced
    # folders (harmless), never an index pointing at a deleted point.
    remove_ids = {p["id"] for p in to_remove}
    chain["points"] = [p for p in points if p["id"] not in remove_ids]
    if chain["points"]:
        chain["latest"] = chain["points"][-1]["id"]
    save_chain(storage, vm_name, chain)

    for pt in to_remove:
        rel = point_rel(vm_name, pt["id"])
        if storage.exists(rel):
            log_info(f"[CBT] Retention: removing point {pt['id']}")
            storage.delete_dir(rel)
    return chain

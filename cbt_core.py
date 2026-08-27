"""
cbt_core.py — VMware Changed Block Tracking helpers.
"""

from logger_util import log_info, log_warn


def is_cbt_enabled(vm):
    from pyVmomi import vim
    if getattr(vm.config, "changeTrackingEnabled", False):
        return True
    for dev in getattr(vm.config.hardware, "device", []) or []:
        if isinstance(dev, vim.vm.device.VirtualDisk):
            backing = dev.backing
            if getattr(backing, "changeTrackingEnabled", False):
                return True
    return False


def enable_cbt(si, vm_name):
    """Enable VM-level CBT. Returns (ok, message)."""
    from pyVmomi import vim
    from backup_engine import _get_vm

    vm = _get_vm(si, vm_name)
    if not vm:
        return False, "VM not found"
    if is_cbt_enabled(vm):
        return True, "CBT already enabled"

    spec = vim.vm.ConfigSpec()
    spec.changeTrackingEnabled = True
    log_info(f"[CBT] Enabling change tracking on {vm_name}...")
    try:
        task = vm.ReconfigVM_Task(spec)
        _wait_task(task, timeout_secs=300)
        return True, "CBT enabled"
    except Exception as e:
        return False, f"Failed to enable CBT: {e}"


def _wait_task(task, timeout_secs=600):
    import time
    from pyVmomi import vim

    start = time.time()
    while task.info.state not in (vim.TaskInfo.State.success, vim.TaskInfo.State.error):
        if time.time() - start > timeout_secs:
            raise TimeoutError(f"Task timeout after {timeout_secs}s")
        time.sleep(1)
    if task.info.state == vim.TaskInfo.State.error:
        raise RuntimeError(str(task.info.error))


def disk_excluded(rel_path, patterns):
    """True when a disk's datastore-relative path matches an exclusion prefix.

    patterns: comma-separated path prefixes (e.g. "fcd/"). The default
    excludes vSphere CNS/First-Class Disks — Kubernetes CSI volumes that
    attach/detach as pods move, so a per-VM image backup of them is an
    inconsistent stale copy of data owned by another system.
    """
    for pat in (patterns or "").split(","):
        pat = pat.strip()
        if pat and rel_path.startswith(pat):
            return True
    return False


def collect_cbt_disks(vm, config=None):
    """Return disk descriptors enriched with device_key and capacity_bytes.

    Disks matching config.exclude_disk_patterns are skipped (logged once).
    """
    from pyVmomi import vim
    from backup_engine import _parse_datastore_path
    from logger_util import log_info

    patterns = getattr(config, "exclude_disk_patterns", None) if config else None
    disks = []
    seen = set()
    for dev in getattr(vm.config.hardware, "device", []) or []:
        if not isinstance(dev, vim.vm.device.VirtualDisk):
            continue
        backing = dev.backing
        fn = getattr(backing, "fileName", None) if backing else None
        if not fn:
            continue
        ds_name, rel_path = _parse_datastore_path(fn)
        if not ds_name or fn in seen:
            continue
        seen.add(fn)
        if disk_excluded(rel_path, patterns):
            log_info(f"[CBT] Skipping excluded disk {fn} (exclude_disk_patterns)")
            continue
        cap_kb = getattr(dev, "capacityInKB", None) or getattr(backing, "capacityInKB", 0)
        disks.append({
            "device_key": dev.key,
            "ds_name": ds_name,
            "ds_path": fn,
            "rel_path": rel_path,
            "capacity_bytes": int(cap_kb) * 1024,
        })
    return disks


def get_snapshot_change_ids(snap_obj, disk_keys):
    """
    Read changeId for each disk device key from snapshot config.
    Returns dict device_key -> change_id string.
    """
    from pyVmomi import vim
    result = {}
    if not snap_obj or not getattr(snap_obj, "config", None):
        return result
    devices = getattr(snap_obj.config.hardware, "device", []) or []
    for dev in devices:
        if not isinstance(dev, vim.vm.device.VirtualDisk):
            continue
        if dev.key not in disk_keys:
            continue
        backing = dev.backing
        cid = getattr(backing, "changeId", None) if backing else None
        if cid:
            result[dev.key] = cid
    return result


def query_changed_areas(vm, snap_obj, device_key, previous_change_id, capacity_bytes):
    """
    Query all changed disk areas since previous_change_id.
    previous_change_id use '*' for all blocks (first incremental after full).
    Returns list of (start, length) tuples.

    Uses VirtualMachine.QueryChangedDiskAreas (not VirtualDiskManager).
    """
    areas = []
    start_offset = 0
    change_id = previous_change_id or "*"

    while start_offset < capacity_bytes:
        try:
            info = vm.QueryChangedDiskAreas(
                snapshot=snap_obj,
                deviceKey=int(device_key),
                startOffset=int(start_offset),
                changeId=str(change_id),
            )
        except Exception as e:
            if e.__class__.__name__ == "InvalidArgument":
                break
            raise

        changed = getattr(info, "changedArea", None) or []
        if not changed:
            break
        for area in changed:
            start = int(area.start)
            length = int(area.length)
            if length > 0:
                areas.append((start, length))

        info_length = int(getattr(info, "length", 0) or 0)
        if info_length <= 0:
            break
        info_start = int(getattr(info, "startOffset", start_offset) or start_offset)
        next_offset = info_start + info_length
        if next_offset <= start_offset:
            break
        start_offset = next_offset

    return areas


def should_take_full_backup(config, vm, chain, storage):
    """Decide whether the next backup should be a full (not incremental)."""
    from backup_manifest import count_incrementals_since_full
    if not getattr(config, "cbt_enabled", True):
        return True, "CBT disabled in config"
    if getattr(vm, "cbt_enabled", None) is False:
        return True, "CBT disabled for VM"
    if storage and getattr(storage, "get_base_path", lambda: "")().startswith("s3://"):
        return True, "S3 storage requires full backups (no delta chain)"
    if not chain or not chain.get("points"):
        return True, "No existing chain"
    latest = chain["points"][-1]
    if latest.get("type") not in ("full", "synthetic_full", "incremental"):
        return True, "Unknown prior backup type"
    interval = getattr(config, "cbt_full_interval", 7) or 7
    if count_incrementals_since_full(chain) >= interval:
        return True, f"Full interval reached ({interval} incrementals)"
    return False, "Incremental backup"

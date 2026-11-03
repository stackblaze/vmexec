"""
One status for the Backup page's strip and banner (GET /api/v1/status).

- last 24 h results, next scheduled run, protected count
- backup storage health: /mnt/backups must be its own mount (ZeroFS over
  9P on the appliance, never the root disk) and a probe file must write,
  fsync (= durable in S3 on ZeroFS), read back and delete in time
- the ZeroFS cache disk, mounted read-only into the container
- problems: what the red banner shows, most serious first
"""
import datetime
import os
import socket
import threading
import time

from models import VM, BackupLog, ESXiHost

REPO = os.environ.get("VMEXEC_BACKUP_MOUNT", "/mnt/backups")
CACHE_DIR = os.environ.get("VMEXEC_ZEROFS_CACHE_MOUNT", "/host/zerofs-cache")
PROBE_TIMEOUT_S = 20
PROBE_CACHE_S = 30
VCENTER_CACHE_S = 60

_probe_lock = threading.Lock()
_probe_cache = {"at": 0.0, "result": None}
_vc_cache = {}


def mount_of(path, mounts_file="/proc/mounts"):
    """(mount point, fstype) of the mount holding path; ('/', ...) if none."""
    best = ("/", "")
    try:
        with open(mounts_file) as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mnt, fstype = parts[1].replace("\\040", " "), parts[2]
                p = os.path.abspath(path)
                if (p == mnt or p.startswith(mnt.rstrip("/") + "/")) and len(mnt) >= len(best[0]):
                    best = (mnt, fstype)
    except OSError:
        pass
    return best


def repo_mount_problem(path=REPO, mounts_file="/proc/mounts"):
    """Why backups must not be written to path, or None.

    The repository must be its own mount: otherwise a missing ZeroFS mount
    means backups silently fill the appliance's own disk.
    """
    mnt, fstype = mount_of(path, mounts_file)
    if os.path.abspath(path) != mnt:
        return f"{path} is not mounted (ZeroFS is not running or not mounted); refusing to write backups to the local disk"
    if fstype in ("overlay", "tmpfs"):
        return f"{path} is a {fstype} mount, not the backup storage"
    return None


def _run_probe(path):
    d = os.path.join(path, ".vmexec-health")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"probe-{os.getpid()}-{threading.get_ident()}")
    data = os.urandom(4096)
    t0 = time.monotonic()
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    with open(f, "rb") as fh:
        ok = fh.read() == data
    os.remove(f)
    if not ok:
        raise IOError("probe file read back different data")
    return int((time.monotonic() - t0) * 1000)


def storage_health(path=REPO, now=None):
    """{'healthy', 'fstype', 'probe_ms', 'error'}; cached PROBE_CACHE_S."""
    now = now or time.monotonic()
    cached = _probe_cache["result"]
    if cached and now - _probe_cache["at"] < PROBE_CACHE_S:
        return cached
    problem = repo_mount_problem(path)
    mnt, fstype = mount_of(path)
    result = {"healthy": False, "fstype": fstype or None, "probe_ms": None, "error": problem}
    if not problem:
        if not _probe_lock.acquire(blocking=False):
            return cached or {**result, "error": "health check already running"}
        try:
            box = {}

            def work():
                try:
                    box["ms"] = _run_probe(path)
                except Exception as e:  # noqa: BLE001 - reported to the UI
                    box["err"] = str(e)

            t = threading.Thread(target=work, daemon=True)
            t.start()
            t.join(PROBE_TIMEOUT_S)
            if t.is_alive():
                result["error"] = f"write check did not finish in {PROBE_TIMEOUT_S} s (S3 or ZeroFS stalled)"
            elif "err" in box:
                result["error"] = f"write check failed: {box['err']}"
            else:
                result.update(healthy=True, probe_ms=box["ms"])
        finally:
            _probe_lock.release()
    _probe_cache.update(at=now, result=result)
    return result


def cache_disk(path=CACHE_DIR):
    try:
        if mount_of(path)[0] != os.path.abspath(path):
            return None
        st = os.statvfs(path)
    except OSError:
        return None
    gb = 1024 ** 3
    total = st.f_blocks * st.f_frsize
    used = total - st.f_bavail * st.f_frsize
    # ZeroFS evicts at its own limit (config [cache] disk_size_gb), usually
    # below the disk's size: measure against that when install.sh set it.
    try:
        limit = float(os.environ.get("VMEXEC_ZEROFS_CACHE_LIMIT_GB") or 0) * gb
    except ValueError:
        limit = 0
    size = min(limit, total) if limit > 0 else total
    return {"total_gb": round(size / gb, 1), "used_gb": round(used / gb, 1),
            "used_pct": round(min(100.0, 100 * used / size), 1) if size else 0.0}


def _vcenter_reachable(host, port=443, timeout=3):
    now = time.monotonic()
    hit = _vc_cache.get(host)
    if hit and now - hit[0] < VCENTER_CACHE_S:
        return hit[1]
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
    except OSError:
        ok = False
    _vc_cache[host] = (now, ok)
    return ok


def next_run(vms, now=None):
    """(datetime, [vm names]) of the next scheduled start, or (None, [])."""
    now = now or datetime.datetime.now()
    best, names = None, []
    for vm in vms:
        if not (vm.is_selected and vm.is_job_active):
            continue
        days = {int(d) for d in (vm.schedule_days or "0,1,2,3,4,5,6").split(",") if d.strip().isdigit()}
        freq = vm.schedule_frequency or "daily"
        for add in range(0, 40):
            day = (now + datetime.timedelta(days=add)).date()
            at = datetime.datetime.combine(day, datetime.time(vm.schedule_hour or 0, vm.schedule_minute or 0))
            if at <= now:
                continue
            if freq == "weekly" and day.weekday() not in days:
                continue
            if freq == "monthly" and (day.day > 7 or day.weekday() not in days):
                continue
            break
        else:
            continue
        if best is None or at < best:
            best, names = at, [vm.vm_name]
        elif at == best:
            names.append(vm.vm_name)
    return best, names


def get_status(db, scheduler_paused=False, vddk_installed=True, probe=True):
    vms = db.query(VM).all()
    protected = [v for v in vms if v.is_selected]
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    logs = db.query(BackupLog).filter(BackupLog.timestamp >= since).order_by(BackupLog.timestamp.desc()).all()
    succeeded = sum(1 for log in logs if log.status == "Success")
    failed_logs = [log for log in logs if log.status == "Failed"]

    storage = storage_health() if probe else {"healthy": None, "fstype": None, "probe_ms": None, "error": None}
    storage["location"] = os.environ.get("VMEXEC_REPO_LOCATION") or None
    storage["encrypted"] = os.environ.get("VMEXEC_REPO_ENCRYPTED", "") in ("1", "true", "yes")
    storage["cache"] = cache_disk()

    hosts = db.query(ESXiHost).all()
    vcenters = [{"name": h.name, "address": h.host_ip, "reachable": _vcenter_reachable(h.host_ip)} for h in hosts]

    at, names = next_run(protected)
    problems = []
    if storage.get("error"):
        problems.append({"kind": "storage", "severity": "error",
                         "message": f"Backup storage is not available: {storage['error']}."})
    for vc in vcenters:
        if not vc["reachable"]:
            problems.append({"kind": "vcenter", "severity": "error",
                             "message": f"vCenter {vc['address']} is not reachable."})
    if failed_logs:
        first = failed_logs[0]
        more = f" and {len(failed_logs) - 1} more" if len(failed_logs) > 1 else ""
        problems.append({"kind": "backup", "severity": "error", "vm_name": first.vm_name,
                         "message": f"{len(failed_logs)} backup(s) failed in the last 24 h: "
                                    f"{first.vm_name}{more}. {(first.message or '')[:200]}".strip()})
    if not vddk_installed:
        problems.append({"kind": "vddk", "severity": "error", "message": "VDDK is not installed."})
    if scheduler_paused:
        problems.append({"kind": "paused", "severity": "warning", "message": "All scheduled backups are paused."})

    return {
        "last24h": {"succeeded": succeeded, "failed": len(failed_logs)},
        "next_run": {"at": at.isoformat() if at else None, "vm_count": len(names)},
        "protected": {"count": len(protected), "total": len(vms)},
        "storage": storage,
        "vcenters": vcenters,
        "never_powered_off": _never_powered_off(vms),
        "problems": problems,
    }


def _never_powered_off(vms):
    """VMs the power guard always refuses to power off (by name), for Settings > vCenter."""
    import power_guard
    return sorted(v.vm_name for v in vms if power_guard.name_block_reason(v.vm_name))

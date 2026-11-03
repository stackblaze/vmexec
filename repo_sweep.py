"""
Remove what a backup or restore left in backup storage when it could not
clean up itself (the worker was killed, the VM rebooted, out of memory):

- a restore-point folder that is not in its VM's chain index: a backup
  that never finished (a finished one is in the index);
- a _materialized folder: the temporary full disk of an old-style restore.

Only folders older than MIN_AGE are touched, and never those of a backup
that is running now. Runs from the worker's watchdog (sweep_repository).
"""
import os
import time

from logger_util import log_info, log_warn

MIN_AGE_SECS = 30 * 60
SWEEP_EVERY_SECS = 10 * 60
_last = {"at": 0.0}


def _age(path):
    try:
        return time.time() - os.stat(path).st_mtime
    except OSError:
        return 0


def sweep_repository(storage, running_vm_names, now=None, min_age=MIN_AGE_SECS):
    """Returns the relative paths removed."""
    from backup_manifest import load_chain
    resolve = getattr(storage, "_full_path", None)
    if resolve is None:
        return []
    removed = []
    for vm_name in storage.list_dirs(""):
        if vm_name.startswith("_") or vm_name in running_vm_names:
            continue
        points_rel = f"{vm_name}/_chain/points"
        if not storage.exists(points_rel):
            continue
        chain = load_chain(storage, vm_name) or {"points": []}
        known = {p["id"] for p in chain.get("points", [])}
        for pid in storage.list_dirs(points_rel):
            rel = f"{points_rel}/{pid}"
            full = resolve(rel)
            if pid not in known:
                if _age(full) >= min_age:
                    storage.delete_dir(rel)
                    removed.append(rel)
                continue
            mat = f"{rel}/_materialized"
            if storage.exists(mat) and _age(resolve(mat)) >= min_age:
                storage.delete_dir(mat)
                removed.append(mat)
    for rel in removed:
        log_info(f"[SWEEP] Removed leftover {rel}")
    return removed


def maybe_sweep(storage, running_vm_names):
    """At most every SWEEP_EVERY_SECS; never raises."""
    if time.time() - _last["at"] < SWEEP_EVERY_SECS:
        return []
    _last["at"] = time.time()
    try:
        return sweep_repository(storage, running_vm_names)
    except Exception as e:  # noqa: BLE001 - housekeeping must not stop the daemon
        log_warn(f"[SWEEP] skipped: {e}")
        return []

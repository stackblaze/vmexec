"""Capacity projection: expected steady-state repository usage of the
configured backup jobs versus the storage actually available.

Per selected VM the steady-state footprint is approximately

    2 x full_size + retention_count x daily_delta

Two fulls coexist because a full cannot be pruned while incrementals still
depend on it (the old chain survives until the next full completes). full_size
is estimated from the VM's committed size in vCenter (synced into
VM.storage_gb) scaled by FULL_RATIO — observed ratio of bytes a full actually
occupies on the repository (sparse writes, compression) to committed bytes.
daily_delta uses the measured average of the VM's recent incremental deltas
when the chain has history, else DELTA_FALLBACK_PCT of committed.
"""

import os

import backup_manifest as bm
from models import VM
from storage_util import get_storage

# Observed across live estates: sparse-aware transports write well under the
# committed size. Deliberately conservative (high) so the projection errs
# toward warning early rather than late.
FULL_RATIO = 0.7
# Daily change rate assumed until a chain has measured incrementals.
DELTA_FALLBACK_PCT = 0.04
# How many recent incrementals to average for the measured daily delta.
DELTA_SAMPLE_POINTS = 5
# Projected usage above this fraction of capacity is flagged.
WARN_THRESHOLD = 0.8

_GB = 1024 ** 3


def _measured_daily_delta_gb(storage, vm_name):
    """Average size (GB) of the VM's most recent incremental deltas, or None.

    Only works when the repository is local-path storage; S3 chains simply
    fall back to the percentage estimate.
    """
    base = getattr(storage, "base_path", None)
    if not base:
        return None
    try:
        chain = bm.load_chain(storage, vm_name)
        if not chain:
            return None
        incrementals = [p for p in chain.get("points", []) if p.get("type") == "incremental"]
        if not incrementals:
            return None
        sizes = []
        for point in incrementals[-DELTA_SAMPLE_POINTS:]:
            point_dir = os.path.join(base, vm_name, bm.CHAIN_DIR, "points", point["id"])
            if not os.path.isdir(point_dir):
                continue
            total = 0
            for name in os.listdir(point_dir):
                if name.endswith(".delta.nvbd"):
                    total += os.path.getsize(os.path.join(point_dir, name))
            if total > 0:
                sizes.append(total)
        if not sizes:
            return None
        return (sum(sizes) / len(sizes)) / _GB
    except Exception:
        return None


def project_usage(db, config, selection=None):
    """Projected steady-state repository usage for a set of jobs.

    selection: optional {vm_id: is_selected} overriding the stored selection —
    used to evaluate a proposed selection before it is applied. Returns a dict
    with per-VM rows and totals in GB; capacity comes from the caller's
    storage scan (disk_total_gb) and may be None (e.g. S3).
    """
    try:
        storage = get_storage(config)
    except Exception:
        storage = None

    vms = db.query(VM).all()
    rows = []
    total_gb = 0.0
    measured_count = 0
    for vm in vms:
        selected = vm.is_selected
        if selection is not None and vm.id in selection:
            selected = selection[vm.id]
        if not selected:
            continue
        committed_gb = float(vm.storage_gb or 0)
        retention = max(int(vm.retention_count or 7), 1)
        full_gb = committed_gb * FULL_RATIO
        measured = _measured_daily_delta_gb(storage, vm.vm_name) if storage else None
        if measured is not None:
            delta_gb = measured
            measured_count += 1
        else:
            delta_gb = committed_gb * DELTA_FALLBACK_PCT
        projected = 2 * full_gb + retention * delta_gb
        total_gb += projected
        rows.append({
            "vm_id": vm.id,
            "vm_name": vm.vm_name,
            "committed_gb": round(committed_gb, 1),
            "projected_gb": round(projected, 1),
            "delta_source": "measured" if measured is not None else "estimated",
        })

    rows.sort(key=lambda r: -r["projected_gb"])
    return {
        "projected_gb": round(total_gb, 1),
        "vm_count": len(rows),
        "measured_count": measured_count,
        "full_ratio": FULL_RATIO,
        "delta_fallback_pct": DELTA_FALLBACK_PCT,
        "warn_threshold": WARN_THRESHOLD,
        "vms": rows,
    }

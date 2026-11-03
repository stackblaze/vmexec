"""
Backup policies: when VMs are backed up and how long restore points are kept.

A VM is protected when it has a policy. The policy owns the schedule: on
every change its VMs get the policy's frequency/days and its start time plus
STAGGER_MINUTES per VM (by name), written to the VM's own schedule fields,
so the scheduler (worker.py) is unchanged. Retention reads keep_* through
retention_for(). Backups are always incremental with a full every
config.cbt_full_interval runs; that is not a policy setting.
"""
from sqlalchemy.exc import IntegrityError

from models import VM, BackupPolicy

STAGGER_MINUTES = 5

DEFAULT_POLICIES = (
    {"name": "Daily", "frequency": "daily", "days": "0,1,2,3,4,5,6", "hour": 2, "minute": 0,
     "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6},
    {"name": "Weekly", "frequency": "weekly", "days": "6", "hour": 3, "minute": 0,
     "keep_daily": 0, "keep_weekly": 4, "keep_monthly": 6},
)

LIMITS = {"keep_daily": (0, 90), "keep_weekly": (0, 52), "keep_monthly": (0, 120)}


class PolicyError(ValueError):
    """Invalid policy input, or an operation the policy's state does not allow."""


def policy_to_dict(policy):
    return {
        "id": policy.id,
        "name": policy.name,
        "frequency": policy.frequency,
        "days": policy.days,
        "hour": policy.hour,
        "minute": policy.minute,
        "keep_daily": policy.keep_daily,
        "keep_weekly": policy.keep_weekly,
        "keep_monthly": policy.keep_monthly,
        "vm_count": len(policy.vms),
        "summary": describe(policy),
    }


def describe(policy):
    """'Every day 02:00 · keep 7 daily, 4 weekly, 6 monthly'."""
    import time
    tz = time.strftime("%Z") or ""
    names = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
    when = f"{policy.hour:02d}:{policy.minute:02d}" + (f" {tz}" if tz else "")
    if policy.frequency == "daily":
        head = f"Every day {when}"
    else:
        days = [names[int(d)] for d in policy.days.split(",") if d.strip().isdigit() and 0 <= int(d) <= 6]
        head = f"{', '.join(days) or 'Weekly'} {when}"
    keep = [f"{n} {label}" for n, label in (
        (policy.keep_daily, "daily"), (policy.keep_weekly, "weekly"), (policy.keep_monthly, "monthly")) if n]
    return f"{head} · keep {', '.join(keep)}"


def _clean(data, current=None):
    """Validated fields for a create (current None) or an update."""
    out = {}
    if "name" in data or current is None:
        name = str(data.get("name") or "").strip()
        if not 1 <= len(name) <= 40:
            raise PolicyError("Name must be 1-40 characters.")
        out["name"] = name
    if "frequency" in data or current is None:
        freq = str(data.get("frequency") or "daily").lower()
        if freq not in ("daily", "weekly"):
            raise PolicyError("Frequency must be daily or weekly.")
        out["frequency"] = freq
    freq = out.get("frequency") or (current.frequency if current else "daily")
    if "days" in data or current is None or "frequency" in out:
        raw = data.get("days", current.days if current else "0,1,2,3,4,5,6") or ""
        days = sorted({int(d) for d in str(raw).split(",") if d.strip().isdigit() and 0 <= int(d) <= 6})
        if freq == "daily":
            days = list(range(7))
        if not days:
            raise PolicyError("Pick at least one day.")
        out["days"] = ",".join(str(d) for d in days)
    for key, (lo, hi) in (("hour", (0, 23)), ("minute", (0, 59)), *LIMITS.items()):
        if key in data or current is None:
            default = {"hour": 2, "minute": 0, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6}[key]
            try:
                val = int(data.get(key, default))
            except (TypeError, ValueError):
                raise PolicyError(f"{key} must be a number.")
            if not lo <= val <= hi:
                raise PolicyError(f"{key} must be between {lo} and {hi}.")
            out[key] = val
    keeps = [out.get(k, getattr(current, k, 0) if current else 0) for k in LIMITS]
    if not any(keeps):
        raise PolicyError("Keep at least one restore point (daily, weekly or monthly).")
    return out


def restagger(db, policy):
    """Write the policy's schedule onto its VMs, STAGGER_MINUTES apart."""
    vms = sorted(policy.vms, key=lambda v: v.vm_name or "")
    for i, vm in enumerate(vms):
        total = policy.minute + i * STAGGER_MINUTES
        vm.schedule_hour = (policy.hour + total // 60) % 24
        vm.schedule_minute = total % 60
        vm.schedule_frequency = policy.frequency
        vm.schedule_days = policy.days


def ensure_default_policies(db):
    """Create Daily/Weekly once; existing selected VMs without a policy join Daily."""
    if db.query(BackupPolicy).count() == 0:
        try:
            for spec in DEFAULT_POLICIES:
                db.add(BackupPolicy(**spec))
            db.commit()
        except IntegrityError:  # the other container created them first
            db.rollback()
    daily = db.query(BackupPolicy).filter(BackupPolicy.name == "Daily").first()
    orphans = db.query(VM).filter(VM.is_selected == True, VM.policy_id.is_(None)).all()  # noqa: E712
    if daily and orphans:
        for vm in orphans:
            vm.policy = daily
        db.flush()
        restagger(db, daily)
        db.commit()


def list_policies(db):
    return [policy_to_dict(p) for p in db.query(BackupPolicy).order_by(BackupPolicy.id).all()]


def create_policy(db, data):
    fields = _clean(data)
    if db.query(BackupPolicy).filter(BackupPolicy.name == fields["name"]).first():
        raise PolicyError(f"A policy named {fields['name']} already exists.")
    policy = BackupPolicy(**fields)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy_to_dict(policy)


def update_policy(db, policy_id, data):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == policy_id).first()
    if not policy:
        raise LookupError("Policy not found")
    fields = _clean(data, current=policy)
    if "name" in fields:
        clash = db.query(BackupPolicy).filter(BackupPolicy.name == fields["name"], BackupPolicy.id != policy_id).first()
        if clash:
            raise PolicyError(f"A policy named {fields['name']} already exists.")
    for k, v in fields.items():
        setattr(policy, k, v)
    restagger(db, policy)
    db.commit()
    db.refresh(policy)
    return policy_to_dict(policy)


def delete_policy(db, policy_id):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == policy_id).first()
    if not policy:
        raise LookupError("Policy not found")
    if policy.vms:
        raise PolicyError(f"{len(policy.vms)} VM(s) use {policy.name}. Move them to another policy first.")
    db.delete(policy)
    db.commit()


def assign(db, vm_ids, policy_id):
    """Put VMs on a policy (protect them), or policy_id None to unprotect."""
    policy = None
    if policy_id is not None:
        policy = db.query(BackupPolicy).filter(BackupPolicy.id == policy_id).first()
        if not policy:
            raise LookupError("Policy not found")
    vms = db.query(VM).filter(VM.id.in_(list(vm_ids))).all()
    if len(vms) != len(set(vm_ids)):
        raise LookupError("VM not found")
    touched = {vm.policy for vm in vms if vm.policy}
    for vm in vms:
        vm.policy = policy
        vm.is_selected = policy is not None
        if policy is not None:
            vm.is_job_active = True
    db.flush()
    for p in touched | ({policy} if policy else set()):
        restagger(db, p)
    db.commit()
    return [vm.id for vm in vms]


def retention_for(vm):
    """(daily, weekly, monthly) for a VM's policy, or None (legacy count retention)."""
    p = getattr(vm, "policy", None)
    if not p:
        return None
    return (p.keep_daily or 0, p.keep_weekly or 0, p.keep_monthly or 0)

import os
import sys
import time
import hashlib
import threading
from models import SessionLocal, VM, Config, ESXiHost, K8sCluster, init_db
import worker
from logger_util import log_info, log_error, log_critical
from config_env import DATA_DIR

SNAPSHOT_SWEEP_INTERVAL_SECS = 300

HEARTBEAT_FILE = os.path.join(DATA_DIR, "worker.heartbeat")


def _run_orphan_snapshot_sweep(min_age_secs=120):
    """Background sweep for VMBACKUP_TEMP_* snapshots left by crashed or killed backups."""
    try:
        from backup_engine import cleanup_orphaned_snapshots_all
        skip = worker.get_active_backup_vm_ids()
        removed = cleanup_orphaned_snapshots_all(skip_vm_ids=skip, min_age_secs=min_age_secs)
        if removed:
            label = "Startup" if min_age_secs == 0 else "Orphan sweep"
            log_info(f"[SNAPSHOT] {label}: removed {removed} orphaned backup snapshot(s)")
    except Exception as e:
        log_error(f"[SNAPSHOT] Orphan sweep failed: {e}")


def write_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass

def get_schedule_hash():
    """ Computes a hash of the current backup schedule for all VMs to detect changes. """
    db = SessionLocal()
    try:
        config = db.query(Config).first()
        paused = bool(getattr(config, "scheduler_paused", False)) if config else False
        vms = db.query(VM).filter(VM.is_selected == True).all()
        # Create a string representation of the schedule state
        # Include frequency/days/interval so switching e.g. daily → weekly
        # reschedules live (previously only hour/minute/active were hashed).
        state_str = f"paused:{int(paused)}|" + "".join(
            [f"{v.id}:{v.schedule_hour}:{v.schedule_minute}:{v.is_job_active}:"
             f"{getattr(v, 'schedule_frequency', 'daily')}:{getattr(v, 'schedule_days', '')}:"
             f"{getattr(v, 'interval_hours', 0)}"
             for v in vms]
        )
        clusters = db.query(K8sCluster).all()
        # Include targets JSON so per-target schedule edits reschedule live.
        state_str += "".join(
            [f"|k8s{c.id}:{c.schedule_hour}:{c.schedule_minute}:{c.is_job_active}:"
             f"{c.schedule_frequency}:{c.interval_hours}:{c.targets}" for c in clusters]
        )
        return hashlib.md5(state_str.encode()).hexdigest()
    finally:
        db.close()

def run_daemon():
    init_db()
    pid = os.getpid()
    log_info(f"[PID {pid}] Starting Backup Engine Daemon...")

    db = SessionLocal()
    try:
        if db.query(ESXiHost).count() > 0:
            from services.vddk_install import ensure_vddk_installed
            from vddk_transport import ensure_vddk_runtime_dirs
            ensure_vddk_runtime_dirs()
            ok, msg = ensure_vddk_installed(db.query(Config).first())
            log_info(f"[VDDK] Startup check: {msg}" if ok else f"[VDDK] Startup: {msg}")
    finally:
        db.close()
    
    # Initial scheduler start + concurrency limits
    worker.start_scheduler()
    db = SessionLocal()
    try:
        config = db.query(Config).first()
        worker.configure_concurrency(config or Config())
    finally:
        db.close()
    last_hash = get_schedule_hash()
    
    log_info(f"[PID {pid}] Enter polling loop. Monitoring DB for manual triggers and schedule changes.")
    write_heartbeat()
    
    # Reconcile stale in-progress state: no backup thread survives a restart,
    # so any non-empty action (Backing up.../Queued.../Stopping.../CBT.../waiting)
    # is stale and must be cleared. Preserve PENDING_RUN so a queued manual
    # trigger still fires after the restart.
    db = SessionLocal()
    try:
        for v in db.query(VM).all():
            action = (v.current_action or "").strip()
            if not action or action == "PENDING_RUN":
                continue
            log_info(
                f"[PID {pid}] Clearing stale action '{action}' for {v.vm_name} "
                "(no backup survives a worker restart)"
            )
            v.current_action = ""
            v.progress = 0
            v.speed_mbps = 0.0
        db.commit()
    finally:
        db.close()

    # Remove orphaned VMBACKUP_TEMP_* snapshots left by prior worker crashes/restarts
    threading.Thread(
        target=_run_orphan_snapshot_sweep,
        kwargs={"min_age_secs": 0},
        daemon=True,
        name="startup-snapshot-sweep",
    ).start()

    last_snapshot_sweep = time.time()

    while True:
        try:
            write_heartbeat()
            # 1. Check for schedule changes
            current_hash = get_schedule_hash()
            if current_hash != last_hash:
                log_info(f"[PID {pid}] Detected schedule changes in DB. Reloading scheduler...")
                worker.start_scheduler()
                last_hash = current_hash

            # 2. Poll for Manual Run Requests ("PENDING_RUN")
            db = SessionLocal()
            pending_runs = db.query(VM).filter(VM.current_action == "PENDING_RUN").all()
            for vm in pending_runs:
                log_info(f"[PID {pid}] Found manual trigger request for VM: {vm.vm_name}")
                vm.current_action = "Queued..."
                db.commit()
                # Submit to worker thread pool
                worker.queue_backup(vm.id)
                
            # 2b. Manual K8s snapshot requests. current_action == "PENDING_RUN"
            # runs all targets; "PENDING_RUN:<target>" runs just that one.
            for cl in db.query(K8sCluster).filter(
                    K8sCluster.current_action.like("PENDING_RUN%")).all():
                tgt = None
                if (cl.current_action or "").startswith("PENDING_RUN:"):
                    tgt = cl.current_action.split(":", 1)[1]
                log_info(f"[PID {pid}] Manual k8s snapshot request: "
                         f"{cl.name}/{tgt or 'all'}")
                cl.current_action = "Queued..."
                db.commit()
                worker.queue_k8s_backup(cl.id, tgt)

            # 3. Poll for Manual Stop Requests ("PENDING_STOP")
            pending_stops = db.query(VM).filter(VM.current_action == "PENDING_STOP").all()
            if pending_stops:
                active_ids = worker.get_active_backup_vm_ids()
                for vm in pending_stops:
                    log_info(f"[PID {pid}] Found manual stop request for VM: {vm.vm_name}")
                    worker.stop_job(vm.id)
                    if vm.id in active_ids or vm.id in worker.active_processes:
                        vm.current_action = "Stopping..."
                    else:
                        # Nothing actually running to stop; return to idle.
                        vm.current_action = ""
                        vm.progress = 0
                        vm.speed_mbps = 0.0
                    db.commit()
                
            db.close()

            now = time.time()
            if now - last_snapshot_sweep >= SNAPSHOT_SWEEP_INTERVAL_SECS:
                last_snapshot_sweep = now
                threading.Thread(
                    target=_run_orphan_snapshot_sweep,
                    kwargs={"min_age_secs": 120},
                    daemon=True,
                ).start()
            
        except Exception as e:
            log_error(f"{e}")
            
        # Poll every 5 seconds
        time.sleep(5)

if __name__ == "__main__":
    lock_file = "daemon.lock"
    lock_fh = None
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except:
            log_critical("Another instance of Backup Daemon is already running.")
            sys.exit(1)
            
    try:
        lock_fh = open(lock_file, "w")
        lock_fh.write(str(os.getpid()))
        lock_fh.flush()
        
        run_daemon()
    finally:
        if lock_fh:
            lock_fh.close()
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except:
                pass


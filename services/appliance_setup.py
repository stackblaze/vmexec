"""
Appliance setup steps that need the app's database, run by deploy/install.sh
inside the worker container:

  python -m services.appliance_setup storage /mnt/backups
      Backup storage = the ZeroFS mount (storage_type NFS, that path),
      incrementals on. Clears the unused direct-S3 settings, which held
      an S3 key the app no longer needs (ZeroFS has its own, on the host).

  python -m services.appliance_setup add-vcenter <name> <address>  < creds
      Register vCenter (username and password on stdin, one per line) if it
      is not registered yet. Verifies the login like Settings > vCenter.

  python -m services.appliance_setup vcenter <name> <address>  < creds
      Same, and when this vCenter is already registered with other
      credentials, switch it to these (login verified first). Used to move
      VMExec onto its own least-privilege account.

  python -m services.appliance_setup copy-db /mnt/backups/_appliance
      Copy the database and its keys into backup storage (daily timer), so
      install.sh --recover on a new VM brings back jobs, policies and the
      vCenter registration together with the backups.

  python -m services.appliance_setup summary /mnt/backups
      What this appliance knows after install.sh --recover: vCenters,
      protected VMs and policies, users, and the restore points in the
      repository (read from each VM's chain.json).
"""
import os
import shutil
import sqlite3
import sys
import tempfile

from config_env import DATA_DIR

DB_FILES = ("backup_system.db",)
KEY_FILES = ("secret.key", "session.key")  # credential encryption key, session signing key


def set_storage(path):
    from models import init_db, SessionLocal, Config
    init_db()
    db = SessionLocal()
    try:
        c = db.query(Config).first()
        c.storage_type = "NFS"
        c.nfs_path = path
        c.cbt_enabled = True
        for f in ("s3_endpoint", "s3_access_key", "s3_secret_key", "s3_bucket"):
            setattr(c, f, "")
        db.commit()
    finally:
        db.close()
    print(f"storage: {path} (ZeroFS), incrementals on, direct-S3 settings cleared")


def _fsync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_db(dest):
    # Every file and the folder are fsynced: ZeroFS keeps unsynced writes in its
    # local cache, and an appliance that dies (the case this copy is for) loses them.
    os.makedirs(dest, mode=0o700, exist_ok=True)
    for name in DB_FILES:
        src = os.path.join(DATA_DIR, name)
        if not os.path.exists(src):
            continue
        # sqlite's online backup: a consistent copy while the app runs.
        fd, tmp = tempfile.mkstemp(dir=dest, prefix=f".{name}.")
        os.close(fd)
        try:
            with sqlite3.connect(src) as s, sqlite3.connect(tmp) as d:
                s.backup(d)
            d.close()
            os.chmod(tmp, 0o600)
            _fsync(tmp)
            os.replace(tmp, os.path.join(dest, name))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    for name in KEY_FILES:
        src = os.path.join(DATA_DIR, name)
        if os.path.exists(src):
            dst = os.path.join(dest, name)
            shutil.copyfile(src, dst + ".tmp")
            os.chmod(dst + ".tmp", 0o600)
            _fsync(dst + ".tmp")
            os.replace(dst + ".tmp", dst)
    _fsync(dest)
    print(f"copied database and keys to {dest}")


def summary(repo):
    import json
    from models import init_db, SessionLocal, ESXiHost, VM, BackupPolicy, User
    from backup_manifest import chain_json_rel
    init_db()
    db = SessionLocal()
    try:
        hosts = db.query(ESXiHost).all()
        print("vCenter:        " + (", ".join(f"{h.name} ({h.host_ip}, {h.username})" for h in hosts) or "none"))
        protected = db.query(VM).filter(VM.policy_id.isnot(None)).all()
        policies = db.query(BackupPolicy).all()
        print(f"Protected VMs:  {len(protected)}" + (f" ({', '.join(sorted(v.vm_name for v in protected))})" if protected else ""))
        print(f"Policies:       {len(policies)}" + (f" ({', '.join(p.name for p in policies)})" if policies else ""))
        print(f"Users:          {db.query(User).count()}")
    finally:
        db.close()
    total, vms, newest = 0, 0, ""
    try:
        names = sorted(os.listdir(repo))
    except OSError as e:
        print(f"Restore points: cannot read {repo}: {e}")
        return
    for name in names:
        path = os.path.join(repo, chain_json_rel(name))
        try:
            with open(path) as f:
                points = json.load(f).get("points") or []
        except (OSError, ValueError):
            continue
        if points:
            vms += 1
            total += len(points)
            newest = max([newest] + [str(p.get("timestamp") or "") for p in points])
    print(f"Restore points: {total} across {vms} VMs" + (f", newest {newest}" if newest else ""))


def add_vcenter(name, address):
    import esxi_handler
    from models import init_db, SessionLocal, ESXiHost
    from services import backup_ops
    lines = sys.stdin.read().splitlines()
    if len(lines) < 2 or not lines[0] or not lines[1]:
        raise SystemExit("add-vcenter: expected username and password on stdin")
    init_db()
    db = SessionLocal()
    try:
        addr = esxi_handler.normalize_host(address)
        if db.query(ESXiHost).filter(ESXiHost.host_ip == addr).first():
            print(f"vCenter {addr} is already connected")
            return
        try:
            backup_ops.add_esxi_host(db, name, addr, lines[0], lines[1], connection_type="auto")
        except (ValueError, ConnectionError) as e:
            raise SystemExit(f"add-vcenter: {e}")
        print(f"vCenter {addr} connected as {name}")
    finally:
        db.close()


def set_vcenter(name, address):
    import esxi_handler
    from models import init_db, SessionLocal, ESXiHost
    lines = sys.stdin.read().splitlines()
    if len(lines) < 2 or not lines[0] or not lines[1]:
        raise SystemExit("vcenter: expected username and password on stdin")
    user, password = lines[0], lines[1]
    init_db()
    db = SessionLocal()
    try:
        addr = esxi_handler.normalize_host(address)
        host = db.query(ESXiHost).filter(ESXiHost.host_ip == addr).first()
        if host is None:
            from services import backup_ops
            try:
                backup_ops.add_esxi_host(db, name, addr, user, password, connection_type="auto")
            except (ValueError, ConnectionError) as e:
                raise SystemExit(f"vcenter: {e}")
            print(f"vCenter {addr} connected as {user}")
            return
        if host.username == user and host.password == password:
            print(f"vCenter {addr}: already uses {user}")
            return
        try:
            si = esxi_handler.connect_esxi(addr, user, password, raise_on_error=True)
        except esxi_handler.VSphereConnectionError as e:
            raise SystemExit(f"vcenter: login as {user} failed: {e}")
        esxi_handler.Disconnect(si)
        host.username, host.password = user, password
        db.commit()
        print(f"vCenter {addr}: switched to {user}")
    finally:
        db.close()


def main(argv):
    if len(argv) == 2 and argv[0] == "storage":
        return set_storage(argv[1])
    if len(argv) == 2 and argv[0] == "copy-db":
        return copy_db(argv[1])
    if len(argv) == 2 and argv[0] == "summary":
        return summary(argv[1])
    if len(argv) == 3 and argv[0] == "add-vcenter":
        return add_vcenter(argv[1], argv[2])
    if len(argv) == 3 and argv[0] == "vcenter":
        return set_vcenter(argv[1], argv[2])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

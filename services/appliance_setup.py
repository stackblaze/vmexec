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

  python -m services.appliance_setup copy-db /mnt/backups/_appliance
      Copy the database and its keys into backup storage (daily timer), so
      install.sh --recover on a new VM brings back jobs, policies and the
      vCenter registration together with the backups.
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


def copy_db(dest):
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
            os.chmod(tmp, 0o600)
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
            os.replace(dst + ".tmp", dst)
    print(f"copied database and keys to {dest}")


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


def main(argv):
    if len(argv) == 2 and argv[0] == "storage":
        return set_storage(argv[1])
    if len(argv) == 2 and argv[0] == "copy-db":
        return copy_db(argv[1])
    if len(argv) == 3 and argv[0] == "add-vcenter":
        return add_vcenter(argv[1], argv[2])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

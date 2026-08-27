"""
secondary_copy.py — 3-2-1 secondary repository copy after backup.
"""

import os
import shutil
import subprocess

from logger_util import log_info, log_warn, log_error


def secondary_enabled(config):
    return bool(getattr(config, "secondary_copy_enabled", False))


def authenticate_secondary_smb(config):
    """Authenticate to secondary SMB share on Windows hosts."""
    stype = (getattr(config, "secondary_storage_type", None) or "NFS").upper()
    if stype != "SMB":
        return True, "Not SMB"
    path = getattr(config, "secondary_smb_unc_path", "") or ""
    if not path or os.name != "nt":
        return True, "SMB auth skipped"
    user = getattr(config, "secondary_smb_user", "") or ""
    subprocess.run(["net", "use", path, "/delete", "/y"], capture_output=True)
    cmd = ["net", "use", path]
    password = getattr(config, "secondary_smb_password", "") or ""
    if password and user:
        cmd.extend([password, f"/user:{user}"])
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        msg = f"Secondary SMB auth failed: {res.stderr}"
        log_warn(f"[COPY] {msg}")
        return False, msg
    log_info(f"[COPY] Secondary SMB authenticated: {path}")
    return True, "Secondary SMB OK"


def get_secondary_storage(config):
    from storage_util import get_secondary_storage as _build
    return _build(config)


def _copy_dir_recursive(primary, secondary, rel_path):
    """Recursively copy a directory tree via storage providers.

    Files already present on the secondary with a matching size are skipped —
    hourly K8s state syncs re-walk the same tree and must not re-upload
    hundreds of MB of unchanged snapshots every run."""
    secondary.makedirs(rel_path)
    for fn in primary.list_files(rel_path) or []:
        src_rel = f"{rel_path.rstrip('/')}/{fn}"
        try:
            if secondary.exists(src_rel) and \
                    secondary.get_size(src_rel) == primary.get_size(src_rel):
                continue
        except Exception:
            pass  # unknown state → copy
        with primary.open_read(src_rel) as src, secondary.open_write(src_rel) as dst:
            shutil.copyfileobj(src, dst)
    for subdir in primary.list_dirs(rel_path) or []:
        _copy_dir_recursive(primary, secondary, f"{rel_path.rstrip('/')}/{subdir}")


def copy_tree(primary, secondary, rel_path):
    """Copy a backup folder from primary to secondary storage."""
    if not secondary or not rel_path:
        return False, "Secondary storage not configured"

    if not primary.exists(rel_path) and not primary.list_dirs(rel_path):
        return False, f"Source not found: {rel_path}"

    # Local-to-local fast path
    if hasattr(primary, "base_path") and hasattr(secondary, "base_path"):
        src = os.path.join(primary.base_path, rel_path)
        dst = os.path.join(secondary.base_path, rel_path)
        if not os.path.isdir(src):
            return False, f"Source is not a directory: {src}"
        os.makedirs(os.path.dirname(dst) or secondary.base_path, exist_ok=True)
        if os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        log_info(f"[COPY] Secondary copy: {rel_path} → {secondary.base_path}")
        return True, f"Copied to {dst}"

    try:
        _copy_dir_recursive(primary, secondary, rel_path.rstrip("/"))
        log_info(f"[COPY] Secondary copy (recursive): {rel_path}")
        return True, f"Copied {rel_path} via storage API"
    except Exception as e:
        log_error(f"[COPY] Secondary copy failed: {e}")
        return False, str(e)


def sync_after_backup(config, primary_storage, dest_rel_dir):
    """Run secondary copy if enabled. Returns (ok, message)."""
    if not secondary_enabled(config):
        return True, "Secondary copy disabled"
    auth_ok, auth_msg = authenticate_secondary_smb(config)
    if not auth_ok:
        return False, auth_msg
    secondary = get_secondary_storage(config)
    if not secondary:
        return False, "Secondary storage unavailable"
    # CBT: sync entire chain tree so secondary has consistent chain.json + all points
    if dest_rel_dir and "/_chain/points/" in dest_rel_dir:
        vm_name = dest_rel_dir.split("/")[0]
        dest_rel_dir = f"{vm_name}/_chain"
    return copy_tree(primary_storage, secondary, dest_rel_dir)

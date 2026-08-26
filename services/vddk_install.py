"""Auto-install VMware VDDK when ESXi hosts are added."""

import glob
import os
import re
import shutil
import tarfile

from config_env import DATA_DIR
from logger_util import log_info, log_warn, log_error

# Bundled tarball locations (read-only mount in Docker)
VDDK_VENDOR_DIRS = [
    "/app/vendor/vddk",
    "/opt/vmexec/vendor/vddk",
    os.path.join(DATA_DIR, "vendor", "vddk"),
    # Legacy NovaBak location, kept last so existing installs keep working.
    "/opt/NovaBak/vendor/vddk",
]


def get_vddk_libdir(config=None):
    if config is not None:
        libdir = getattr(config, "vddk_libdir", None)
        if libdir and libdir.strip():
            return libdir.strip()
    env = os.environ.get("VDDK_LIBDIR")
    if env:
        return env
    return os.path.join(DATA_DIR, "vddk", "vmware-vix-disklib-distrib")


def parse_vddk_version(path):
    """
    Extract a comparable version tuple from a VDDK tarball filename.

    Broadcom has shipped several shapes across releases, e.g.
        VMware-vix-disklib-8.0.3-24145417.x86_64.tar.gz
        VMware-vix-disklib-9.0.0-24280709.x86_64.tar.gz
    Returns () when no version can be read, which sorts below anything real.
    """
    m = re.search(r"VMware-vix-disklib-([0-9]+(?:\.[0-9]+)*)", os.path.basename(path))
    if not m:
        return ()
    return tuple(int(part) for part in m.group(1).split("."))


def find_vddk_tarball():
    """
    Return the HIGHEST-VERSION VMware-vix-disklib-*.tar.gz in the vendor dirs.

    Previously this picked by mtime, so copying an older tarball onto a host
    that already had a newer one silently downgraded VDDK. Version wins; mtime
    only breaks ties between identical versions.
    """
    candidates = []
    for vendor_dir in VDDK_VENDOR_DIRS:
        if not os.path.isdir(vendor_dir):
            continue
        candidates.extend(glob.glob(os.path.join(vendor_dir, "VMware-vix-disklib-*.tar.gz")))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (parse_vddk_version(p), os.path.getmtime(p)))


def is_vddk_installed(libdir=None):
    libdir = libdir or get_vddk_libdir()
    for sub in ("lib64", "lib32"):
        if os.path.isfile(os.path.join(libdir, sub, "libvixDiskLib.so")):
            return True
    return False


def _find_distrib_root(root):
    """
    Locate the VDDK distribution inside an extracted tarball.

    Identifies it by CONTENT — the directory holding lib64/libvixDiskLib.so —
    rather than by the exact name "vmware-vix-disklib-distrib". The old exact
    match meant any future layout change (a version-qualified directory name,
    an extra nesting level) failed with "not found in tarball" even though the
    library was present, so a new VDDK release could not be adopted without a
    code change. Searched depth-first, shallowest match wins.
    """
    for current, dirnames, _files in os.walk(root):
        for sub in ("lib64", "lib32"):
            if os.path.isfile(os.path.join(current, sub, "libvixDiskLib.so")):
                return current
        # keep the walk cheap and deterministic
        dirnames.sort()
    return None


def install_vddk_from_tarball(tarball_path, libdir=None):
    """
    Extract VDDK tarball to libdir.
    Returns (ok: bool, message: str).
    """
    libdir = libdir or get_vddk_libdir()
    if not tarball_path or not os.path.isfile(tarball_path):
        return False, f"VDDK tarball not found: {tarball_path}"

    log_info(f"[VDDK] Installing from {tarball_path} → {libdir}")
    tmp = libdir + ".tmp"
    try:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)

        with tarfile.open(tarball_path, "r:gz") as tf:
            # filter="data" refuses absolute paths, traversal and special files.
            # Added in 3.11.4/3.12 and the default from 3.14; passing it
            # explicitly keeps behaviour identical across those versions.
            try:
                tf.extractall(tmp, filter="data")
            except TypeError:
                tf.extractall(tmp)

        distrib = _find_distrib_root(tmp)
        if not distrib:
            return False, (
                "No VDDK distribution found in the tarball: no directory "
                "containing lib64/libvixDiskLib.so (or lib32)."
            )

        if os.path.isdir(libdir):
            shutil.rmtree(libdir)
        shutil.move(distrib, libdir)
        shutil.rmtree(tmp, ignore_errors=True)

        parsed = parse_vddk_version(tarball_path)
        version = ".".join(str(n) for n in parsed) if parsed else "unknown version"
        log_info(f"[VDDK] Installed version {version} at {libdir}")
        return True, f"VDDK {version} installed at {libdir}"

    except Exception as e:
        log_error(f"[VDDK] Install failed: {e}")
        shutil.rmtree(tmp, ignore_errors=True)
        return False, str(e)


def ensure_vddk_installed(config=None, force=False):
    """
    Install VDDK from vendor tarball if not already present.
    Returns (installed: bool, message: str).
    """
    libdir = get_vddk_libdir(config)

    if not force and is_vddk_installed(libdir):
        return True, f"VDDK already installed at {libdir}"

    tarball = find_vddk_tarball()
    if not tarball:
        # Name the directories actually searched. The old text hardcoded
        # /opt/NovaBak/vendor/vddk, which does not exist on most installs, so
        # the one instruction the operator gets pointed at the wrong place.
        searched = ", ".join(VDDK_VENDOR_DIRS)
        return False, (
            "No VDDK tarball found. Download VMware-vix-disklib-*.tar.gz from "
            "Broadcom (it is proprietary and cannot be shipped with VMExec) and "
            f"place it in one of: {searched}"
        )

    ok, msg = install_vddk_from_tarball(tarball, libdir)
    return ok, msg


def ensure_vddk_on_host_add(db):
    """
    Called when an ESXi host is added: install VDDK and enable NBD transport.
    Returns dict with vddk status for API/UI feedback.
    """
    from models import Config

    config = db.query(Config).first()
    ok, msg = ensure_vddk_installed(config)

    if config:
        if ok:
            config.vddk_libdir = get_vddk_libdir(config)
            if getattr(config, "backup_transport", "legacy") in ("legacy", None, ""):
                config.backup_transport = "nbd"
                log_info("[VDDK] Set backup_transport=nbd after VDDK install")
        db.commit()

    if ok:
        log_info(f"[VDDK] Host-add bootstrap: {msg}")
    else:
        log_warn(f"[VDDK] Host-add bootstrap skipped: {msg}")

    return {"vddk_installed": ok, "vddk_message": msg}

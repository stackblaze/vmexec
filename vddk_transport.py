"""
vddk_transport.py — VDDK/NBD live backup transport

Streams snapshot-backed virtual disks over NBD using nbdkit-vddk-plugin.
Works against standalone ESXi and vCenter (see vsphere_context.py).

See: https://libguestfs.org/nbdkit-vddk-plugin.1.html
"""

import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time

from logger_util import log_info, log_warn, log_error
import vsphere_context

# Cached ESXi/vCenter SSL thumbprints for the process lifetime
_thumbprint_cache = {}

SNAPSHOT_SETTLE_SECS = 3


class VddkNotAvailableError(Exception):
    """Raised when VDDK/NBD dependencies are missing or misconfigured."""


def get_vddk_libdir(config):
    from services.vddk_install import get_vddk_libdir as _libdir
    return _libdir(config)


def is_available(config=None):
    """Return True if nbdkit-vddk plugin and VDDK library are present."""
    if shutil.which("nbdkit") is None:
        return False
    if not _nbdkit_vddk_plugin_present():
        return False
    libdir = get_vddk_libdir(config)
    for sub in ("lib64", "lib32"):
        if os.path.isfile(os.path.join(libdir, sub, "libvixDiskLib.so")):
            return True
    return False


def _nbdkit_vddk_plugin_present():
    import glob as _glob
    patterns = [
        "/usr/lib/x86_64-linux-gnu/nbdkit/plugins/nbdkit-vddk-plugin.so",
        "/usr/lib/*/nbdkit/plugins/nbdkit-vddk-plugin.so",
        "/usr/local/lib/nbdkit/plugins/nbdkit-vddk-plugin.so",
    ]
    for pat in patterns:
        if _glob.glob(pat):
            return True
    return False


def availability_message(config=None):
    """Human-readable reason when is_available() is False."""
    if shutil.which("nbdkit") is None:
        return "nbdkit not found in PATH"
    if not _nbdkit_vddk_plugin_present():
        return "nbdkit-vddk-plugin not installed (rebuild worker image)"
    libdir = get_vddk_libdir(config)
    if not is_vddk_lib_installed(libdir):
        return f"VDDK library missing under {libdir} (add ESXi host to auto-install from vendor/vddk/)"
    return "unknown"


def is_vddk_lib_installed(libdir):
    for sub in ("lib64", "lib32"):
        if os.path.isfile(os.path.join(libdir, sub, "libvixDiskLib.so")):
            return True
    return False


def ensure_vddk_runtime_dirs():
    """VDDK creates cache dirs under /tmp/vmware-root; ensure writable."""
    for path in ("/tmp/vmware-root", os.path.expanduser("~/.vmware")):
        try:
            os.makedirs(path, mode=0o1777, exist_ok=True)
        except OSError:
            pass


def get_server_thumbprint(host, port=443):
    """Fetch and cache the ESXi/vCenter SSL certificate thumbprint."""
    cache_key = f"{host}:{port}"
    if cache_key in _thumbprint_cache:
        return _thumbprint_cache[cache_key]

    try:
        with socket.create_connection((host, port), timeout=15) as sock:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                der = ssock.getpeercert(binary_form=True)
    except OSError as e:
        raise VddkNotAvailableError(f"Cannot reach {host}:{port} for thumbprint: {e}") from e

    import hashlib
    digest = hashlib.sha1(der).hexdigest().upper()
    thumbprint = ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))
    _thumbprint_cache[cache_key] = thumbprint
    return thumbprint


def _file_bytes_written(path):
    """Actual bytes on disk (handles sparse VMDK files correctly)."""
    try:
        st = os.stat(path)
        return st.st_blocks * 512
    except OSError:
        return 0


def _stream_disk_via_nbdcopy(
    cmd_prefix,
    dest_path,
    timeout_secs=7200,
    stall_secs=120,
    capacity_bytes=None,
    progress_callback=None,
    progress_base=0,
    progress_total=100,
    speed_callback=None,
    action_callback=None,
    is_cancelled_func=None,
):
    """Run nbdkit with nbdcopy to write a flat disk image to dest_path."""
    import time

    nbdcopy = shutil.which("nbdcopy")
    if not nbdcopy:
        raise VddkNotAvailableError("nbdcopy not found in PATH (install libnbd-bin)")

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)

    # nbdkit runs with -v and is extremely chatty (a debug line per read). If
    # its stderr goes to a pipe that we don't drain while the copy runs, the
    # ~64 KB OS pipe buffer fills, nbdkit blocks on its next log write, and the
    # whole transfer freezes — observed as a bogus "stall" at a few tens of MB.
    # Send stderr to a file so it can never block (same pattern as the extent
    # reader path). Read the tail only on failure.
    err_fd, err_path = tempfile.mkstemp(prefix="nbdkit_copy_err_")
    os.close(err_fd)
    # nbdcopy --progress=FD periodically writes "N/100" reflecting how far it
    # has advanced through the SOURCE. Unlike destination allocation (st_blocks),
    # this keeps moving while nbdcopy streams large all-zero regions (which it
    # writes back as holes, so st_blocks flatlines). We use it as a second
    # liveness signal so sparse disks don't trip a false stall, and to drive an
    # accurate progress bar. FD 3 is redirected to a file inside the --run shell.
    prog_fd, prog_path = tempfile.mkstemp(prefix="nbdcopy_prog_")
    os.close(prog_fd)
    run_cmd = cmd_prefix + [
        "--run",
        f'{nbdcopy} --no-extents --progress=3 "$uri" "{dest_path}" 3>"{prog_path}"',
    ]
    log_info(f"[NBD] Streaming disk → {dest_path}")
    if action_callback:
        action_callback("Streaming disk via NBD…")

    def _read_progress_pct():
        """Last 'N/100' value nbdcopy wrote to the progress file, or None."""
        try:
            with open(prog_path, "r", errors="replace") as f:
                data = f.read()
        except OSError:
            return None
        pct = None
        for tok in data.split():
            if tok.endswith("/100"):
                try:
                    pct = int(tok.split("/", 1)[0])
                except ValueError:
                    pass
        return pct

    def _err_tail():
        try:
            with open(err_path, "r", errors="replace") as f:
                return f.read()[-2000:].strip()
        except OSError:
            return ""

    def _cleanup_tmp():
        for p in (prog_path, err_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    errf = open(err_path, "wb")
    proc = subprocess.Popen(run_cmd, stdout=subprocess.DEVNULL, stderr=errf)
    errf.close()
    start = time.time()
    last_size = 0
    last_pct = -1
    last_advance = start
    last_speed_t = start

    def _abort(msg):
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=30)
            except Exception:
                pass
        err = _err_tail()
        _cleanup_tmp()
        raise RuntimeError(f"{msg}. {err}" if err else msg)

    try:
        while proc.poll() is None:
            if is_cancelled_func and is_cancelled_func():
                _abort("Backup cancelled by user")
            if time.time() - start > timeout_secs:
                _abort(f"nbdcopy timed out after {timeout_secs}s")
            time.sleep(1.5)
            now = time.time()
            size = _file_bytes_written(dest_path) if os.path.isfile(dest_path) else 0
            pct = _read_progress_pct()
            # Advance if EITHER the destination grew (non-zero regions) OR the
            # source read position moved (zero regions). Only a genuine hang
            # freezes both at once.
            advanced = False
            if size > last_size:
                advanced = True
            if pct is not None and pct > last_pct:
                last_pct = pct
                advanced = True
            if advanced:
                last_advance = now
            elif now - last_advance > stall_secs:
                _abort(
                    f"nbdcopy stalled: no data written for {stall_secs}s"
                    if size == 0 and last_pct <= 0
                    else f"nbdcopy stalled: no progress for {stall_secs}s at {size // (1024 * 1024)} MB"
                )
            dt = now - last_speed_t
            if dt >= 1.5 and speed_callback and size > last_size:
                mbps = (size - last_size) / dt / (1024 * 1024)
                if mbps > 0:
                    speed_callback(round(mbps, 1))
                last_speed_t = now
            if size > last_size:
                last_size = size
            if progress_callback:
                if pct is not None and pct >= 0:
                    p = progress_base + int(pct / 100 * progress_total)
                    progress_callback(min(p, progress_base + max(progress_total - 1, 0)))
                elif capacity_bytes and capacity_bytes > 0 and size > 0:
                    p = progress_base + int((size / capacity_bytes) * progress_total)
                    progress_callback(min(p, progress_base + max(progress_total - 1, 0)))
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=30)
            except Exception:
                pass

    rc = proc.returncode
    written = _file_bytes_written(dest_path) if os.path.isfile(dest_path) else 0
    err = _err_tail()
    _cleanup_tmp()
    if rc != 0:
        raise RuntimeError(f"nbdcopy failed (exit {rc}): {err}")
    if progress_callback:
        progress_callback(min(progress_base + progress_total, 99))
    return written


def _resolve_local_dest(storage, dest_rel_path):
    """NBD writes via nbdcopy to a local path; resolve from StorageProvider."""
    base = storage.get_base_path()
    if base.startswith("s3://"):
        return None, "NBD transport currently requires local or NFS backup storage (not S3)"
    if hasattr(storage, "base_path"):
        full = os.path.join(storage.base_path, dest_rel_path)
        return full, None
    if os.path.isabs(dest_rel_path):
        return dest_rel_path, None
    if os.path.isdir(base.rstrip("/")):
        return os.path.join(base.rstrip("/"), dest_rel_path), None
    return None, f"Cannot resolve local path for storage base: {base}"


def stream_snapshot_disk(
    si,
    vm,
    snap_obj,
    disk,
    server_host,
    host_user,
    host_password,
    storage,
    dest_rel_path,
    config=None,
    connection_type=vsphere_context.CONN_AUTO,
    is_cancelled_func=None,
    progress_callback=None,
    progress_base=0,
    progress_total=100,
    speed_callback=None,
    action_callback=None,
):
    """
    Stream one snapshot-backed disk descriptor to storage via NBD/VDDK.
    Tries multiple disk open paths (active delta vs base) before failing.
    """
    if not is_available(config):
        raise VddkNotAvailableError(availability_message(config))

    ensure_vddk_runtime_dirs()
    dest_path, err = _resolve_local_dest(storage, dest_rel_path)
    if err:
        raise VddkNotAvailableError(err)

    libdir = get_vddk_libdir(config)
    thumbprint = get_server_thumbprint(server_host)
    conn_type = vsphere_context.resolve_connection_type(si, connection_type)
    candidates = vsphere_context.vddk_disk_open_candidates(disk, conn_type)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="vddk_pw_") as pw_file:
        pw_file.write(host_password)
        pw_path = pw_file.name

    last_err = None
    try:
        for disk_ds_path in candidates:
            if is_cancelled_func and is_cancelled_func():
                raise RuntimeError("Backup cancelled by user")
            cmd, _ = vsphere_context.build_nbdkit_vddk_cmd(
                si=si,
                vm=vm,
                snap_obj=snap_obj,
                disk_ds_path=disk_ds_path,
                server_host=server_host,
                user=host_user,
                password_file=pw_path,
                thumbprint=thumbprint,
                libdir=libdir,
                stored_type=connection_type,
            )
            log_info(
                f"[NBD] VDDK via {vsphere_context.connection_label(conn_type)}: "
                f"vm=moref={vsphere_context.get_vm_moref(vm)} "
                f"snapshot={vsphere_context.get_snapshot_moref(snap_obj)} "
                f"disk={disk_ds_path}"
            )
            try:
                capacity = disk.get("capacity_bytes") if isinstance(disk, dict) else None
                nbytes = _stream_disk_via_nbdcopy(
                    cmd,
                    dest_path,
                    capacity_bytes=capacity,
                    progress_callback=progress_callback,
                    progress_base=progress_base,
                    progress_total=progress_total,
                    speed_callback=speed_callback,
                    action_callback=action_callback,
                    is_cancelled_func=is_cancelled_func,
                )
                if progress_callback:
                    progress_callback(min(progress_base + progress_total, 99))
                return nbytes
            except RuntimeError as e:
                last_err = e
                log_warn(f"[NBD] VDDK open failed for {disk_ds_path}: {str(e)[:300]}")
        raise last_err or RuntimeError("VDDK failed for all disk open candidates")
    finally:
        try:
            os.unlink(pw_path)
        except OSError:
            pass


def export_live_nbd(
    si,
    vm_name,
    storage,
    dest_rel_dir,
    disk_descriptors,
    vmx_ds_name,
    vmx_rel_path,
    server_host,
    host_user,
    host_password,
    config=None,
    connection_type=vsphere_context.CONN_AUTO,
    progress_callback=None,
    speed_callback=None,
    action_callback=None,
    is_cancelled_func=None,
    create_snapshot_func=None,
    remove_snapshot_func=None,
    download_vmx_func=None,
):
    """
    Live VM backup via VDDK/NBD (no CopyVirtualDisk temp on ESXi).
    server_host is the registered endpoint (ESXi or vCenter FQDN/IP).
    """
    if not is_available(config):
        return False, f"NBD transport unavailable: {availability_message(config)}"

    from backup_engine import _find_snapshot_by_name, _collect_vm_disk_layout

    vm = vsphere_context.find_vm_by_name(si, vm_name)
    if not vm:
        return False, f"VM {vm_name} not found"

    snap_obj = None
    snap_name = None
    files_downloaded = []

    try:
        if action_callback:
            action_callback("Creating backup snapshot…")
        snap_obj, snap_name = create_snapshot_func(si, vm_name)
        if not snap_obj:
            return False, f"Snapshot creation failed: {snap_name}"
        if snap_name and not getattr(snap_obj, "_moId", None):
            vm_refreshed = vsphere_context.find_vm_by_name(si, vm_name)
            resolved = _find_snapshot_by_name(vm_refreshed, snap_name)
            if resolved:
                snap_obj = resolved
            else:
                return False, f"Cannot resolve snapshot moRef for {snap_name}"

        log_info(f"[NBD] Waiting {SNAPSHOT_SETTLE_SECS}s for snapshot to settle...")
        if action_callback:
            action_callback(f"Waiting {SNAPSHOT_SETTLE_SECS}s for snapshot to settle…")
        time.sleep(SNAPSHOT_SETTLE_SECS)

        vm = vsphere_context.find_vm_by_name(si, vm_name)
        _, disk_descriptors, _, _ = _collect_vm_disk_layout(vm, config=config)
        if not disk_descriptors:
            return False, f"No disks found for {vm_name} after snapshot"

        storage.makedirs(dest_rel_dir)
        total_disks = len(disk_descriptors)

        for idx, disk in enumerate(disk_descriptors):
            if is_cancelled_func and is_cancelled_func():
                return False, "Backup cancelled by user"

            disk_basename = os.path.basename(disk["rel_path"])
            flat_basename = disk_basename.replace(".vmdk", "-flat.vmdk")
            flat_rel = f"{dest_rel_dir}/{flat_basename}"
            desc_rel = f"{dest_rel_dir}/{disk_basename}"

            step_base = 5 + (85 * idx // max(total_disks, 1))
            step_end = 5 + (85 * (idx + 1) // max(total_disks, 1))

            log_info(f"[NBD] Disk {idx + 1}/{total_disks}: {disk_basename}")

            if download_vmx_func:
                download_vmx_func(
                    si, disk["ds_name"], disk["rel_path"], storage, desc_rel,
                    progress_callback=progress_callback,
                    progress_base=step_base,
                    progress_total=2,
                    speed_callback=speed_callback,
                    is_cancelled_func=is_cancelled_func,
                    vm=vm,
                )
            files_downloaded.append(disk_basename)

            stream_snapshot_disk(
                si, vm, snap_obj, disk,
                server_host, host_user, host_password,
                storage, flat_rel, config=config,
                connection_type=connection_type,
                is_cancelled_func=is_cancelled_func,
                progress_callback=progress_callback,
                progress_base=step_base + 2,
                progress_total=max(step_end - step_base - 2, 1),
                speed_callback=speed_callback,
                action_callback=action_callback,
            )
            files_downloaded.append(flat_basename)

        if progress_callback:
            progress_callback(93)
        if remove_snapshot_func and snap_name:
            remove_snapshot_func(si, vm_name, snap_name, timeout_mins=60)
            snap_name = None

        if progress_callback:
            progress_callback(96)
        if vmx_ds_name and vmx_rel_path and download_vmx_func:
            vmx_filename = os.path.basename(vmx_rel_path)
            try:
                download_vmx_func(
                    si, vmx_ds_name, vmx_rel_path, storage, f"{dest_rel_dir}/{vmx_filename}",
                    is_cancelled_func=is_cancelled_func,
                    vm=vm,
                )
                files_downloaded.append(vmx_filename)
            except Exception as e:
                log_warn(f"[NBD] VMX download warning: {e}")

        if progress_callback:
            progress_callback(100)
        conn = vsphere_context.resolve_connection_type(si, connection_type)
        return True, (
            f"Backup completed [nbd/{conn}]: {len(files_downloaded)} file(s) saved to storage"
        )

    except VddkNotAvailableError as e:
        return False, str(e)
    except Exception as e:
        if is_cancelled_func and is_cancelled_func():
            return False, "Backup cancelled by user"
        log_error(f"[NBD] Live backup failed: {e}")
        return False, str(e)
    finally:
        if snap_name and remove_snapshot_func:
            try:
                remove_snapshot_func(si, vm_name, snap_name, timeout_mins=30)
            except Exception as ce:
                log_error(f"[NBD] Snapshot cleanup error: {ce}")


def _python313():
    """Debian python3 (matches python3-libnbd); worker app is 3.11."""
    return "/usr/bin/python3" if os.path.isfile("/usr/bin/python3") else sys.executable


def _wait_for_unix_socket(path, proc, err_path, timeout_secs=60):
    """Wait for nbdkit's UNIX socket; raise with nbdkit stderr if it dies first."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        if os.path.exists(path):
            return
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    err = ""
    try:
        with open(err_path, "r", errors="replace") as f:
            err = f.read()[-800:]
    except OSError:
        pass
    raise RuntimeError(f"nbdkit failed to start extent reader. {err}".strip())


# Reader runs under system python3 (has python3-libnbd); connects to the open
# nbdkit UNIX socket and streams framed (offset,len,data) for each area.
_EXTENT_READER_SRC = (
    "import json, nbd, struct, sys\n"
    "sock = sys.argv[1]\n"
    "areas = json.loads(open(sys.argv[2]).read())\n"
    "h = nbd.NBD()\n"
    "h.connect_uri('nbd+unix://?socket=' + sock)\n"
    "out = sys.stdout.buffer\n"
    # libnbd rejects preads larger than 64 MiB (ERANGE). A single CBT changed
    # region can be far larger, so split every area into <=32 MiB reads (also
    # gentler on VDDK). Each chunk is framed separately with its own offset.
    "CHUNK = 32 * 1024 * 1024\n"
    "for start, length in areas:\n"
    "    off = start\n"
    "    remaining = length\n"
    "    while remaining > 0:\n"
    "        n = CHUNK if remaining > CHUNK else remaining\n"
    "        data = h.pread(n, off)\n"
    "        out.write(struct.pack('>Q', off))\n"
    "        out.write(struct.pack('>Q', len(data)))\n"
    "        out.write(data)\n"
    "        off += n\n"
    "        remaining -= n\n"
    "out.flush()\n"
)


def read_snapshot_extents(
    si,
    vm,
    snap_obj,
    disk,
    areas,
    server_host,
    host_user,
    host_password,
    config=None,
    connection_type=vsphere_context.CONN_AUTO,
):
    """Read (offset, length) areas from a snapshot disk via one open nbdkit VDDK
    session on a UNIX socket (single reader process, no multi-connection)."""
    if not is_available(config):
        raise VddkNotAvailableError(availability_message(config))
    ensure_vddk_runtime_dirs()
    conn_type = vsphere_context.resolve_connection_type(si, connection_type)
    candidates = vsphere_context.vddk_disk_open_candidates(disk, conn_type)
    filtered = [(int(s), int(l)) for s, l in areas if int(l) > 0]
    if not filtered:
        return []

    import json
    import struct

    last_err = None
    for disk_ds_path in candidates:
        pw_path = script_path = areas_path = sock = err_path = None
        proc = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="vddk_pw_") as pw_file:
                pw_file.write(host_password)
                pw_path = pw_file.name
            cmd, _ = vsphere_context.build_nbdkit_vddk_cmd(
                si=si,
                vm=vm,
                snap_obj=snap_obj,
                disk_ds_path=disk_ds_path,
                server_host=server_host,
                user=host_user,
                password_file=pw_path,
                thumbprint=get_server_thumbprint(server_host),
                libdir=get_vddk_libdir(config),
                stored_type=connection_type,
            )
            # Serve on a UNIX socket instead of --run; disk path is the last arg.
            sock = os.path.join(
                tempfile.gettempdir(),
                f"nbdkit_ext_{os.getpid()}_{int(time.time() * 1000)}.sock",
            )
            run_cmd = cmd[:-1] + ["-U", sock, cmd[-1]]
            log_info(
                f"[NBD] CBT extent read via {vsphere_context.connection_label(conn_type)}: "
                f"disk={disk_ds_path} areas={len(filtered)}"
            )
            # nbdkit -v is chatty; send its stderr to a file so it can't block.
            err_fd, err_path = tempfile.mkstemp(prefix="nbdkit_err_")
            proc = subprocess.Popen(run_cmd, stdout=subprocess.DEVNULL, stderr=err_fd)
            os.close(err_fd)
            _wait_for_unix_socket(sock, proc, err_path)

            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as sf:
                sf.write(_EXTENT_READER_SRC)
                script_path = sf.name
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as af:
                json.dump(filtered, af)
                areas_path = af.name

            reader = subprocess.run(
                [_python313(), script_path, sock, areas_path],
                capture_output=True, timeout=7200,
            )
            if reader.returncode != 0:
                err = (reader.stderr or b"").decode("utf-8", errors="replace")[-800:]
                raise RuntimeError(err or f"extent reader exit {reader.returncode}")

            buf = reader.stdout
            extents = []
            pos = 0
            while pos + 16 <= len(buf):
                start, length = struct.unpack_from(">QQ", buf, pos)
                pos += 16
                extents.append((start, buf[pos:pos + length]))
                pos += length
            # A single requested area may be returned as several <=32 MiB
            # chunks (see reader), so the frame count won't match the input
            # count. Validate by total bytes covered instead.
            got_bytes = sum(len(d) for _, d in extents)
            want_bytes = sum(length for _, length in filtered)
            if got_bytes != want_bytes:
                raise RuntimeError(
                    f"extent byte mismatch: expected {want_bytes}, got {got_bytes}"
                )
            return extents
        except Exception as e:
            last_err = e
            log_warn(f"[NBD] CBT extent read failed for {disk_ds_path}: {str(e)[:300]}")
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass
            for path in (pw_path, script_path, areas_path, sock, err_path):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
    raise RuntimeError(last_err or "VDDK extent read failed for all disk candidates")


def read_snapshot_extent(
    si,
    vm,
    snap_obj,
    disk,
    offset,
    length,
    server_host,
    host_user,
    host_password,
    config=None,
    connection_type=vsphere_context.CONN_AUTO,
):
    """Read a byte range from a snapshot-backed disk via NBD/VDDK."""
    areas = read_snapshot_extents(
        si, vm, snap_obj, disk, [(offset, length)],
        server_host, host_user, host_password, config, connection_type,
    )
    # A read >32 MiB is returned as multiple ordered chunks; concatenate them.
    return b"".join(d for _, d in areas)

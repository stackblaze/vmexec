"""
Fast restore of a CBT chain point: thin disks written through VDDK, only data.

The old path rebuilt the whole disk into a temporary file next to the point
(a full-size write into backup storage) and uploaded every byte of it,
zeros included, through the datastore HTTP interface (about 18 MB/s on
Central: 25 minutes for a 20 GB disk holding about 1 GB of data).

Here, for each disk:
  1. create a thin VMDK of the backed-up size (VirtualDiskManager), upload
     the .vmx, register the VM (powered off), as before;
  2. open the new disk read-write through nbdkit + VDDK (no snapshot) on a
     UNIX socket;
  3. nbdcopy the full point's flat file into it with --destination-is-zero:
     blocks that are all zero are skipped (the new thin disk already reads
     as zeros), so only real data crosses the network;
  4. write each incremental's changed extents on top, in chain order.

Anything this path does not handle raises FastRestoreUnsupported before a
change is made, and the caller uses the old path. A failure after the VM
was created removes it again (it is ours, never a pre-existing VM).
"""
import os
import re
import struct
import subprocess
import tempfile
import time
import uuid

from pyVmomi import vim

import vsphere_context
from logger_util import log_info, log_warn

NBD_WRITE_CHUNK = 32 * 1024 * 1024


class FastRestoreUnsupported(Exception):
    """This restore point cannot use the fast path; use the old one."""


# Runs under the system python3 (python3-libnbd), like the extent reader:
# reads framed (offset u64, length u64, data) from stdin and writes them.
_EXTENT_WRITER_SRC = (
    "import nbd, struct, sys\n"
    "h = nbd.NBD()\n"
    "h.connect_uri('nbd+unix://?socket=' + sys.argv[1])\n"
    "src = sys.stdin.buffer\n"
    "n = 0\n"
    "while True:\n"
    "    hdr = src.read(16)\n"
    "    if not hdr:\n"
    "        break\n"
    "    off, length = struct.unpack('>QQ', hdr)\n"
    "    data = src.read(length)\n"
    "    if len(data) != length:\n"
    "        raise SystemExit('truncated extent stream')\n"
    "    h.pwrite(data, off)\n"
    "    n += length\n"
    "h.flush()\n"
    "h.shutdown()\n"
    "print(n)\n"
)

_ADAPTERS = {"lsilogic": "lsiLogic", "buslogic": "busLogic", "ide": "ide"}


def plan(storage, point_rel_dir):
    """What to write, or raise FastRestoreUnsupported. No side effects.

    Returns {"vm_name", "vmx_rel", "disks": [{descriptor, capacity, adapter,
    full_local, deltas_local: [...]}]}.
    """
    from backup_manifest import load_chain, load_manifest, point_rel, walk_chain_to_point

    resolve = getattr(storage, "_full_path", None)
    if resolve is None:
        raise FastRestoreUnsupported("backup storage is not a local path")
    parts = point_rel_dir.strip("/").split("/")
    if len(parts) < 4 or parts[1:3] != ["_chain", "points"]:
        raise FastRestoreUnsupported("not a chain point")
    vm_name, point_id = parts[0], parts[3]
    manifest = load_manifest(storage, vm_name, point_id)
    chain = load_chain(storage, vm_name)
    if not manifest or not chain:
        raise FastRestoreUnsupported("no manifest or chain index")
    path = walk_chain_to_point(chain, point_id)
    if not path or path[0].get("type") not in ("full", "synthetic_full"):
        raise FastRestoreUnsupported("chain does not start at a full")

    manifests = [load_manifest(storage, vm_name, p["id"]) for p in path]
    if any(m is None for m in manifests):
        raise FastRestoreUnsupported("a manifest in the chain is missing")
    vmx = manifest.get("vmx_file")
    if not vmx or not storage.exists(f"{point_rel(vm_name, point_id)}/{vmx}"):
        raise FastRestoreUnsupported("no .vmx in the point")

    disks = []
    for d in manifest["disks"]:
        key = d["device_key"]
        full_m = manifests[0]
        fd = next((x for x in full_m["disks"] if x["device_key"] == key), None)
        if not fd:
            raise FastRestoreUnsupported(f"disk {key} has no full")
        flat = fd.get("storage_flat") or fd["flat_basename"]
        if flat.endswith(".gz"):
            raise FastRestoreUnsupported("compressed full")
        full_local = resolve(f"{point_rel(vm_name, path[0]['id'])}/{flat}")
        if not os.path.isfile(full_local) or os.path.getsize(full_local) != int(d["capacity_bytes"]):
            raise FastRestoreUnsupported(f"full flat for disk {key} missing or wrong size")
        deltas = []
        for p, m in zip(path[1:], manifests[1:]):
            dd = next((x for x in m["disks"] if x["device_key"] == key), None)
            if not dd or dd.get("file_type") != "incremental":
                raise FastRestoreUnsupported(f"disk {key} missing from point {p['id']}")
            dl = resolve(f"{point_rel(vm_name, p['id'])}/{dd.get('delta_file') or fd['flat_basename'] + '.delta.nvbd'}")
            if not os.path.isfile(dl):
                raise FastRestoreUnsupported(f"delta for disk {key} in {p['id']} missing")
            deltas.append(dl)
        desc_local = resolve(f"{point_rel(vm_name, path[0]['id'])}/{fd['descriptor_basename']}")
        adapter = "lsiLogic"
        try:
            m = re.search(r'ddb\.adapterType\s*=\s*"([^"]+)"', open(desc_local, errors="replace").read())
            if m:
                adapter = _ADAPTERS.get(m.group(1).lower(), "lsiLogic")
        except OSError:
            pass
        disks.append({
            "descriptor": d["descriptor_basename"],
            "capacity": int(d["capacity_bytes"]),
            "adapter": adapter,
            "full_local": full_local,
            "deltas_local": deltas,
        })
    return {"vm_name": vm_name, "vmx_rel": f"{point_rel(vm_name, point_id)}/{vmx}", "vmx": vmx, "disks": disks}


def _wait_task(task, what, timeout=600):
    end = time.time() + timeout
    while task.info.state not in (vim.TaskInfo.State.success, vim.TaskInfo.State.error):
        if time.time() > end:
            raise RuntimeError(f"{what}: timed out")
        time.sleep(1)
    if task.info.state == vim.TaskInfo.State.error:
        raise RuntimeError(f"{what}: {task.info.error.msg if task.info.error else 'failed'}")
    return task.info.result


def _datacenter_for(content, ds_name):
    for dc in content.rootFolder.childEntity:
        if isinstance(dc, vim.Datacenter) and any(ds.name == ds_name for ds in dc.datastore):
            return dc
    raise RuntimeError(f"no datacenter holds datastore {ds_name}")


def _start_nbdkit(si, vm, disk_ds_path, server_host, user, pw_path, config):
    """nbdkit VDDK, read-write, no snapshot, on a UNIX socket. Returns (proc, sock, err_path)."""
    from vddk_transport import _wait_for_unix_socket, get_server_thumbprint, get_vddk_libdir, ensure_vddk_runtime_dirs
    ensure_vddk_runtime_dirs()
    sock = os.path.join(tempfile.gettempdir(), f"nbdkit_restore_{os.getpid()}_{uuid.uuid4().hex[:12]}.sock")
    # -f: stay in the foreground. Without it nbdkit forks, the server keeps
    # running after we "stop" the parent, and holds the disk open.
    cmd = [
        "nbdkit", "-f", "-v", "vddk",
        f"libdir={get_vddk_libdir(config)}",
        f"server={server_host}",
        f"user={user}",
        f"password=+{pw_path}",
        f"thumbprint={get_server_thumbprint(server_host)}",
        f"vm=moref={vsphere_context.get_vm_moref(vm)}",
        "transports=nbdssl:nbd",
    ]
    if vsphere_context.resolve_connection_type(si, vsphere_context.CONN_AUTO) == vsphere_context.CONN_VCENTER:
        cookie = vsphere_context.get_session_cookie(si)
        if cookie:
            cmd.append(f"cookie={cookie}")
    cmd += ["-U", sock, disk_ds_path]
    err_fd, err_path = tempfile.mkstemp(prefix="nbdkit_restore_err_")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_fd)
    os.close(err_fd)
    _wait_for_unix_socket(sock, proc, err_path)
    return proc, sock, err_path


def _stop(proc):
    """Stop nbdkit; it must be gone before the VM is touched again."""
    if not proc or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _nbdcopy_full(full_local, sock, progress, base, span, is_cancelled):
    """Copy the full flat into the new (all-zero) disk, skipping zero blocks."""
    r, w = os.pipe()
    proc = subprocess.Popen(
        ["nbdcopy", "--destination-is-zero", f"--progress={w}", full_local, f"nbd+unix:///?socket={sock}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, pass_fds=(w,),
    )
    os.close(w)
    buf = b""
    with os.fdopen(r, "rb", buffering=0) as pr:
        while True:
            if is_cancelled and is_cancelled():
                proc.kill()
                raise RuntimeError("Restore cancelled by user")
            chunk = pr.read(64)
            if not chunk:
                break
            buf += chunk
            # nbdcopy --progress=FD writes "pct/100\n" lines
            *lines, buf = buf.split(b"\n")
            for line in lines:
                m = re.match(rb"\s*(\d+)/100", line)
                if m and progress:
                    progress(base + span * int(m.group(1)) // 100)
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"nbdcopy failed: {(err or b'').decode(errors='replace')[-400:]}")


def _write_deltas(delta_paths, sock):
    from delta_store import read_delta_file
    from vddk_transport import _python313
    if not delta_paths:
        return 0
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as sf:
        sf.write(_EXTENT_WRITER_SRC)
        script = sf.name
    try:
        proc = subprocess.Popen([_python313(), script, sock], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for path in delta_paths:  # chain order: later changes win
                for off, data in read_delta_file(path):
                    for i in range(0, len(data), NBD_WRITE_CHUNK):
                        piece = data[i:i + NBD_WRITE_CHUNK]
                        proc.stdin.write(struct.pack(">QQ", off + i, len(piece)))
                        proc.stdin.write(piece)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
        # communicate() would flush the stdin we just closed: read directly.
        out = proc.stdout.read()
        err = proc.stderr.read()
        proc.wait(timeout=7200)
        if proc.returncode != 0:
            raise RuntimeError(f"extent writer failed: {(err or b'').decode(errors='replace')[-400:]}")
        return int((out or b"0").strip() or 0)
    finally:
        os.unlink(script)


def restore_point(si, storage, point_rel_dir, target_ds, target_name, server_host, user, password,
                  config=None, progress_callback=None, is_cancelled_func=None, upload_file=None):
    """Restore one chain point as a new VM. Returns (ok, message).

    Raises FastRestoreUnsupported (before changing anything) when this point
    needs the old path. upload_file(si, ds, dest_rel, storage, src_rel, dc_path)
    uploads one small file (the .vmx).
    """
    from vddk_transport import is_available
    if not is_available(config):
        raise FastRestoreUnsupported("VDDK not available")
    p = plan(storage, point_rel_dir)
    progress = progress_callback or (lambda _p: None)
    content = si.RetrieveContent()
    dc = _datacenter_for(content, target_ds)
    folder = f"[{target_ds}] {target_name}"
    created_vm = None
    pw_path = None
    t0 = time.time()
    try:
        log_info(f"[RESTORE-FAST] {p['vm_name']} -> {target_name} on {target_ds}: {len(p['disks'])} disk(s), thin, VDDK")
        content.fileManager.MakeDirectory(name=folder, datacenter=dc, createParentDirectories=True)
        vdm = content.virtualDiskManager
        for d in p["disks"]:
            spec = vim.VirtualDiskManager.FileBackedVirtualDiskSpec(
                diskType="thin", adapterType=d["adapter"], capacityKb=d["capacity"] // 1024)
            _wait_task(vdm.CreateVirtualDisk_Task(name=f"{folder}/{d['descriptor']}", datacenter=dc, spec=spec),
                       f"create disk {d['descriptor']}")
        progress(5)
        upload_file(si, target_ds, f"{target_name}/{p['vmx']}", storage, p["vmx_rel"], dc.name)
        from esxi_handler import register_vm
        ok, msg = register_vm(si, target_ds, f"{target_name}/{p['vmx']}", target_name)
        if not ok:
            raise RuntimeError(f"register: {msg}")
        created_vm = vsphere_context.find_vm_by_name(si, target_name)
        if created_vm is None:
            raise RuntimeError("registered VM not found")
        progress(8)

        with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="vddk_pw_") as f:
            f.write(password)
            pw_path = f.name
        n = len(p["disks"])
        for i, d in enumerate(p["disks"]):
            base, span = 8 + 90 * i // n, 90 // n
            proc = sock = err = None
            try:
                proc, sock, err = _start_nbdkit(si, created_vm, f"{folder}/{d['descriptor']}", server_host, user,
                                                pw_path, config)
                _nbdcopy_full(d["full_local"], sock, progress, base, span * 9 // 10, is_cancelled_func)
                written = _write_deltas(d["deltas_local"], sock)
                log_info(f"[RESTORE-FAST] {d['descriptor']}: full copied (zeros skipped), "
                         f"{len(d['deltas_local'])} incremental(s), {written} changed bytes")
            finally:
                _stop(proc)
                for path in (sock, err):
                    if path and os.path.exists(path):
                        os.unlink(path)
            progress(base + span)
        progress(100)
        return True, f"VM {target_name} restored and registered (fast path, {time.time() - t0:.0f} s)."
    except Exception:
        if created_vm is not None:
            try:
                _wait_task(created_vm.Destroy_Task(), "remove partial VM")
            except Exception as e:  # noqa: BLE001
                log_warn(f"[RESTORE-FAST] could not remove partial VM {target_name}: {e}")
        else:
            try:
                _wait_task(content.fileManager.DeleteDatastoreFile_Task(name=folder, datacenter=dc), "remove folder")
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        if pw_path and os.path.exists(pw_path):
            os.unlink(pw_path)

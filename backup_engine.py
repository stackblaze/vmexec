"""
backup_engine.py — Snapshot + Datastore HTTP Backup Engine (v2)
Uses the same approach as ghettoVCB: snapshot → download VMDKs via
ESXi's built-in HTTP file server → remove snapshot.
No ExportVm, no HttpNfcLease, no zombie tasks.
"""

import os
import re
import time
import datetime
import shutil
import requests
from pyVmomi import vim
from urllib.parse import quote as url_quote
from logger_util import log_info, log_warn, log_error
import vsphere_context

# Disable SSL warnings for ESXi self-signed certs
requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)

CHUNK_SIZE = 1024 * 1024  # 1MB chunks for download

# Infrastructure VMs skipped when config.exclude_infra_vms is True
INFRA_VM_PATTERNS = [
    re.compile(r"(?i)vcenter"),
    re.compile(r"(?i)\bvcls\b"),
    re.compile(r"(?i)vsphere cluster service"),
    re.compile(r"(?i)photon platform"),
]


# ---------------------------------------------------------------------------
#  Helper: Get VM object by name
# ---------------------------------------------------------------------------
def _get_vm(si, vm_name):
    """Finds a VM on standalone ESXi or vCenter."""
    return vsphere_context.find_vm_by_name(si, vm_name)


# ---------------------------------------------------------------------------
#  Helper: Parse "[datastore] path/to/file.vmdk" → (datastore, path)
# ---------------------------------------------------------------------------
def _parse_datastore_path(ds_path):
    """Parses a VMware datastore path like '[datastore1] vm/disk.vmdk'
    into (datastore_name, relative_path)."""
    match = re.match(r'\[([^\]]+)\]\s*(.*)', ds_path)
    if match:
        return match.group(1), match.group(2)
    return None, ds_path


# ---------------------------------------------------------------------------
#  Helper: Build auth cookies from SOAP session
# ---------------------------------------------------------------------------
def _get_session_cookies(si):
    """Extracts the session cookie from the pyVmomi connection."""
    cookie_str = si._stub.cookie
    if not cookie_str:
        return {}
    parts = cookie_str.split(';')
    if '=' in parts[0]:
        name, value = parts[0].split('=', 1)
        return {name.strip(): value.strip().strip('"')}
    return {}


# ---------------------------------------------------------------------------
#  Helper: Get ESXi host IP from the service instance
# ---------------------------------------------------------------------------
def _get_host_ip(si):
    """Extracts the ESXi host IP from the SOAP stub."""
    try:
        from urllib.parse import urlparse
        url = si._stub.soapStub.safeGetWsdlUrl()
        return urlparse(url).hostname
    except Exception:
        pass
    try:
        return si._stub.host
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  Download VMDK via Datastore HTTP
# ---------------------------------------------------------------------------
def _download_file_http(si, datastore_name, file_path, storage, dest_rel_path, progress_callback=None,
                         progress_base=0, progress_total=100, speed_callback=None, is_cancelled_func=None,
                         vm=None, dc_path=None, connection_type=vsphere_context.CONN_AUTO):
    """
    Downloads a file from ESXi/vCenter HTTP folder API via StorageProvider.
    """
    host_ip = _get_host_ip(si)
    if not host_ip:
        raise Exception("Cannot determine host IP for HTTP folder access")

    if not dc_path:
        dc_path = vsphere_context.resolve_dc_path(si, vm=vm, stored_type=connection_type)

    cookies = _get_session_cookies(si)

    # URL-encode the file path (but not the slashes)
    encoded_path = '/'.join(url_quote(p, safe='') for p in file_path.split('/'))

    url = (f"https://{host_ip}/folder/{encoded_path}"
           f"?dcPath={url_quote(dc_path, safe='')}&dsName={url_quote(datastore_name, safe='')}")

    log_info(f"[DOWNLOAD] {file_path} from [{datastore_name}] to {dest_rel_path}")

    resp = requests.get(url, stream=True, cookies=cookies, verify=False, timeout=7200)

    if resp.status_code != 200:
        body = resp.text[:500] if resp.text else '(empty)'
        raise Exception(f"HTTP {resp.status_code} downloading {file_path}: {body}")

    # Get total size from Content-Length if available
    total_size = int(resp.headers.get('Content-Length', 0))
    bytes_written = 0
    speed_window_bytes = 0
    speed_window_start = time.time()

    storage.makedirs(os.path.dirname(dest_rel_path))

    # We use a context manager for the storage writer
    with storage.open_write(dest_rel_path) as f:
        # Optimization for local files (sparse support)
        is_local = hasattr(storage, 'base_path')
        zero_chunk = b'\x00' * CHUNK_SIZE if is_local else None

        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if is_cancelled_func and is_cancelled_func():
                raise Exception("Backup cancelled by user")
            if chunk:
                # Thin provisioning stream optimization (only for local files with seek support)
                if is_local and len(chunk) == CHUNK_SIZE and chunk == zero_chunk:
                    if hasattr(f, 'seek'):
                        f.seek(CHUNK_SIZE, os.SEEK_CUR)
                        bytes_written += CHUNK_SIZE
                    else:
                        f.write(chunk)
                        bytes_written += len(chunk)
                elif is_local and not chunk.strip(b'\x00'):
                    if hasattr(f, 'seek'):
                        f.seek(len(chunk), os.SEEK_CUR)
                        bytes_written += len(chunk)
                    else:
                        f.write(chunk)
                        bytes_written += len(chunk)
                else:
                    f.write(chunk)
                    bytes_written += len(chunk)
                    
                # Update progress and speed every chunk
                now = time.time()
                speed_window_bytes += len(chunk)
                elapsed_window = now - speed_window_start
                if elapsed_window >= 2.0:  # report speed every 2s
                    speed_mbps = (speed_window_bytes / (1024 * 1024)) / elapsed_window
                    if speed_callback:
                        speed_callback(round(speed_mbps, 1))
                    speed_window_bytes = 0
                    speed_window_start = now

                if total_size > 0 and progress_callback:
                    file_pct = (bytes_written * 100) / total_size
                    overall_pct = progress_base + (file_pct * progress_total / 100)
                    progress_callback(min(int(overall_pct), 99))
                    
        # Force file boundaries if supported
        if is_local and bytes_written > 0 and hasattr(f, 'truncate'):
            try:
                f.truncate(bytes_written)
            except Exception as e:
                log_warn(f"[DOWNLOAD] Warning: Truncate skipped: {e}")

    size_mb = bytes_written / (1024 * 1024)
    log_info(f"[DOWNLOAD] Complete: {size_mb:.1f} MB processed for {os.path.basename(dest_rel_path)}")

    return bytes_written


def _download_file_http_range(si, datastore_name, file_path, start, length, vm=None,
                              dc_path=None, connection_type=vsphere_context.CONN_AUTO):
    """
    Download a byte range from ESXi/vCenter HTTP folder API.
    Returns raw bytes (length may be shorter if EOF).
    """
    host_ip = _get_host_ip(si)
    if not host_ip:
        raise Exception("Cannot determine host IP for HTTP folder access")

    if not dc_path:
        dc_path = vsphere_context.resolve_dc_path(si, vm=vm, stored_type=connection_type)

    cookies = _get_session_cookies(si)
    encoded_path = '/'.join(url_quote(p, safe='') for p in file_path.split('/'))
    url = (f"https://{host_ip}/folder/{encoded_path}"
           f"?dcPath={url_quote(dc_path, safe='')}&dsName={url_quote(datastore_name, safe='')}")

    end = start + length - 1
    headers = {"Range": f"bytes={start}-{end}"}
    resp = requests.get(url, headers=headers, cookies=cookies, verify=False, timeout=7200)

    if resp.status_code not in (200, 206):
        body = resp.text[:500] if resp.text else '(empty)'
        raise Exception(f"HTTP {resp.status_code} range download {file_path}@{start}: {body}")

    return resp.content


# ---------------------------------------------------------------------------
#  Preflight: Disconnect Removable Devices
# ---------------------------------------------------------------------------
def _handle_consolidation(si, vm_name, timeout_mins=15):
    """Checks if consolidation is needed and triggers it."""
    vm = _get_vm(si, vm_name)
    if not vm:
        return True

    if not getattr(vm.runtime, 'consolidationNeeded', False):
        return True

    log_info(f"[PREFLIGHT] VM {vm_name} needs consolidation. Triggering...")
    try:
        task = vm.ConsolidateVMDisks_Task()
        start = time.time()
        while task.info.state not in [vim.TaskInfo.State.success,
                                      vim.TaskInfo.State.error]:
            if (time.time() - start) > (timeout_mins * 60):
                log_error(f"[PREFLIGHT] Consolidation timeout ({timeout_mins}m) for {vm_name}")
                return False
            time.sleep(5)

        if task.info.state == vim.TaskInfo.State.success:
            log_info(f"[PREFLIGHT] Consolidation completed for {vm_name}")
            return True
        else:
            log_error(f"[PREFLIGHT] Consolidation failed: {task.info.error}")
            return False
    except Exception as e:
        log_error(f"[PREFLIGHT] Consolidation error: {e}")
        return False


# ---------------------------------------------------------------------------
#  Orphaned backup snapshot cleanup (VMBACKUP_TEMP_*)
# ---------------------------------------------------------------------------
VMBACKUP_SNAP_PREFIX = "VMBACKUP_TEMP_"


def _find_backup_snapshot_nodes(tree):
    """Return (name, snapshot_mo) pairs for all VMBACKUP_TEMP_* nodes in the tree."""
    out = []
    for node in tree or []:
        if node.name.startswith(VMBACKUP_SNAP_PREFIX):
            out.append((node.name, node.snapshot))
        out.extend(_find_backup_snapshot_nodes(node.childSnapshotList))
    return out


def _backup_snapshot_age_secs(name):
    """Age in seconds from VMBACKUP_TEMP_YYYYMMDD_HHMMSS name, or None if not our prefix."""
    if not name.startswith(VMBACKUP_SNAP_PREFIX):
        return None
    suffix = name[len(VMBACKUP_SNAP_PREFIX):]
    try:
        created = datetime.datetime.strptime(suffix, "%Y%m%d_%H%M%S")
        return (datetime.datetime.now() - created).total_seconds()
    except ValueError:
        return float("inf")


def remove_orphaned_backup_snapshots(
    si,
    vm_name,
    timeout_mins=10,
    min_age_secs=0,
    log_prefix="[SNAPSHOT]",
):
    """
    Remove VMBACKUP_TEMP_* snapshots left by interrupted backups.

    min_age_secs: only remove snapshots at least this old (safety for in-flight jobs).
    Returns the number of snapshots removed.
    """
    vm = _get_vm(si, vm_name)
    if not vm or not vm.snapshot:
        return 0

    candidates = _find_backup_snapshot_nodes(vm.snapshot.rootSnapshotList)
    removed = 0
    for name, snap in candidates:
        age = _backup_snapshot_age_secs(name)
        if age is not None and age < min_age_secs:
            continue
        log_info(f"{log_prefix} Removing orphaned snapshot {name} for {vm_name}...")
        task = snap.RemoveSnapshot_Task(removeChildren=False)
        start = time.time()
        while task.info.state not in [vim.TaskInfo.State.success,
                                      vim.TaskInfo.State.error]:
            if (time.time() - start) > (timeout_mins * 60):
                log_error(f"{log_prefix} Snapshot removal timeout for {vm_name} ({name})")
                return removed
            time.sleep(2)
        if task.info.state == vim.TaskInfo.State.error:
            log_error(f"{log_prefix} Snapshot removal failed for {name}: {task.info.error}")
            continue
        log_info(f"{log_prefix} Removed orphaned snapshot {name} for {vm_name}")
        removed += 1
    return removed


def cleanup_orphaned_snapshots_all(skip_vm_ids=None, min_age_secs=120):
    """
    Scan all registered VMs and remove orphaned VMBACKUP_TEMP_* snapshots.
    skip_vm_ids: VM IDs with an active backup (never touch their snapshots).
    Returns total snapshots removed.
    """
    from models import SessionLocal, VM
    import esxi_handler

    skip_vm_ids = set(skip_vm_ids or ())
    db = SessionLocal()
    host_sessions = {}
    total_removed = 0
    try:
        vms = db.query(VM).filter(VM.is_selected == True).all()
        for vm in vms:
            if vm.id in skip_vm_ids or not vm.esxi_host:
                continue
            host = vm.esxi_host
            if host.id not in host_sessions:
                si = esxi_handler.connect_esxi(host.host_ip, host.username, host.password)
                if not si:
                    log_warn(f"[SNAPSHOT] Orphan sweep: cannot connect to host {host.name}")
                    continue
                host_sessions[host.id] = si
            removed = remove_orphaned_backup_snapshots(
                host_sessions[host.id],
                vm.vm_name,
                timeout_mins=30,
                min_age_secs=min_age_secs,
            )
            total_removed += removed
    finally:
        for si in host_sessions.values():
            try:
                esxi_handler.Disconnect(si)
            except Exception:
                pass
        db.close()
    return total_removed


def _remove_stale_snapshots(si, vm_name, timeout_mins=10):
    """Preflight: remove all orphaned backup snapshots before starting a new run."""
    removed = remove_orphaned_backup_snapshots(
        si, vm_name, timeout_mins=timeout_mins, min_age_secs=0, log_prefix="[PREFLIGHT]"
    )
    if removed:
        log_info(f"[PREFLIGHT] Removed {removed} orphaned snapshot(s) for {vm_name}")
    return True


# ---------------------------------------------------------------------------
#  Preflight: Cleanup Stale Temp Directories
# ---------------------------------------------------------------------------
def _cleanup_stale_temp_dirs(si, datastore_name, hours=12):
    """
    Scans a datastore for abandoned _backup_temp_ directories and removes them.
    Only removes folders older than 'hours' to avoid interfering with running jobs.
    """
    try:
        content = si.RetrieveContent()
        datacenter = content.rootFolder.childEntity[0]
        
        # Find datastore object
        ds = next((d for d in datacenter.datastore if d.name == datastore_name), None)
        if not ds: return

        browser = ds.browser
        search_spec = vim.host.DatastoreBrowser.SearchSpec()
        search_spec.matchPattern = ["_backup_temp_*"]
        
        task = browser.SearchDatastore_Task(datastorePath=f"[{datastore_name}]", searchSpec=search_spec)
        
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            time.sleep(1)
            
        if task.info.state == vim.TaskInfo.State.success:
            results = task.info.result
            if results and hasattr(results, 'file'):
                fm = content.fileManager
                for f in results.file:
                    # We can't easily check folder modification time without more SearchSpec details
                    # To be safe, we just log and attempt deletion of any _backup_temp_ folder
                    # that matches our internal naming scheme
                    folder_path = f"[{datastore_name}] {f.path}"
                    log_info(f"[CLEANUP] Found potentially stale temp folder: {folder_path}. Attempting removal...")
                    try:
                        fm.DeleteDatastoreFile_Task(name=folder_path, datacenter=datacenter)
                    except: pass
    except Exception as e:
        log_warn(f"[CLEANUP] Error during temp folder scan on {datastore_name}: {e}")


def _get_datastore_summary(si, ds_name):
    """Returns capacity/free stats for a named datastore on the host."""
    from pyVmomi import vim
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.Datastore], True)
    try:
        for ds in container.view:
            if ds.summary.name == ds_name:
                cap = ds.summary.capacity or 0
                free = ds.summary.freeSpace or 0
                cap_gb = cap / (1024**3)
                free_gb = free / (1024**3)
                free_pct = (free / cap * 100) if cap else 0
                return {
                    "name": ds_name,
                    "capacity_gb": round(cap_gb, 1),
                    "free_gb": round(free_gb, 1),
                    "free_pct": round(free_pct, 1),
                }
    finally:
        container.Destroy()
    return None


def matches_infra_vm_pattern(vm_name):
    """Return True if VM name matches built-in infrastructure patterns."""
    return any(p.search(vm_name or "") for p in INFRA_VM_PATTERNS)


def _is_infra_vm(vm_name, config):
    """Return True if VM matches built-in infrastructure patterns and exclusion is enabled."""
    if config is None or not getattr(config, "exclude_infra_vms", True):
        return False
    return matches_infra_vm_pattern(vm_name)


def _effective_datastore_multiplier(config, power_state):
    """Live legacy path uses temp copy (2×); NBD path uses snapshot only (1×)."""
    multiplier = getattr(config, "datastore_est_multiplier", None) if config else None
    if multiplier is None:
        multiplier = 2.0
    if power_state == "poweredOff":
        return 1.0
    transport = getattr(config, "backup_transport", "nbd") if config else "nbd"
    if transport == "nbd":
        return 1.0
    return float(multiplier)


def _check_repo_capacity_for_vm(storage, si, vm_name, config):
    """Repo guard with VM-size estimate when ESXi connection is available."""
    if storage is None:
        return True, "No storage provider"

    min_gb = getattr(config, "repo_min_free_gb", None) if config else None
    if min_gb is None:
        min_gb = 50

    base = storage.get_base_path()
    if base.startswith("s3://"):
        return True, "S3 repo space check skipped"

    path = getattr(storage, "base_path", None) or base
    if not path or not os.path.exists(path):
        return False, f"[SKIP] Backup repository path not accessible: {path}"

    try:
        stat = shutil.disk_usage(path)
    except OSError as e:
        return False, f"[SKIP] Cannot read backup repository disk usage: {e}"

    free_gb = stat.free / (1024 ** 3)
    vm = _get_vm(si, vm_name) if si else None
    disk_gb = _vm_disk_gb(vm) if vm else 0
    need_gb = max(float(min_gb), disk_gb * 1.1) if disk_gb else float(min_gb)

    if free_gb < need_gb:
        return False, (
            f"[SKIP] Backup repository has {free_gb:.0f} GB free "
            f"({path}) — need ~{need_gb:.0f} GB for {vm_name}"
        )
    return True, "Repository capacity OK"


def _vm_disk_gb(vm):
    if getattr(vm, "storage_gb", None) and vm.storage_gb > 0:
        return float(vm.storage_gb)
    total = 0.0
    if hasattr(vm, "layoutEx") and vm.layoutEx and vm.layoutEx.file:
        for f in vm.layoutEx.file:
            if f.type == "diskDescriptor" and getattr(f, "size", None):
                total += (f.size or 0) / (1024**3)
    return max(total, 1.0)


def _check_datastore_capacity(si, vm_name, config):
    """
    Verify source datastore(s) have enough free space for backup.
    Returns (ok: bool, message: str). Prefix [SKIP] on message when backup should be skipped.
    """
    vm = _get_vm(si, vm_name)
    if not vm:
        return False, "VM not found"

    min_pct = getattr(config, "datastore_min_free_pct", None)
    if min_pct is None:
        min_pct = 15
    headroom = getattr(config, "datastore_headroom_gb", None)
    if headroom is None:
        headroom = 10

    power_state = getattr(vm.runtime, "powerState", "poweredOn")
    multiplier = _effective_datastore_multiplier(config, power_state)

    disk_gb = _vm_disk_gb(vm)
    need_gb = disk_gb * float(multiplier) + float(headroom)

    ds_names = set()
    if vm.config and vm.config.files and vm.config.files.vmPathName:
        name, _ = _parse_datastore_path(vm.config.files.vmPathName)
        if name:
            ds_names.add(name)
    if hasattr(vm, "layoutEx") and vm.layoutEx and vm.layoutEx.file:
        for f in vm.layoutEx.file:
            if f.type == "diskDescriptor":
                name, _ = _parse_datastore_path(f.name)
                if name:
                    ds_names.add(name)

    if not ds_names:
        return True, "No datastores to check"

    errors = []
    for ds_name in sorted(ds_names):
        summary = _get_datastore_summary(si, ds_name)
        if not summary:
            errors.append(
                f"Datastore '{ds_name}' not found — cannot verify free space (fail closed)"
            )
            continue
        if summary["free_pct"] < min_pct:
            errors.append(
                f"Datastore '{ds_name}' {summary['free_pct']}% free "
                f"({summary['free_gb']} GB of {summary['capacity_gb']} GB) — minimum {min_pct}% required"
            )
        if summary["free_gb"] < need_gb:
            errors.append(
                f"Datastore '{ds_name}' has {summary['free_gb']} GB free but ~{need_gb:.0f} GB "
                f"estimated need for {disk_gb:.0f} GB VM (×{multiplier} + {headroom} GB headroom)"
            )

    if errors:
        return False, "[SKIP] " + "; ".join(errors)
    return True, "Datastore capacity OK"


def _find_snapshot_by_name(vm, snap_name):
    """Find snapshot managed object by name (searches full snapshot tree)."""
    if not vm or not vm.snapshot:
        return None

    def walk(tree):
        for s in tree:
            if s.name == snap_name:
                return s.snapshot
            found = walk(s.childSnapshotList)
            if found:
                return found
        return None

    return walk(vm.snapshot.rootSnapshotList)


def _collect_vm_disk_layout(vm):
    """Return disk descriptors, vmx paths, and power state for a VM."""
    power_state = getattr(vm.runtime, "powerState", "poweredOn")
    is_off = power_state == "poweredOff"

    disk_descriptors = []
    seen = set()
    for dev in getattr(vm.config.hardware, "device", []) or []:
        if not isinstance(dev, vim.vm.device.VirtualDisk):
            continue
        backing = dev.backing
        fn = getattr(backing, "fileName", None) if backing else None
        if not fn:
            continue
        ds_name, rel_path = _parse_datastore_path(fn)
        if not ds_name or fn in seen:
            continue
        seen.add(fn)
        disk_descriptors.append({
            "ds_name": ds_name,
            "ds_path": fn,
            "rel_path": rel_path,
        })

    if not disk_descriptors and hasattr(vm, "layoutEx") and vm.layoutEx and vm.layoutEx.file:
        for f in vm.layoutEx.file:
            if f.type != "diskDescriptor" or f.name in seen:
                continue
            ds_name, rel_path = _parse_datastore_path(f.name)
            if ds_name:
                seen.add(f.name)
                disk_descriptors.append({
                    "ds_name": ds_name,
                    "ds_path": f.name,
                    "rel_path": rel_path,
                })

    vmx_ds_name = None
    vmx_rel_path = None
    if vm.config and vm.config.files and vm.config.files.vmPathName:
        vmx_ds_name, vmx_rel_path = _parse_datastore_path(vm.config.files.vmPathName)

    return is_off, disk_descriptors, vmx_ds_name, vmx_rel_path

# ===========================================================================
#  MAIN: Preflight Check
# ===========================================================================
def preflight_check(si, vm_name, timeout_mins=15, config=None, storage=None, **kwargs):
    """
    Runs a comprehensive pre-backup checklist.
    Returns (success: bool, message: str)
    """
    if _is_infra_vm(vm_name, config):
        return False, (
            "[SKIP] Infrastructure VM excluded from backup "
            f"({vm_name}). Disable exclude_infra_vms in settings to override."
        )

    # Attempt cleanup on the VM's datastore(s)
    vm = _get_vm(si, vm_name)
    if vm and vm.config and vm.config.files:
        ds_name, _ = _parse_datastore_path(vm.config.files.vmPathName)
        if ds_name:
            _cleanup_stale_temp_dirs(si, ds_name)

    steps = [
        ("Remove stale snapshots", lambda: _remove_stale_snapshots(si, vm_name, timeout_mins)),
        # No "disconnect removable devices" step: it rewrote the VM's CD-ROM /
        # floppy (ISO detached, not connected at power on) before every
        # backup, and a CD-ROM the guest had locked raised a vCenter question
        # that froze the VM until someone answered it (vault-us-central-1,
        # 2026-11-03). Snapshot backups do not need it; VMExec does not change
        # a VM's configuration to back it up.
        ("Handle consolidation", lambda: _handle_consolidation(si, vm_name, timeout_mins)),
    ]
    if config is not None:
        steps.insert(0, ("Check datastore free space", lambda: _check_datastore_capacity(si, vm_name, config)))
    if storage is not None:
        steps.insert(0, ("Check repository free space", lambda: _check_repo_capacity_for_vm(storage, si, vm_name, config)))

    for name, func in steps:
        log_info(f"[PREFLIGHT] Step: {name}...")
        try:
            result = func()
            if isinstance(result, tuple):
                ok, msg = result
                if not ok:
                    return False, msg
            elif not result:
                return False, f"Preflight failed at: {name}"
        except Exception as e:
            return False, f"Preflight error at {name}: {e}"

    return True, "All preflight checks passed"


# ===========================================================================
#  MAIN: Create Snapshot
# ===========================================================================
def _create_backup_snapshot(si, vm_name, timeout_mins=10, quiesce=False):
    """Creates a snapshot for backup. Returns (snapshot object, name) or (None, error)."""
    vm = _get_vm(si, vm_name)
    if not vm:
        return None, "VM not found"

    snap_name = f"VMBACKUP_TEMP_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    kind = "quiesced" if quiesce else "crash-consistent"
    log_info(f"[SNAPSHOT] Creating {snap_name} for {vm_name} ({kind})...")

    try:
        task = vm.CreateSnapshot_Task(
            name=snap_name,
            description="Temporary snapshot for automated backup",
            memory=False,
            quiesce=quiesce,
        )

        start = time.time()
        while task.info.state not in [vim.TaskInfo.State.success,
                                      vim.TaskInfo.State.error]:
            if (time.time() - start) > (timeout_mins * 60):
                return None, f"Snapshot creation timeout ({timeout_mins}m)"
            time.sleep(2)

        if task.info.state == vim.TaskInfo.State.success:
            log_info(f"[SNAPSHOT] Created successfully: {snap_name}")
            snap_obj = getattr(task.info, "result", None)
            if snap_obj:
                return snap_obj, snap_name
            vm = _get_vm(si, vm_name)
            snap_obj = _find_snapshot_by_name(vm, snap_name)
            if snap_obj:
                return snap_obj, snap_name
            return None, f"Snapshot {snap_name} created but object not found"
        else:
            return None, f"Snapshot failed: {task.info.error}"

    except Exception as e:
        return None, f"Snapshot error: {e}"


def _create_live_backup_snapshot(si, vm_name, timeout_mins=10):
    """Live backup snapshot; quiesce when VMware Tools is running."""
    vm = _get_vm(si, vm_name)
    quiesce = False
    if vm and getattr(vm, "guest", None):
        if getattr(vm.guest, "toolsRunningStatus", None) == "guestToolsRunning":
            quiesce = True
    return _create_backup_snapshot(si, vm_name, timeout_mins=timeout_mins, quiesce=quiesce)


# ===========================================================================
#  MAIN: Remove Backup Snapshot
# ===========================================================================
def _remove_backup_snapshot(si, vm_name, snap_name, timeout_mins=60):
    """Removes the backup snapshot by name."""
    vm = _get_vm(si, vm_name)
    if not vm or not vm.snapshot:
        return True

    def find_snap(tree, name):
        for s in tree:
            if s.name == name:
                return s.snapshot
            found = find_snap(s.childSnapshotList, name)
            if found:
                return found
        return None

    snap = find_snap(vm.snapshot.rootSnapshotList, snap_name)
    if not snap:
        log_info(f"[SNAPSHOT] Snapshot {snap_name} not found (already removed?)")
        return True

    log_info(f"[SNAPSHOT] Removing {snap_name} for {vm_name}...")
    task = snap.RemoveSnapshot_Task(removeChildren=False)
    start = time.time()
    while task.info.state not in [vim.TaskInfo.State.success,
                                  vim.TaskInfo.State.error]:
        if (time.time() - start) > (timeout_mins * 60):
            log_error(f"[SNAPSHOT] Removal timeout ({timeout_mins}m)")
            return False
        time.sleep(3)

    if task.info.state == vim.TaskInfo.State.success:
        log_info(f"[SNAPSHOT] Removed successfully: {snap_name}")
        return True
    else:
        log_error(f"[SNAPSHOT] Removal failed: {task.info.error}")
        return False


# ---------------------------------------------------------------------------
#  Upload file to ESXi via Datastore HTTP
# ---------------------------------------------------------------------------
def _upload_file_http(si, datastore_name, dest_rel_path, storage, source_rel_path, is_cancelled_func=None, progress_callback=None, base_pct=0, max_pct=100, dc_path="ha-datacenter"):
    """
    Uploads a file to ESXi's HTTP file server from StorageProvider.
    """
    host_ip = _get_host_ip(si)
    cookies = _get_session_cookies(si)

    encoded_path = '/'.join(url_quote(p, safe='') for p in dest_rel_path.split('/'))
    url = (f"https://{host_ip}/folder/{encoded_path}"
           f"?dcPath={url_quote(dc_path, safe='')}&dsName={url_quote(datastore_name, safe='')}")

    log_info(f"[UPLOAD] {source_rel_path} to [{datastore_name}] {dest_rel_path}")

    with storage.open_read(source_rel_path) as f:
        f_size = storage.get_size(source_rel_path)
        
        class CancelableStreamWrapper:
            def __init__(self, stream, size, is_cancelled_func):
                self._stream = stream
                self._size = size
                self._is_cancelled = is_cancelled_func
                self._read_so_far = 0
                self._last_pct = -1

            def read(self, size=-1):
                if self._is_cancelled and self._is_cancelled():
                    raise Exception("CancellationRequested")
                
                chunk = self._stream.read(size)
                if chunk and self._size > 0 and progress_callback:
                    self._read_so_far += len(chunk)
                    file_pct = self._read_so_far / self._size
                    overall_pct = int(base_pct + (max_pct - base_pct) * file_pct)
                    if overall_pct > self._last_pct:
                        progress_callback(overall_pct)
                        self._last_pct = overall_pct
                
                return chunk

            def __len__(self):
                return self._size
                
        wrapped_stream = CancelableStreamWrapper(f, f_size, is_cancelled_func)

        try:
            headers = {'Content-Length': str(f_size)}
            resp = requests.put(url, data=wrapped_stream, cookies=cookies, verify=False, timeout=7200, headers=headers)
            if resp.status_code not in [200, 201]:
                body = resp.text[:500] if resp.text else '(empty)'
                raise Exception(f"HTTP {resp.status_code} uploading {dest_rel_path}: {body}")
        except Exception as e:
            if "CancellationRequested" in str(e):
                raise Exception("Restore cancelled by user")
            raise e

    log_info(f"[UPLOAD] Complete: {dest_rel_path}")
    return True

# ===========================================================================
#  MAIN: Import VM via Datastore HTTP + Register
# ===========================================================================
def import_vm_native(si, storage, source_rel_dir, target_ds, target_name, progress_callback=None, is_cancelled_func=None):
    """
    Restores a VM by uploading files from StorageProvider to ESXi and registering the VMX.
    """
    mat_dir = None
    created_dir = False
    try:
        log_info(f"[RESTORE] Starting import_vm_native for {target_name} on {target_ds}")
        content = si.RetrieveContent()

        from chain_restore import resolve_restore_source
        source_rel_dir, _mat = resolve_restore_source(storage, source_rel_dir)
        mat_dir = _mat
        if _mat:
            log_info(f"[RESTORE] Using materialized CBT chain at {source_rel_dir}")
        
        # More robust datacenter find
        def find_obj(container, vim_type):
            for obj in container.childEntity:
                if isinstance(obj, vim_type): return obj
                if hasattr(obj, 'childEntity'):
                    res = find_obj(obj, vim_type)
                    if res: return res
            return None
            
        log_info(f"[RESTORE] Resolving datacenter...")
        # Prefer the datacenter that actually owns the target datastore. On
        # vCenter the datacenter is NOT "ha-datacenter", so hardcoding it makes
        # the datastore HTTP folder URL 404. Walk each DC's datastores to match.
        datacenter = None
        for dc in content.rootFolder.childEntity:
            if not isinstance(dc, vim.Datacenter):
                continue
            try:
                if any(ds.name == target_ds for ds in dc.datastore):
                    datacenter = dc
                    break
            except Exception:
                continue
        if not datacenter:
            datacenter = find_obj(content.rootFolder, vim.Datacenter)
        if not datacenter:
            log_warn("[RESTORE] Could not find Datacenter via traversal, falling back to index 0.")
            datacenter = content.rootFolder.childEntity[0]

        dc_path = datacenter.name
        log_info(f"[RESTORE] Using datacenter '{dc_path}' for datastore '{target_ds}'.")

        fm = content.fileManager

        # 1. Create target directory
        res_dir = f"[{target_ds}] {target_name}"
        log_info(f"[RESTORE] Creating target directory: {res_dir}")
        try:
            fm.MakeDirectory(name=res_dir, datacenter=datacenter, createParentDirectories=True)
            created_dir = True  # ours: may be removed if the restore fails
            log_info(f"[RESTORE] Directory {res_dir} created/verified.")
        except Exception as dm_err:
            log_error(f"[RESTORE] MakeDirectory failed: {dm_err}")
            raise dm_err

        if progress_callback: progress_callback(5)

        # 2. List source files
        files = storage.list_files(source_rel_dir)
        if not files:
            return False, f"No files found in source directory {source_rel_dir}"

        # 3. Separate files (VMX must be uploaded last or we just upload all)
        vmx_file = next((f for f in files if f.endswith('.vmx')), None)
        if not vmx_file:
            return False, f"No VMX file found in {source_rel_dir}"

        total_files = len(files)
        for idx, filename in enumerate(files):
            source_p = f"{source_rel_dir}/{filename}"
            dest_p = f"{target_name}/{filename}"
            
            step_pct_start = 5 + (90 * idx // total_files)
            step_pct_end = 5 + (90 * (idx + 1) // total_files)
            
            if progress_callback: progress_callback(step_pct_start)
            
            log_info(f"[RESTORE] Uploading {filename} ({idx+1}/{total_files})...")
            if is_cancelled_func and is_cancelled_func():
                raise Exception("Restore cancelled by user")
            _upload_file_http(si, target_ds, dest_p, storage, source_p, is_cancelled_func, progress_callback, step_pct_start, step_pct_end, dc_path=dc_path)

        if progress_callback: progress_callback(95)

        # 4. Register VM
        from esxi_handler import register_vm
        vmx_rel_on_ds = f"{target_name}/{vmx_file}"
        ok, msg = register_vm(si, target_ds, vmx_rel_on_ds, target_name)
        
        if ok:
            if progress_callback: progress_callback(100)
            return True, f"VM {target_name} restored and registered successfully."
        else:
            return False, f"Registration failed: {msg}"

    except Exception as e:
        log_error(f"[RESTORE] Native restore failed: {e}")
        # Nothing registered yet: remove the half-uploaded folder we created
        # on the target datastore (a cancelled restore used to leave it).
        try:
            if created_dir and vsphere_context.find_vm_by_name(si, target_name) is None:
                t = content.fileManager.DeleteDatastoreFile_Task(
                    name=f"[{target_ds}] {target_name}", datacenter=datacenter)
                while t.info.state not in (vim.TaskInfo.State.success, vim.TaskInfo.State.error):
                    time.sleep(1)
                log_info(f"[RESTORE] Removed partial folder [{target_ds}] {target_name}")
        except Exception as clean_err:  # noqa: BLE001
            log_warn(f"[RESTORE] Could not remove partial folder: {clean_err}")
        return False, str(e)
    finally:
        # The rebuilt full disk is temporary: without this every restore left
        # a full-size copy in backup storage (and in S3), success or not.
        if mat_dir:
            try:
                storage.delete_dir(mat_dir)
                log_info(f"[RESTORE] Removed temporary rebuilt disk {mat_dir}")
            except Exception as e:  # noqa: BLE001
                log_warn(f"[RESTORE] Could not remove {mat_dir}: {e}")

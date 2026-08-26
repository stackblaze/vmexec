import ssl
import socket
import atexit
import datetime
import urllib3
from urllib.parse import urlparse
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from logger_util import log_info, log_warn, log_error

# Disable strict SSL verification warnings for ESXi self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import vsphere_context


class VSphereConnectionError(Exception):
    """A connection or authentication failure with a reason a human can act on."""


def split_host_port(raw):
    """
    Accept what people actually paste and return (host, port).

    SmartConnect wants a BARE hostname. Given "https://vc.example.com/" it looks
    up a host literally named "https://vc.example.com/", fails DNS, and the caller
    sees a generic connection error that says nothing about the real cause. A
    stray scheme or trailing slash is by far the most common way to register a
    host that "cannot connect" while the server is perfectly reachable.
    """
    if not raw:
        return "", None
    value = str(raw).strip()
    if not value:
        return "", None
    # urlparse only populates .hostname/.port when there is a netloc to parse.
    if "//" not in value:
        value = "//" + value
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").strip()
        port = parsed.port
    except ValueError:
        # e.g. a non-numeric port — fall back to the raw text minus decoration
        return value.lstrip("/").split("/")[0], None
    return host, port


def normalize_host(raw):
    """split_host_port() as a single string, for storing/displaying."""
    host, port = split_host_port(raw)
    if host and port:
        return f"{host}:{port}"
    return host


def describe_connect_failure(host, exc, port=None):
    """Turn a pyVmomi/socket exception into something worth showing a user."""
    target = f"{host}:{port}" if port else host
    if isinstance(exc, vim.fault.InvalidLogin):
        return f"Incorrect username or password for {target}."
    if isinstance(exc, vim.fault.NoPermission):
        return f"That account has no permission to log in to {target}."
    if isinstance(exc, socket.gaierror):
        return (f"'{host}' could not be resolved. Enter a bare hostname or IP "
                f"(no https:// prefix and no trailing slash).")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"Timed out connecting to {target}. Check routing and firewalls."
    if isinstance(exc, ConnectionRefusedError):
        return f"Connection refused by {target}. Is it listening on that port?"
    if isinstance(exc, ssl.SSLError):
        return f"TLS handshake with {target} failed: {exc}"
    return f"Could not connect to {target}: {exc}"


def connect_esxi(host, user, pwd, raise_on_error=False):
    """
    Connects to the ESXi/vCenter host and returns the service instance.

    Returns None on failure by default, which is the contract every existing
    caller relies on. Pass raise_on_error=True to get a VSphereConnectionError
    carrying the actual reason instead — callers that surface errors to a user
    want to distinguish "wrong password" from "no such host".
    """
    host_clean, port = split_host_port(host)
    if not host_clean:
        reason = "No host address was provided."
        log_error(f"[ESXI] {reason}")
        if raise_on_error:
            raise VSphereConnectionError(reason)
        return None
    cleaned = normalize_host(host)
    if cleaned != str(host).strip():
        log_info(f"[ESXI] Normalized host {str(host).strip()!r} -> {cleaned!r}")

    context = ssl._create_unverified_context() # Ignore self-signed certs
    try:
        log_info(f"[ESXI] Connecting to {host_clean}...")
        kwargs = {"host": host_clean, "user": user, "pwd": pwd, "sslContext": context}
        if port:
            kwargs["port"] = port
        si = SmartConnect(**kwargs)
        log_info(f"[ESXI] Connected successfully to {host_clean}")
        atexit.register(Disconnect, si)
        return si
    except Exception as e:
        reason = describe_connect_failure(host_clean, e, port)
        log_error(f"[ESXI] {reason}")
        if raise_on_error:
            raise VSphereConnectionError(reason) from e
        return None

def get_all_vms(si):
    """
    Retrieves a list of all VMs on the host.
    Returns a list of dictionaries with basic VM info.
    """
    if not si:
        return []
    
    content = si.RetrieveContent()
    container = content.rootFolder
    viewType = [vim.VirtualMachine]
    recursive = True
    
    containerView = content.viewManager.CreateContainerView(container, viewType, recursive)
    
    children = containerView.view
    vm_list = []
    
    for child in children:
        summary_config = child.summary.config if child.summary else None
        # vSphere templates are VirtualMachine objects too. They cannot be
        # powered on or snapshotted, so offering them as backup candidates only
        # clutters the inventory with rows that could never produce a backup.
        if summary_config is None or getattr(summary_config, "template", False):
            continue
        # vCLS agent VMs (vSphere Cluster Services) are owned by vCenter's EAM:
        # auto-created, auto-recreated, and VMware explicitly says never to back
        # up or snapshot them. Unconditional, unlike the exclude_infra_vms
        # setting, which also matches names like "vcenter" that ARE legitimate
        # backup targets. VMware names them "vCLS-<uuid>" (older builds "vCLS (n)").
        name = getattr(summary_config, "name", "") or ""
        if name == "vCLS" or name.startswith("vCLS-") or name.startswith("vCLS "):
            continue
        vm_list.append({
            "name": child.summary.config.name,
            "power_state": child.summary.runtime.powerState,
            "uuid": child.summary.config.uuid,
            "cpu_count": child.summary.config.numCpu if child.summary.config else 0,
            "memory_mb": child.summary.config.memorySizeMB if child.summary.config else 0,
            "storage_gb": round(child.summary.storage.committed / (1024**3), 2) if child.summary.storage else 0.0
        })
    
    return vm_list

def get_datastores(si):
    """
    Retrieves a list of all datastore names on the host.
    """
    if not si:
        return []
    
    content = si.RetrieveContent()
    container = content.rootFolder
    viewType = [vim.Datastore]
    recursive = True
    
    containerView = content.viewManager.CreateContainerView(container, viewType, recursive)
    
    children = containerView.view
    ds_list = []
    
    for child in children:
        cap = child.summary.capacity or 0
        free = child.summary.freeSpace or 0
        cap_gb = round(cap / (1024**3), 1) if cap else 0.0
        free_gb = round(free / (1024**3), 1) if free else 0.0
        free_pct = round((free / cap) * 100, 1) if cap else 0.0
        ds_list.append({
            "name": child.summary.name,
            "capacity_gb": cap_gb,
            "free_gb": free_gb,
            "free_pct": free_pct,
        })
        
    return ds_list

def _find_vm(si, vm_name):
    return vsphere_context.find_vm_by_name(si, vm_name)


def create_snapshot(si, vm_name):
    """ Creates a crash-consistent snapshot of a VM. Returns the task. """
    vm = _find_vm(si, vm_name)
    
    if not vm:
        print(f"VM {vm_name} not found for snapshot.")
        return None
        
    snapshot_name = f"VMBACKUP_TEMP_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    description = "Temporary snapshot for automated backup."
    memory = False  # Crash-consistent only
    quiesce = False # Basic snapshot
    
    task = vm.CreateSnapshot_Task(name=snapshot_name, description=description, memory=memory, quiesce=quiesce)
    print(f"Creating snapshot {snapshot_name} for {vm_name}...")
    
    import time
    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
        time.sleep(2)
        
    if task.info.state == vim.TaskInfo.State.success:
        print(f"Snapshot created successfully.")
        # Return the actual snapshot object reference
        for snap in vm.snapshot.rootSnapshotList:
            if snap.name == snapshot_name:
                return snap.snapshot
        return True # Fallback if we can't find the exact ref
    else:
        print(f"Snapshot creation failed: {task.info.error}")
        return None

def remove_snapshot(si, vm_name, timeout_mins=60):
    """Remove all orphaned VMBACKUP_TEMP_* snapshots for a VM."""
    import backup_engine
    backup_engine.remove_orphaned_backup_snapshots(
        si, vm_name, timeout_mins=timeout_mins, min_age_secs=0,
    )
    return True

def wait_for_vm_idle(si, vm_name, timeout_mins=15):
    """ Polls the VM's recent tasks and waits until none are in progress. """
    content = si.RetrieveContent()
    container = content.rootFolder
    viewType = [vim.VirtualMachine]
    recursive = True
    containerView = content.viewManager.CreateContainerView(container, viewType, recursive)
    
    vm = None
    for child in containerView.view:
        if child.name == vm_name:
            vm = child
            break
            
    if not vm:
        print(f"wait_for_vm_idle: VM {vm_name} not found.")
        return True
        
    import time
    start_time = time.time()
    print(f"Checking if VM {vm_name} is busy with tasks...")
    
    while (time.time() - start_time) < (timeout_mins * 60):
        busy = False
        active_tasks_info = []
        
        # recentTask includes tasks from the last few minutes
        for task in vm.recentTask:
            if task.info.state in [vim.TaskInfo.State.running, vim.TaskInfo.State.queued]:
                busy = True
                
                # Calculate duration
                duration_str = "Unknown"
                if task.info.startTime:
                    now = datetime.datetime.now(task.info.startTime.tzinfo)
                    diff = now - task.info.startTime
                    duration_str = str(diff).split('.')[0] # Remove microseconds
                
                task_desc = task.info.descriptionId or "Unknown Task"
                progress = task.info.progress if task.info.progress is not None else 0
                
                info_msg = f"{task_desc} (State: {task.info.state}, Progress: {progress}%, Started: {duration_str} ago)"
                active_tasks_info.append(info_msg)
        
        if not busy:
            print(f"VM {vm_name} is idle. Proceeding...")
            return True, ""
            
        status_report = " | ".join(active_tasks_info)
        print(f"VM {vm_name} is busy: {status_report}. Waiting 15s...")
        time.sleep(15)
        
    final_msg = f"Timeout ({timeout_mins}m) waiting for VM {vm_name} to be idle."
    if active_tasks_info:
        final_msg += f" Last active tasks: {status_report}"
    
    print(f"[WARN] {final_msg}")
    return False, final_msg

def disconnect_removable_devices(si, vm_name):
    """ Disconnects any ISO images from CD-ROM drives and Floppy drives before backup. """
    content = si.RetrieveContent()
    vm = _find_vm(si, vm_name)
    
    if not vm:
        print(f"disconnect_removable_devices: VM {vm_name} not found.")
        return False
        
    devices_to_change = []
    for device in vm.config.hardware.device:
        if isinstance(device, (vim.VirtualCdrom, vim.VirtualFloppy)):
            # Check if it has a backing that points to a file (ISO/FLP)
            has_file_backing = False
            if hasattr(device.backing, 'fileName') and device.backing.fileName:
                has_file_backing = True
                
            if has_file_backing:
                print(f"Disconnecting removable media {device.backing.fileName} from {vm_name}...")
                
                if isinstance(device, vim.VirtualCdrom):
                    new_backing = vim.VirtualCdromAtapiBackingInfo(deviceName="")
                else:
                    new_backing = vim.VirtualFloppyDeviceBackingInfo(deviceName="")
                
                device.backing = new_backing
                device.connectable.connected = False
                device.connectable.startConnected = False
                
                spec = vim.VirtualDeviceConfigSpec()
                spec.device = device
                spec.operation = vim.VirtualDeviceConfigSpec.Operation.edit
                devices_to_change.append(spec)
                
    if not devices_to_change:
        return True
        
    config_spec = vim.vm.ConfigSpec()
    config_spec.deviceChange = devices_to_change
    
    task = vm.ReconfigVM_Task(spec=config_spec)
    
    import time
    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
        time.sleep(2)
        
    return task.info.state == vim.TaskInfo.State.success

def check_consolidation_needed(si, vm_name):
    """ Returns True if the VM requires disk consolidation. """
    content = si.RetrieveContent()
    vm = _find_vm(si, vm_name)
    if vm and hasattr(vm.runtime, 'consolidationNeeded'):
        return vm.runtime.consolidationNeeded
    return False

def cleanup_ghost_tasks(si, vm_name, timeout_mins=60):
    """ Finds any existing 'exportVm' tasks for this VM and cancels them if they are too old. """
    content = si.RetrieveContent()
    vm = _find_vm(si, vm_name)
    if not vm:
        return
        
    for task in vm.recentTask:
        if task.info.descriptionId == "vim.VirtualMachine.exportVm" and task.info.state == vim.TaskInfo.State.running:
            # Check age
            if task.info.startTime:
                now = datetime.datetime.now(task.info.startTime.tzinfo)
                diff = now - task.info.startTime
                if diff.total_seconds() > (timeout_mins * 60):
                    print(f"[RECOVERY] Found ghost exportVm task for {vm_name} running for {int(diff.total_seconds()/60)}m. Attempting to cancel...")
                    try:
                        task.CancelTask()
                    except Exception as e:
                        print(f"[RECOVERY] Failed to cancel task: {e}")

def shutdown_vm(si, vm_name, graceful_timeout_mins=5):
    """
    Gracefully shuts down a VM using VMware Tools guest shutdown.
    Falls back to hard PowerOff if the guest doesn't respond within graceful_timeout_mins.
    Returns (success: bool, message: str)
    """
    import time
    content = si.RetrieveContent()
    vm = _find_vm(si, vm_name)
    if not vm:
        return False, f"VM {vm_name} not found"

    power_state = getattr(vm.runtime, 'powerState', None)
    if power_state == 'poweredOff':
        log_info(f"[POWER] VM {vm_name} is already powered off.")
        return True, "Already powered off"

    # Try graceful shutdown via VMware Tools
    try:
        log_info(f"[POWER] Sending graceful shutdown to {vm_name}...")
        vm.ShutdownGuest()
    except Exception as e:
        log_warn(f"[POWER] Guest shutdown failed (tools may not be running): {e}. Falling back to hard power off.")
        try:
            task = vm.PowerOffVM_Task()
            start = time.time()
            while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                if time.time() - start > 120:
                    return False, "Hard power-off timeout"
                time.sleep(3)
            if task.info.state == vim.TaskInfo.State.success:
                log_info(f"[POWER] Hard power-off successful for {vm_name}")
                return True, "Hard power-off successful"
            else:
                return False, f"Hard power-off failed: {task.info.error}"
        except Exception as e2:
            return False, f"Hard power-off error: {e2}"

    # Wait for graceful shutdown to complete
    deadline = time.time() + (graceful_timeout_mins * 60)
    log_info(f"[POWER] Waiting up to {graceful_timeout_mins}m for {vm_name} to shut down...")
    while time.time() < deadline:
        time.sleep(5)
        try:
            # Refresh VM state
            vm = _find_vm(si, vm_name)
            if vm and vm.runtime.powerState == 'poweredOff':
                log_info(f"[POWER] {vm_name} shut down gracefully.")
                return True, "Graceful shutdown successful"
        except Exception:
            pass

    # Graceful timeout — fall back to hard power off
    log_warn(f"[POWER] Graceful shutdown timeout for {vm_name}. Issuing hard power-off...")
    try:
        task = vm.PowerOffVM_Task()
        start = time.time()
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            if time.time() - start > 120:
                return False, "Hard power-off timeout after graceful timeout"
            time.sleep(3)
        if task.info.state == vim.TaskInfo.State.success:
            log_info(f"[POWER] Hard power-off successful for {vm_name} (after graceful timeout)")
            return True, "Hard power-off successful (graceful timeout)"
        else:
            return False, f"Hard power-off failed: {task.info.error}"
    except Exception as e:
        return False, f"Hard power-off error after graceful timeout: {e}"


def poweron_vm(si, vm_name, timeout_mins=3):
    """
    Powers on a VM. Waits until it reaches poweredOn state.
    Returns (success: bool, message: str)
    """
    import time
    content = si.RetrieveContent()
    vm = _find_vm(si, vm_name)
    if not vm:
        return False, f"VM {vm_name} not found"

    power_state = getattr(vm.runtime, 'powerState', None)
    if power_state == 'poweredOn':
        log_info(f"[POWER] VM {vm_name} is already powered on.")
        return True, "Already powered on"

    log_info(f"[POWER] Powering on {vm_name}...")
    try:
        task = vm.PowerOnVM_Task()
        start = time.time()
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            if time.time() - start > (timeout_mins * 60):
                return False, f"Power-on timeout ({timeout_mins}m)"
            time.sleep(3)
        if task.info.state == vim.TaskInfo.State.success:
            log_info(f"[POWER] {vm_name} powered on successfully.")
            return True, "Power-on successful"
        else:
            return False, f"Power-on failed: {task.info.error}"
    except Exception as e:
        return False, f"Power-on error: {e}"


def register_vm(si, datastore_name, vmx_rel_path, vm_name):

    """
    Registers a VM in the ESXi inventory from an existing VMX file on a datastore.
    """
    import time
    content = si.RetrieveContent()

    # Find datacenter robustly
    dc = None
    for child in content.rootFolder.childEntity:
        if isinstance(child, vim.Datacenter):
            dc = child
            break
    if not dc:
        dc = content.rootFolder.childEntity[0]

    folder = dc.vmFolder

    # Find the default resource pool (required by RegisterVM_Task on standalone ESXi)
    # On standalone ESXi, the resource pool is available under the ComputeResource/HostSystem
    resource_pool = None
    try:
        for child in dc.hostFolder.childEntity:
            # child is a ComputeResource or ClusterComputeResource
            if hasattr(child, 'resourcePool') and child.resourcePool:
                resource_pool = child.resourcePool
                break
    except Exception:
        pass

    # Fallback: if still none, find the host and get its parent's resource pool
    if resource_pool is None:
        try:
            container = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.HostSystem], True)
            if container.view:
                host = container.view[0]
                resource_pool = host.parent.resourcePool
        except Exception:
            pass

    vmx_path = f"[{datastore_name}] {vmx_rel_path}"

    log_info(f"Registering VM {vm_name} from {vmx_path}... (pool: {resource_pool})")
    try:
        task = folder.RegisterVM_Task(
            path=vmx_path,
            name=vm_name,
            asTemplate=False,
            pool=resource_pool
        )

        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            time.sleep(2)

        if task.info.state == vim.TaskInfo.State.success:
            log_info(f"VM {vm_name} registered successfully.")
            return True, "Success"
        else:
            return False, str(task.info.error)
    except Exception as e:
        return False, str(e)


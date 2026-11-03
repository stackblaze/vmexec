"""
Never power off a VM that VMExec itself depends on.

"Power off for backup" shuts a VM down through vCenter and powers it back on
through vCenter afterwards. Shutting down the vCenter VMExec is connected to
(or the router or appliance on its path) cuts the connection the power-on
needs, and the VM stays off. These checks run before any power action and do
not depend on any setting:

  1. the name matches the infrastructure patterns (vCenter, vCLS, ...)
  2. the name is listed in VMEXEC_PROTECTED_VMS (comma-separated, for the
     routers and the appliance itself; set by the deployment)
  3. the VM is the vCenter VMExec is connected to: one of its guest IPs is an
     address of the connected host, or its guest hostname is the connected
     host name / vCenter's own FQDN

If a VM's identity cannot be read, the power-off is refused (fail closed).
"""
import os
import socket

from logger_util import log_warn


def protected_names():
    raw = os.environ.get("VMEXEC_PROTECTED_VMS", "")
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


def name_block_reason(vm_name):
    """Reason a VM may never be powered off, from its name alone; or None."""
    from backup_engine import matches_infra_vm_pattern

    if matches_infra_vm_pattern(vm_name):
        return "it is an infrastructure VM (vCenter / vCLS)"
    if (vm_name or "").strip().lower() in protected_names():
        return "it is listed in VMEXEC_PROTECTED_VMS"
    return None


def _addresses(host):
    out = {host}
    try:
        for info in socket.getaddrinfo(host, None):
            out.add(info[4][0])
    except (socket.gaierror, UnicodeError, TypeError):
        pass
    return out


def _vcenter_names(si):
    """vCenter's own FQDN / IP settings (empty on standalone ESXi)."""
    names = set()
    try:
        for opt in si.RetrieveContent().setting.setting or []:
            if opt.key in ("VirtualCenter.FQDN", "VirtualCenter.AutoManagedIPV4") and opt.value:
                names.add(str(opt.value).strip().lower())
    except Exception:
        pass
    return names


def _guest_identity(vm_obj):
    guest = vm_obj.guest
    ips = set()
    if getattr(guest, "ipAddress", None):
        ips.add(guest.ipAddress)
    for nic in getattr(guest, "net", None) or []:
        for ip in getattr(nic, "ipAddress", None) or []:
            ips.add(ip)
    hostname = (getattr(guest, "hostName", None) or "").strip().lower()
    return ips, hostname


def power_off_block_reason(si, vm_obj, vm_name, connected_host):
    """Why VMExec must not power off this VM, or None if it may."""
    reason = name_block_reason(vm_name)
    if reason:
        return reason
    if vm_obj is None:
        return None  # nothing to power off
    try:
        ips, hostname = _guest_identity(vm_obj)
    except Exception as e:
        log_warn(f"[POWER] Cannot read guest identity of {vm_name}: {e}")
        return "its guest identity could not be read, so it may be the vCenter VMExec uses"

    host = (connected_host or "").strip().lower()
    vc_names = _vcenter_names(si)
    targets = _addresses(host) | vc_names
    for n in vc_names:
        targets |= _addresses(n)
    if ips & targets:
        return "it is the vCenter VMExec is connected to"
    if hostname:
        names = {host} | vc_names
        shorts = {n.split(".")[0] for n in names if n and not n[0].isdigit()}
        if hostname in names or hostname.split(".")[0] in shorts:
            return "it is the vCenter VMExec is connected to"
    return None

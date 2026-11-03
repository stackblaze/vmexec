"""power_guard: VMExec never powers off a VM it depends on (2026-11-03:
"Power off for backup" on the vCenter row shut down the vCenter VMExec was
connected to, and the power-on through that vCenter could never happen)."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import power_guard


def _vm(ips=(), hostname=""):
    nics = [SimpleNamespace(ipAddress=list(ips))]
    return SimpleNamespace(guest=SimpleNamespace(ipAddress=ips[0] if ips else None, net=nics, hostName=hostname))


def _si(settings=None):
    si = MagicMock()
    si.RetrieveContent.return_value.setting.setting = [
        SimpleNamespace(key=k, value=v) for k, v in (settings or {}).items()
    ]
    return si


class TestNameBlock(unittest.TestCase):
    def test_vcenter_name_always_blocked(self):
        self.assertIsNotNone(power_guard.name_block_reason("VMware vCenter Server"))

    def test_protected_list(self):
        with patch.dict(os.environ, {"VMEXEC_PROTECTED_VMS": "vyos-01, VMExec-US-Central-1"}):
            self.assertIsNotNone(power_guard.name_block_reason("vyos-01"))
            self.assertIsNotNone(power_guard.name_block_reason("vmexec-us-central-1"))
            self.assertIsNone(power_guard.name_block_reason("swift-dental-01"))

    def test_ordinary_vm_allowed(self):
        with patch.dict(os.environ, {"VMEXEC_PROTECTED_VMS": ""}):
            self.assertIsNone(power_guard.name_block_reason("swift-dental-01"))


class TestConnectedVcenter(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"VMEXEC_PROTECTED_VMS": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_renamed_vcenter_found_by_ip(self):
        vm = _vm(ips=("10.10.32.5",))
        reason = power_guard.power_off_block_reason(_si(), vm, "vc-appliance", "10.10.32.5")
        self.assertIn("connected to", reason)

    def test_renamed_vcenter_found_by_vcenter_fqdn_setting(self):
        vm = _vm(ips=("10.10.32.5",), hostname="vc01.corp.local")
        si = _si({"VirtualCenter.FQDN": "vc01.corp.local"})
        reason = power_guard.power_off_block_reason(si, vm, "vc-appliance", "38.107.233.109")
        self.assertIn("connected to", reason)

    def test_renamed_vcenter_found_by_short_hostname(self):
        vm = _vm(ips=("10.10.32.5",), hostname="vc-us-central-1")
        reason = power_guard.power_off_block_reason(_si(), vm, "appliance-x", "vc-us-central-1.stackblaze.cloud")
        self.assertIn("connected to", reason)

    def test_other_vm_allowed(self):
        vm = _vm(ips=("10.10.34.20",), hostname="worker-1")
        self.assertIsNone(power_guard.power_off_block_reason(_si(), vm, "worker-1", "10.10.32.5"))

    def test_unreadable_guest_fails_closed(self):
        vm = SimpleNamespace()  # no .guest
        self.assertIsNotNone(power_guard.power_off_block_reason(_si(), vm, "worker-1", "10.10.32.5"))


class TestShutdownRefuses(unittest.TestCase):
    def test_shutdown_vm_never_calls_vsphere_for_vcenter(self):
        import esxi_handler
        vm = MagicMock()
        vm.runtime.powerState = "poweredOn"
        with patch.object(esxi_handler, "_find_vm", return_value=vm):
            ok, msg = esxi_handler.shutdown_vm(_si(), "VMware vCenter Server", connected_host="10.0.0.1")
        self.assertFalse(ok)
        self.assertIn("Refusing", msg)
        vm.ShutdownGuest.assert_not_called()
        vm.PowerOffVM_Task.assert_not_called()


class TestApiRefuses(unittest.TestCase):
    def test_update_vm_job_rejects_power_off_for_vcenter(self):
        from services import backup_ops
        vm = SimpleNamespace(vm_name="VMware vCenter Server", power_off_for_backup=False)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = vm
        with self.assertRaises(backup_ops.PowerOffNotAllowed):
            backup_ops.update_vm_job(db, 1, {"power_off_for_backup": True})
        self.assertFalse(vm.power_off_for_backup)
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

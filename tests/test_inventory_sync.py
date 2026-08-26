import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import esxi_handler


def _fake_vm(name, template=False, power="poweredOff"):
    return SimpleNamespace(summary=SimpleNamespace(
        config=SimpleNamespace(name=name, template=template, uuid=f"uuid-{name}",
                               numCpu=2, memorySizeMB=1024),
        runtime=SimpleNamespace(powerState=power),
        storage=SimpleNamespace(committed=10 * 1024**3),
    ))


def _fake_si(vms):
    si = MagicMock()
    si.RetrieveContent.return_value.viewManager.CreateContainerView.return_value.view = vms
    return si


class TestGetAllVmsTemplateFilter(unittest.TestCase):
    """Templates cannot be powered on or snapshotted — never backup candidates."""

    def test_templates_are_skipped(self):
        si = _fake_si([
            _fake_vm("kmj-01", power="poweredOn"),
            _fake_vm("ubuntu-2204-base", template=True),
            _fake_vm("ubuntu-2204-kube-v1.35.0-worker-20260825-2247", template=True),
        ])
        names = [v["name"] for v in esxi_handler.get_all_vms(si)]
        self.assertEqual(names, ["kmj-01"])

    def test_vcls_agent_vms_are_skipped(self):
        si = _fake_si([
            _fake_vm("vCLS-1dc8f8f5-b77d-465b-86b6-584dd5d80a6e", power="poweredOn"),
            _fake_vm("vCLS (1)", power="poweredOn"),
            _fake_vm("kmj-01", power="poweredOn"),
        ])
        names = [v["name"] for v in esxi_handler.get_all_vms(si)]
        self.assertEqual(names, ["kmj-01"])

    def test_vcenter_itself_is_NOT_filtered(self):
        # The VCSA is a legitimate backup target; only the agent VMs are not.
        si = _fake_si([_fake_vm("VMware vCenter Server", power="poweredOn")])
        self.assertEqual(len(esxi_handler.get_all_vms(si)), 1)

    def test_all_templates_yields_empty(self):
        si = _fake_si([_fake_vm("t1", template=True), _fake_vm("t2", template=True)])
        self.assertEqual(esxi_handler.get_all_vms(si), [])

    def test_vm_without_summary_config_is_skipped_not_crashed(self):
        broken = SimpleNamespace(summary=SimpleNamespace(config=None, runtime=None, storage=None))
        si = _fake_si([broken, _fake_vm("ok")])
        names = [v["name"] for v in esxi_handler.get_all_vms(si)]
        self.assertEqual(names, ["ok"])

    def test_regular_fields_still_reported(self):
        si = _fake_si([_fake_vm("vm1", power="poweredOn")])
        vm = esxi_handler.get_all_vms(si)[0]
        self.assertEqual(vm["power_state"], "poweredOn")
        self.assertEqual(vm["cpu_count"], 2)
        self.assertEqual(vm["storage_gb"], 10.0)


if __name__ == "__main__":
    unittest.main()

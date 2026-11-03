import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import vsphere_context


class TestVsphereContext(unittest.TestCase):
    def test_detect_standalone(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "HostAgent"
        self.assertEqual(vsphere_context.detect_connection_type(si), vsphere_context.CONN_STANDALONE)

    def test_detect_vcenter(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "VirtualCenter"
        self.assertEqual(vsphere_context.detect_connection_type(si), vsphere_context.CONN_VCENTER)

    def test_resolve_stored_type(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "HostAgent"
        self.assertEqual(
            vsphere_context.resolve_connection_type(si, vsphere_context.CONN_VCENTER),
            vsphere_context.CONN_VCENTER,
        )

    def test_supports_nfc_export(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "VirtualCenter"
        self.assertTrue(vsphere_context.supports_nfc_export(si))
        si.RetrieveContent.return_value.about.apiType = "HostAgent"
        self.assertFalse(vsphere_context.supports_nfc_export(si))

    def test_vddk_disk_open_candidates(self):
        disk = {
            "ds_name": "ds1",
            "ds_path": "[ds1] vyos-02/vyos-02-000001.vmdk",
            "rel_path": "vyos-02/vyos-02-000001.vmdk",
        }
        standalone = vsphere_context.vddk_disk_open_candidates(disk, vsphere_context.CONN_STANDALONE)
        self.assertEqual(standalone[0], "[ds1] vyos-02/vyos-02.vmdk")
        self.assertEqual(standalone[1], disk["ds_path"])
        vcenter = vsphere_context.vddk_disk_open_candidates(disk, vsphere_context.CONN_VCENTER)
        self.assertEqual(vcenter[0], "[ds1] vyos-02/vyos-02.vmdk")
        self.assertEqual(vcenter[1], disk["ds_path"])

    def test_vddk_base_disk_path(self):
        disk = {
            "ds_name": "ds1",
            "rel_path": "vyos-02/vyos-02-000002.vmdk",
        }
        self.assertEqual(
            vsphere_context.vddk_base_disk_path(disk),
            "[ds1] vyos-02/vyos-02.vmdk",
        )

    def test_vddk_base_disk_path_keeps_numbered_base_name(self):
        # vyos-01.vmdk is a base disk, not a snapshot delta: it must not
        # become vyos.vmdk (seen on the 2026-11-03 vyos-01 backups).
        disk = {"ds_name": "ds1", "rel_path": "vyos-01/vyos-01.vmdk"}
        self.assertEqual(vsphere_context.vddk_base_disk_path(disk), "[ds1] vyos-01/vyos-01.vmdk")
        delta = {"ds_name": "ds1", "rel_path": "vyos-01/vyos-01-000003.vmdk"}
        self.assertEqual(vsphere_context.vddk_base_disk_path(delta), "[ds1] vyos-01/vyos-01.vmdk")

    def test_build_nbdkit_cmd_standalone(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "HostAgent"
        si._stub.cookie = "vmware_soap_session=\"abc\""
        vm = SimpleNamespace(_moId="107")
        snap = SimpleNamespace(_moId="107-snapshot-19")
        cmd, conn = vsphere_context.build_nbdkit_vddk_cmd(
            si, vm, snap, "[ds] vm/disk.vmdk",
            "esxi.example.com", "root", "/tmp/pw", "AA:BB", "/opt/vddk",
        )
        self.assertEqual(conn, vsphere_context.CONN_STANDALONE)
        self.assertIn("vm=moref=107", cmd)
        self.assertIn("snapshot=107-snapshot-19", cmd)
        self.assertIn("--filter=noextents", cmd)
        self.assertIn("unbuffered=true", cmd)
        self.assertIn("-r", cmd)
        self.assertNotIn("snapshot=moref=", " ".join(cmd))
        self.assertFalse(any(c.startswith("cookie=") for c in cmd))

    def test_build_nbdkit_cmd_vcenter_with_cookie(self):
        si = MagicMock()
        si.RetrieveContent.return_value.about.apiType = "VirtualCenter"
        si._stub.cookie = 'vmware_soap_session="sess-token"; other=x'
        vm = SimpleNamespace(_moId="vm-16")
        snap = SimpleNamespace(_moId="snapshot-12345")
        cmd, conn = vsphere_context.build_nbdkit_vddk_cmd(
            si, vm, snap, "[ds] vm/disk.vmdk",
            "vcenter.example.com", "administrator@vsphere.local", "/tmp/pw", "AA:BB", "/opt/vddk",
        )
        self.assertEqual(conn, vsphere_context.CONN_VCENTER)
        self.assertIn("vm=moref=vm-16", cmd)
        self.assertIn("snapshot=snapshot-12345", cmd)
        self.assertIn("cookie=sess-token", cmd)


if __name__ == "__main__":
    unittest.main()

"""restore_vddk.plan: what the fast restore writes, and when it refuses."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import backup_manifest as bm
import restore_vddk
from delta_store import write_delta_file


class Storage:
    def __init__(self, root):
        self.root = root

    def _full_path(self, p):
        return os.path.join(self.root, p)

    def exists(self, p):
        return os.path.exists(self._full_path(p))

    def makedirs(self, p):
        os.makedirs(self._full_path(p), exist_ok=True)

    def open_write(self, p):
        full = self._full_path(p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return open(full, "wb")

    def open_read(self, p):
        return open(self._full_path(p), "rb")


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.st = Storage(self.tmp)
        self.vm = "vyos-01"
        cap = 1024 * 1024
        full, inc = "20261103-173943", "20261103-183337"
        for pid in (full, inc):
            self.st.makedirs(bm.point_rel(self.vm, pid))
        with open(self.st._full_path(f"{bm.point_rel(self.vm, full)}/vyos-01-flat.vmdk"), "wb") as f:
            f.truncate(cap)
        with open(self.st._full_path(f"{bm.point_rel(self.vm, full)}/vyos-01.vmdk"), "w") as f:
            f.write('ddb.adapterType = "buslogic"\n')
        for pid in (full, inc):
            with open(self.st._full_path(f"{bm.point_rel(self.vm, pid)}/vyos-01.vmx"), "w") as f:
                f.write("x")
        write_delta_file(self.st._full_path(f"{bm.point_rel(self.vm, inc)}/vyos-01-flat.vmdk.delta.nvbd"), [(0, b"AB")])
        bm.save_manifest(self.st, self.vm, full, bm.build_manifest(
            full, "full", None, [bm.build_disk_entry(2000, "vyos-01.vmdk", "vyos-01-flat.vmdk", cap, "c1", "full")],
            vmx_file="vyos-01.vmx"))
        bm.save_manifest(self.st, self.vm, inc, bm.build_manifest(
            inc, "incremental", full, [bm.build_disk_entry(2000, "vyos-01.vmdk", "vyos-01-flat.vmdk", cap, "c2",
                                                            "incremental", delta_file="vyos-01-flat.vmdk.delta.nvbd")],
            vmx_file="vyos-01.vmx"))
        chain = bm.create_empty_chain(self.vm)
        chain = bm.add_point_to_chain(chain, {"id": full, "type": "full", "parent": None})
        chain = bm.add_point_to_chain(chain, {"id": inc, "type": "incremental", "parent": full})
        bm.save_chain(self.st, self.vm, chain)
        self.full, self.inc = full, inc

    def test_incremental_point(self):
        p = restore_vddk.plan(self.st, bm.point_rel(self.vm, self.inc))
        d = p["disks"][0]
        self.assertEqual(d["capacity"], 1024 * 1024)
        self.assertEqual(d["adapter"], "busLogic")
        self.assertTrue(d["full_local"].endswith(f"{self.full}/vyos-01-flat.vmdk"))
        self.assertEqual(len(d["deltas_local"]), 1)
        self.assertEqual(p["vmx"], "vyos-01.vmx")

    def test_full_point_has_no_deltas(self):
        p = restore_vddk.plan(self.st, bm.point_rel(self.vm, self.full))
        self.assertEqual(p["disks"][0]["deltas_local"], [])

    def test_refuses_non_chain_and_missing_full(self):
        with self.assertRaises(restore_vddk.FastRestoreUnsupported):
            restore_vddk.plan(self.st, "vyos-01/2026-11-03")
        os.remove(self.st._full_path(f"{bm.point_rel(self.vm, self.full)}/vyos-01-flat.vmdk"))
        with self.assertRaises(restore_vddk.FastRestoreUnsupported):
            restore_vddk.plan(self.st, bm.point_rel(self.vm, self.inc))

    def test_refuses_storage_without_local_paths(self):
        class S3Like:
            pass
        with self.assertRaises(restore_vddk.FastRestoreUnsupported):
            restore_vddk.plan(S3Like(), bm.point_rel(self.vm, self.inc))

    def test_no_vddk_means_old_path_before_any_change(self):
        with patch("vddk_transport.is_available", return_value=False):
            with self.assertRaises(restore_vddk.FastRestoreUnsupported):
                restore_vddk.restore_point(None, self.st, bm.point_rel(self.vm, self.inc), "ds", "copy",
                                           "vc", "u", "p")


if __name__ == "__main__":
    unittest.main()

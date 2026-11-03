"""A failed CBT backup leaves no incomplete point behind."""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cbt_transport


class Storage:
    def __init__(self, root):
        self.root = root

    def _full_path(self, p):
        return os.path.join(self.root, p)

    def exists(self, p):
        return os.path.exists(self._full_path(p))

    def makedirs(self, p):
        os.makedirs(self._full_path(p), exist_ok=True)

    def delete_dir(self, p):
        import shutil
        shutil.rmtree(self._full_path(p), ignore_errors=True)

    def get_base_path(self):
        return self.root

    def open_read(self, p):
        return open(self._full_path(p), "rb")


class TestFailureCleanup(unittest.TestCase):
    def test_incomplete_point_removed(self):
        st = Storage(tempfile.mkdtemp())
        vm = MagicMock()
        vm.runtime.powerState = "poweredOn"
        disk = {"device_key": 2000, "ds_name": "ds", "ds_path": "[ds] v/v.vmdk", "rel_path": "v/v.vmdk",
                "capacity_bytes": 1024}
        snap = MagicMock()

        def make_snap(si, name):
            return snap, "snap"

        with patch("backup_engine._get_vm", return_value=vm), \
             patch.object(cbt_transport.cbt_core, "collect_cbt_disks", return_value=[disk]), \
             patch.object(cbt_transport.cbt_core, "should_take_full_backup", return_value=(True, "test")), \
             patch.object(cbt_transport.cbt_core, "get_snapshot_change_ids", return_value={}), \
             patch.object(cbt_transport.bm, "load_chain", return_value={"points": []}):
            ok, msg, dest = cbt_transport.export_cbt_backup(
                si=MagicMock(), vm_name="v", storage=st, config=None, vm_record=MagicMock(),
                host_ip="h", host_user="u", host_password="p",
                create_snapshot_func=make_snap, remove_snapshot_func=lambda *a, **k: None,
                download_http_func=MagicMock(side_effect=RuntimeError("datastore read failed")),
            )
        self.assertFalse(ok)
        self.assertIn("datastore read failed", msg)
        points = os.path.join(st.root, "v", "_chain", "points")
        self.assertEqual(os.listdir(points) if os.path.isdir(points) else [], [])


if __name__ == "__main__":
    unittest.main()

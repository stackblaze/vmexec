import os
import tempfile
import unittest
from unittest import mock

from services import backup_ops


class MachineDisksTests(unittest.TestCase):
    def test_reports_usage_and_dedupes_same_filesystem(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            # Two dirs on the same filesystem -> one entry.
            with mock.patch.object(backup_ops, "MACHINE_DISK_PATHS", (("App data", a), ("Backup disk", b))):
                disks = backup_ops._machine_disks()
        self.assertEqual(len(disks), 1)
        d = disks[0]
        self.assertEqual(d["label"], "App data")
        self.assertGreater(d["total_gb"], 0)
        self.assertTrue(0 <= d["used_pct"] <= 100)
        self.assertAlmostEqual(d["used_gb"] + d["free_gb"], d["total_gb"], delta=d["total_gb"] * 0.1 + 0.2)

    def test_missing_path_is_skipped(self):
        with mock.patch.object(backup_ops, "MACHINE_DISK_PATHS", (("Backup disk", "/nonexistent/vmexec"),)):
            self.assertEqual(backup_ops._machine_disks(), [])


if __name__ == "__main__":
    unittest.main()

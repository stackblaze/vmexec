"""services/status_ops.py: storage health, next run, problems for the banner."""
import datetime
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import status_ops

MOUNTS_ZEROFS = """overlay / overlay rw 0 0
/run/zerofs/9p.sock /mnt/backups 9p rw,trans=unix 0 0
/dev/sdb /host/zerofs-cache ext4 ro 0 0
"""
MOUNTS_MISSING = """overlay / overlay rw 0 0
"""


class TestMount(unittest.TestCase):
    def _file(self, text):
        f = tempfile.NamedTemporaryFile("w", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_zerofs_mount_ok(self):
        m = self._file(MOUNTS_ZEROFS)
        self.assertEqual(status_ops.mount_of("/mnt/backups/vyos-01", m), ("/mnt/backups", "9p"))
        self.assertIsNone(status_ops.repo_mount_problem("/mnt/backups", m))

    def test_missing_mount_is_refused(self):
        m = self._file(MOUNTS_MISSING)
        self.assertIn("not mounted", status_ops.repo_mount_problem("/mnt/backups", m))


class TestProbe(unittest.TestCase):
    def setUp(self):
        status_ops._probe_cache.update(at=0.0, result=None)
        self.dir = tempfile.mkdtemp()

    def test_probe_writes_and_cleans_up(self):
        with patch.object(status_ops, "repo_mount_problem", return_value=None):
            r = status_ops.storage_health(self.dir)
        self.assertTrue(r["healthy"])
        self.assertIsNotNone(r["probe_ms"])
        self.assertEqual(os.listdir(os.path.join(self.dir, ".vmexec-health")), [])

    def test_stalled_storage_reported_not_hung(self):
        def stall(path):
            time.sleep(2)
            return 1
        with patch.object(status_ops, "repo_mount_problem", return_value=None), \
             patch.object(status_ops, "_run_probe", side_effect=stall), \
             patch.object(status_ops, "PROBE_TIMEOUT_S", 0.2):
            r = status_ops.storage_health(self.dir)
        self.assertFalse(r["healthy"])
        self.assertIn("did not finish", r["error"])

    def test_unmounted_storage_not_probed(self):
        with patch.object(status_ops, "repo_mount_problem", return_value="not mounted"), \
             patch.object(status_ops, "_run_probe") as probe:
            r = status_ops.storage_health(self.dir)
        probe.assert_not_called()
        self.assertFalse(r["healthy"])


def _vm(name, h, m, freq="daily", days="0,1,2,3,4,5,6", selected=True, active=True):
    return SimpleNamespace(vm_name=name, schedule_hour=h, schedule_minute=m, schedule_frequency=freq,
                           schedule_days=days, is_selected=selected, is_job_active=active)


class TestNextRun(unittest.TestCase):
    def test_earliest_tonight(self):
        now = datetime.datetime(2026, 11, 3, 16, 0)  # a Tuesday
        at, names = status_ops.next_run([_vm("b", 2, 5), _vm("a", 2, 0), _vm("c", 2, 0, active=False)], now)
        self.assertEqual(at, datetime.datetime(2026, 11, 4, 2, 0))
        self.assertEqual(names, ["a"])

    def test_weekly_sunday(self):
        now = datetime.datetime(2026, 11, 3, 16, 0)  # Tuesday
        at, _ = status_ops.next_run([_vm("w", 3, 0, freq="weekly", days="6")], now)
        self.assertEqual(at, datetime.datetime(2026, 11, 8, 3, 0))  # Sunday

    def test_nothing_scheduled(self):
        self.assertEqual(status_ops.next_run([_vm("x", 2, 0, selected=False)]), (None, []))


class TestProblems(unittest.TestCase):
    def test_banner_lists_storage_then_failures(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models import Base, VM, BackupLog
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        db.add(VM(vm_name="vyos-02", is_selected=True, schedule_hour=2, schedule_minute=10))
        db.add(BackupLog(vm_name="vyos-02", status="Failed", message="snapshot could not be created"))
        db.add(BackupLog(vm_name="vyos-01", status="Success", message="ok"))
        db.commit()
        bad = {"healthy": False, "fstype": None, "probe_ms": None, "error": "/mnt/backups is not mounted"}
        with patch.object(status_ops, "storage_health", return_value=bad), \
             patch.object(status_ops, "cache_disk", return_value=None):
            s = status_ops.get_status(db, scheduler_paused=False, vddk_installed=True)
        self.assertEqual(s["last24h"], {"succeeded": 1, "failed": 1})
        self.assertEqual([p["kind"] for p in s["problems"]], ["storage", "backup"])
        self.assertIn("snapshot could not be created", s["problems"][1]["message"])
        self.assertEqual(s["protected"], {"count": 1, "total": 1})


if __name__ == "__main__":
    unittest.main()

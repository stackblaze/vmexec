import unittest
from types import SimpleNamespace as NS
from unittest import mock

import worker


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _DB:
    def __init__(self, vms):
        self.vms = vms
        self.commits = 0

    def query(self, _model):
        return _Query(self.vms)

    def commit(self):
        self.commits += 1


def _vm(vid, action):
    return NS(id=vid, vm_name=f"vm{vid}", current_action=action, progress=40, speed_mbps=1.0)


class OrphanedActionTests(unittest.TestCase):
    def setUp(self):
        worker._orphan_action_seen.clear()
        self.addCleanup(worker._orphan_action_seen.clear)

    def test_stuck_cleaning_up_is_cleared_on_second_check(self):
        vm = _vm(1, "Cleaning up...")
        db = _DB([vm])
        with mock.patch.object(worker, "get_active_backup_vm_ids", return_value=set()):
            self.assertEqual(worker.clear_orphaned_actions(db), [])     # first sighting: wait
            self.assertEqual(vm.current_action, "Cleaning up...")
            self.assertEqual(worker.clear_orphaned_actions(db), ["vm1"])
        self.assertEqual(vm.current_action, "")
        self.assertEqual(vm.progress, 0)

    def test_running_backup_is_never_touched(self):
        vm = _vm(2, "Backing up VM...")
        db = _DB([vm])
        with mock.patch.object(worker, "get_active_backup_vm_ids", return_value={2}):
            worker.clear_orphaned_actions(db)
            worker.clear_orphaned_actions(db)
        self.assertEqual(vm.current_action, "Backing up VM...")

    def test_queue_states_are_not_orphans(self):
        vms = [_vm(3, "Queued..."), _vm(4, worker.WAIT_HOST), _vm(5, "PENDING_RUN")]
        db = _DB(vms)
        with mock.patch.object(worker, "get_active_backup_vm_ids", return_value=set()):
            worker.clear_orphaned_actions(db)
            self.assertEqual(worker.clear_orphaned_actions(db), [])

    def test_changed_action_restarts_the_count(self):
        vm = _vm(6, "Preflight checks...")
        db = _DB([vm])
        with mock.patch.object(worker, "get_active_backup_vm_ids", return_value=set()):
            worker.clear_orphaned_actions(db)
            vm.current_action = "Cleaning up..."
            self.assertEqual(worker.clear_orphaned_actions(db), [])


class JobTimeLimitTests(unittest.TestCase):
    def setUp(self):
        worker._active_backup_started.clear()
        worker._time_limit_stopped.clear()
        self.addCleanup(worker._active_backup_started.clear)
        self.addCleanup(worker._time_limit_stopped.clear)

    def test_overdue_job_is_stopped_once(self):
        worker._active_backup_started.update({1: 0.0, 2: 10 * 3600.0})
        fake_db = mock.MagicMock()
        with mock.patch.object(worker, "SessionLocal", return_value=fake_db), \
             mock.patch.object(worker, "stop_job") as stop:
            self.assertEqual(worker.enforce_job_time_limit(now=13 * 3600.0, max_hours=12), [1])
            self.assertEqual(worker.enforce_job_time_limit(now=14 * 3600.0, max_hours=12), [])
        stop.assert_called_once_with(1)
        fake_db.add.assert_called_once()


if __name__ == "__main__":
    unittest.main()

import datetime
import unittest

import worker


class TestTriggerCooldown(unittest.TestCase):
    def tearDown(self):
        worker.last_trigger_times.pop(999001, None)

    def test_never_triggered(self):
        self.assertEqual(worker.trigger_cooldown_left(999001), 0)

    def test_just_triggered(self):
        worker.last_trigger_times[999001] = datetime.datetime.now().timestamp()
        left = worker.trigger_cooldown_left(999001)
        self.assertGreater(left, 0)
        self.assertLessEqual(left, worker.TRIGGER_COOLDOWN_SECS)

    def test_cooldown_over(self):
        worker.last_trigger_times[999001] = datetime.datetime.now().timestamp() - worker.TRIGGER_COOLDOWN_SECS - 1
        self.assertEqual(worker.trigger_cooldown_left(999001), 0)

    def test_daemon_leaves_pending_run_during_cooldown(self):
        # The daemon skips a PENDING_RUN VM still in cooldown instead of
        # marking it Queued (which queue_backup then dropped).
        src = open(worker.__file__.replace("worker.py", "worker_daemon.py")).read()
        loop = src[src.index('VM.current_action == "PENDING_RUN"'):]
        self.assertLess(loop.index("trigger_cooldown_left"), loop.index('vm.current_action = "Queued..."'))


if __name__ == "__main__":
    unittest.main()

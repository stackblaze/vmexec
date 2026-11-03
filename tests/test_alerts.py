"""services/alert_ops.py: webhook payloads, missed schedules, storage transitions."""
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import alert_ops


def cfg(**kw):
    base = dict(alert_webhook_url="https://discord.com/api/webhooks/1/x",
                alert_on_failure=True, alert_on_missed=True, alert_on_storage=True)
    base.update(kw)
    return SimpleNamespace(**base)


def vm(i, h=2, m=0, last=None, action="", freq="daily", days="0,1,2,3,4,5,6"):
    return SimpleNamespace(id=i, vm_name=f"vm{i}", is_selected=True, is_job_active=True, current_action=action,
                           schedule_hour=h, schedule_minute=m, schedule_frequency=freq, schedule_days=days,
                           last_backup=last)


class TestSend(unittest.TestCase):
    def test_payload_shapes(self):
        self.assertIn("content", alert_ops.payload_for("https://discord.com/api/webhooks/1/x", "hi"))
        self.assertEqual(alert_ops.payload_for("https://hooks.slack.com/services/x", "hi"), {"text": "hi"})
        self.assertEqual(alert_ops.payload_for("https://example.com/hook", "hi")["text"], "hi")

    def test_hint_hides_the_secret_path(self):
        self.assertEqual(alert_ops.webhook_hint("https://discord.com/api/webhooks/123/secret"), "discord.com/…")

    def test_switch_off_or_no_url_sends_nothing(self):
        with patch.object(alert_ops, "_post") as post:
            self.assertFalse(alert_ops.send(cfg(alert_on_failure=False), "failure", "x", sync=True))
            self.assertFalse(alert_ops.send(cfg(alert_webhook_url=""), "failure", "x", sync=True))
            post.assert_not_called()

    def test_webhook_error_never_raises(self):
        with patch.object(alert_ops, "_post", side_effect=OSError("down")):
            self.assertTrue(alert_ops.send(cfg(), "failure", "x", sync=True))


class TestMissed(unittest.TestCase):
    def setUp(self):
        alert_ops._state["missed"].clear()
        self.now = datetime.datetime(2026, 11, 4, 5, 0)   # 3 h after 02:00
        self.utc = self.now

    def run_check(self, vms):
        with patch.object(alert_ops, "send") as send:
            out = alert_ops.check_missed(None, cfg(), vms, now=self.now, utc_now=self.utc)
        return out, send

    def test_not_started_is_missed_once(self):
        out, send = self.run_check([vm(1, last=datetime.datetime(2026, 11, 3, 2, 10))])
        self.assertEqual(out, ["vm1"])
        send.assert_called_once()
        out, _ = self.run_check([vm(1, last=datetime.datetime(2026, 11, 3, 2, 10))])
        self.assertEqual(out, [])  # same scheduled time: no second alert

    def test_ran_running_or_too_early_is_not_missed(self):
        ran = vm(1, last=datetime.datetime(2026, 11, 4, 2, 20))
        running = vm(2, action="Backing up...")
        recent = vm(3, h=4, m=0)  # only 1 h ago
        out, _ = self.run_check([ran, running, recent])
        self.assertEqual(out, [])

    def test_paused_scheduler_never_alerts(self):
        self.assertEqual(alert_ops.check_missed(None, cfg(), [vm(1)], now=self.now, utc_now=self.utc, paused=True), [])


class TestStorage(unittest.TestCase):
    def setUp(self):
        alert_ops._state.update(storage_ok=None, storage_checked=None)

    def step(self, healthy, minutes):
        t = datetime.datetime(2026, 11, 4, 0, 0) + datetime.timedelta(minutes=minutes)
        with patch.object(alert_ops, "send") as send:
            r = alert_ops.check_storage(cfg(), lambda: {"healthy": healthy, "error": None if healthy else "not mounted"}, now=t)
        return r, send.call_count

    def test_transitions(self):
        self.assertEqual(self.step(True, 0), (None, 0))     # starts healthy: quiet
        self.assertEqual(self.step(False, 1), (None, 0))    # within 5 min: not checked
        self.assertEqual(self.step(False, 6), ("down", 1))
        self.assertEqual(self.step(False, 12), (None, 0))   # still down: no repeat
        self.assertEqual(self.step(True, 18), ("up", 1))

    def test_down_at_start_alerts(self):
        self.assertEqual(self.step(False, 0), ("down", 1))


if __name__ == "__main__":
    unittest.main()

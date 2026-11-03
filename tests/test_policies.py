"""Backup policies (services/policy_ops.py) on an in-memory database."""
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, VM, BackupPolicy
from services import policy_ops


class PolicyTestCase(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        self.db = sessionmaker(bind=engine)()
        for name, selected in (("vyos-02", True), ("VMware vCenter Server", True), ("vyos-01", True),
                               ("swift-dental-01", False)):
            self.db.add(VM(vm_name=name, is_selected=selected, schedule_hour=5, schedule_minute=30))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def vm(self, name):
        return self.db.query(VM).filter(VM.vm_name == name).one()

    def policy(self, name):
        return self.db.query(BackupPolicy).filter(BackupPolicy.name == name).one()


class TestDefaults(PolicyTestCase):
    def test_defaults_created_and_selected_vms_join_daily(self):
        policy_ops.ensure_default_policies(self.db)
        names = [p["name"] for p in policy_ops.list_policies(self.db)]
        self.assertEqual(names, ["Daily", "Weekly"])
        daily = self.policy("Daily")
        self.assertEqual(sorted(v.vm_name for v in daily.vms),
                         ["VMware vCenter Server", "vyos-01", "vyos-02"])
        self.assertIsNone(self.vm("swift-dental-01").policy_id)

    def test_selected_vms_are_staggered_by_name(self):
        policy_ops.ensure_default_policies(self.db)
        times = {v.vm_name: (v.schedule_hour, v.schedule_minute) for v in self.policy("Daily").vms}
        self.assertEqual(times, {"VMware vCenter Server": (2, 0), "vyos-01": (2, 5), "vyos-02": (2, 10)})

    def test_idempotent(self):
        policy_ops.ensure_default_policies(self.db)
        policy_ops.ensure_default_policies(self.db)
        self.assertEqual(self.db.query(BackupPolicy).count(), 2)


class TestAssign(PolicyTestCase):
    def setUp(self):
        super().setUp()
        policy_ops.ensure_default_policies(self.db)

    def test_move_to_weekly_restaggers_both_policies(self):
        weekly = self.policy("Weekly")
        policy_ops.assign(self.db, [self.vm("vyos-01").id], weekly.id)
        v = self.vm("vyos-01")
        self.assertEqual((v.schedule_frequency, v.schedule_days, v.schedule_hour, v.schedule_minute),
                         ("weekly", "6", 3, 0))
        # vyos-02 moves up into the slot vyos-01 left in Daily
        self.assertEqual((self.vm("vyos-02").schedule_hour, self.vm("vyos-02").schedule_minute), (2, 5))

    def test_protect_and_unprotect(self):
        dental = self.vm("swift-dental-01")
        policy_ops.assign(self.db, [dental.id], self.policy("Daily").id)
        self.assertTrue(self.vm("swift-dental-01").is_selected)
        policy_ops.assign(self.db, [dental.id], None)
        v = self.vm("swift-dental-01")
        self.assertFalse(v.is_selected)
        self.assertIsNone(v.policy_id)

    def test_unknown_vm(self):
        with self.assertRaises(LookupError):
            policy_ops.assign(self.db, [9999], self.policy("Daily").id)


class TestEdit(PolicyTestCase):
    def setUp(self):
        super().setUp()
        policy_ops.ensure_default_policies(self.db)

    def test_time_change_moves_its_vms(self):
        daily = self.policy("Daily")
        policy_ops.update_policy(self.db, daily.id, {"hour": 23, "minute": 55})
        self.assertEqual((self.vm("VMware vCenter Server").schedule_hour, self.vm("VMware vCenter Server").schedule_minute), (23, 55))
        self.assertEqual((self.vm("vyos-01").schedule_hour, self.vm("vyos-01").schedule_minute), (0, 0))

    def test_delete_refused_while_in_use(self):
        with self.assertRaises(policy_ops.PolicyError):
            policy_ops.delete_policy(self.db, self.policy("Daily").id)
        policy_ops.delete_policy(self.db, self.policy("Weekly").id)
        self.assertEqual(self.db.query(BackupPolicy).count(), 1)

    def test_validation(self):
        with self.assertRaises(policy_ops.PolicyError):
            policy_ops.create_policy(self.db, {"name": "None kept", "keep_daily": 0, "keep_weekly": 0, "keep_monthly": 0})
        with self.assertRaises(policy_ops.PolicyError):
            policy_ops.create_policy(self.db, {"name": "No days", "frequency": "weekly", "days": ""})
        with self.assertRaises(policy_ops.PolicyError):
            policy_ops.create_policy(self.db, {"name": "Daily"})
        with self.assertRaises(policy_ops.PolicyError):
            policy_ops.update_policy(self.db, self.policy("Daily").id, {"hour": 24})

    def test_describe_and_retention(self):
        with patch("time.strftime", return_value="UTC"):
            p = policy_ops.list_policies(self.db)
        self.assertEqual(p[0]["summary"], "Every day 02:00 UTC · keep 7 daily, 4 weekly, 6 monthly")
        self.assertEqual(p[1]["summary"], "Sundays 03:00 UTC · keep 4 weekly, 6 monthly")
        self.assertEqual(policy_ops.retention_for(self.vm("vyos-01")), (7, 4, 6))
        self.assertIsNone(policy_ops.retention_for(self.vm("swift-dental-01")))


if __name__ == "__main__":
    unittest.main()

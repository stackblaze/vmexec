import unittest
from types import SimpleNamespace as NS

from cbt_core import incremental_blocked_reason
from services.backup_ops import vm_to_dict


def _vm(**kw):
    base = dict(id=1, vm_name="vm", esxi_host_id=1, is_selected=True, cpu_count=1, memory_mb=1, storage_gb=1,
                schedule_hour=2, schedule_minute=0, retention_count=7, is_job_active=True, schedule_frequency="daily",
                schedule_days="", last_backup=None, last_backup_duration=0, last_status="Never", progress=0,
                current_action="", power_state="on", power_off_for_backup=False, cbt_enabled=True, esxi_host=None,
                last_secondary_copy_status=None)
    base.update(kw)
    return NS(**base)


class CbtEffectiveTests(unittest.TestCase):
    def test_reasons(self):
        on = NS(cbt_enabled=True)
        self.assertIsNone(incremental_blocked_reason(on, NS(cbt_enabled=True), False))
        self.assertEqual(incremental_blocked_reason(NS(cbt_enabled=False), NS(cbt_enabled=True), False), "CBT disabled in config")
        self.assertEqual(incremental_blocked_reason(on, NS(cbt_enabled=False), False), "CBT disabled for VM")
        self.assertIn("S3", incremental_blocked_reason(on, NS(cbt_enabled=True), True))

    def test_s3_forces_full_even_when_vm_flag_is_on(self):
        d = vm_to_dict(_vm(cbt_enabled=True), config=NS(cbt_enabled=True, storage_type="S3"))
        self.assertTrue(d["cbt_enabled"])
        self.assertFalse(d["cbt_effective"])
        self.assertIn("S3", d["cbt_off_reason"])

    def test_global_switch_forces_full(self):
        d = vm_to_dict(_vm(), config=NS(cbt_enabled=False, storage_type="NFS"))
        self.assertFalse(d["cbt_effective"])

    def test_local_storage_incremental(self):
        d = vm_to_dict(_vm(), config=NS(cbt_enabled=True, storage_type="NFS"))
        self.assertTrue(d["cbt_effective"])
        self.assertIsNone(d["cbt_off_reason"])


if __name__ == "__main__":
    unittest.main()

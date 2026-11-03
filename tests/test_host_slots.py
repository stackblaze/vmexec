"""Per-host backup limit counts ESXi hosts, not the vCenter registration."""
import unittest
from types import SimpleNamespace

import worker


class TestSlots(unittest.TestCase):
    def setUp(self):
        worker._slots_configured = True
        worker._global_limit, worker._host_limit = 10, 2
        worker._global_active = 0
        worker._host_active.clear()

    def vm(self, rh):
        return SimpleNamespace(esxi_host_id=1, runtime_host=rh)

    def test_key_is_the_esxi_host_under_one_vcenter(self):
        self.assertEqual(worker.slot_key(self.vm("dxrhhq2.stackblaze.cloud")), "1:dxrhhq2.stackblaze.cloud")
        self.assertEqual(worker.slot_key(self.vm("")), 1)  # standalone ESXi / not synced yet

    def test_four_hosts_run_eight_at_once(self):
        hosts = ["3kykrp2", "3kylrp2", "5rsp853", "dxrhhq2"]
        got = [worker._try_acquire_slots(worker.slot_key(self.vm(h)))[0] for h in hosts for _ in range(2)]
        self.assertEqual(got, [True] * 8)
        self.assertEqual(worker._try_acquire_slots(worker.slot_key(self.vm("dxrhhq2")))[1], "host")

    def test_global_limit_still_applies(self):
        worker._global_limit = 3
        got = [worker._try_acquire_slots(worker.slot_key(self.vm(h)))[0] for h in ("a", "b", "c", "d")]
        self.assertEqual(got, [True, True, True, False])


if __name__ == "__main__":
    unittest.main()


class TestPlainConfig(unittest.TestCase):
    def test_disk_threads_get_a_plain_copy(self):
        from models import Config
        import cbt_transport
        c = Config(cbt_full_interval=7, backup_transport="nbd")
        p = cbt_transport._plain_config(c)
        self.assertFalse(hasattr(p, "__table__"))
        self.assertEqual((p.cbt_full_interval, p.backup_transport), (7, "nbd"))
        self.assertIsNone(cbt_transport._plain_config(None))

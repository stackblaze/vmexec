import unittest
from unittest.mock import patch

from services import capacity


class _VM:
    def __init__(self, id, name, gb, selected=True, retention=7):
        self.id = id
        self.vm_name = name
        self.storage_gb = gb
        self.is_selected = selected
        self.retention_count = retention


class _DB:
    def __init__(self, vms):
        self._vms = vms

    def query(self, model):
        return self

    def all(self):
        return self._vms


class TestProjectUsage(unittest.TestCase):
    """Steady state ≈ 2 fulls + retention × daily delta, per selected VM."""

    def _project(self, vms, selection=None):
        with patch.object(capacity, "get_storage", side_effect=RuntimeError("no storage")):
            return capacity.project_usage(_DB(vms), config=None, selection=selection)

    def test_formula_with_fallback_delta(self):
        p = self._project([_VM(1, "a", 100.0, retention=7)])
        expected = 2 * 100.0 * capacity.FULL_RATIO + 7 * 100.0 * capacity.DELTA_FALLBACK_PCT
        self.assertAlmostEqual(p["projected_gb"], round(expected, 1))
        self.assertEqual(p["vms"][0]["delta_source"], "estimated")

    def test_unselected_vms_excluded(self):
        p = self._project([_VM(1, "a", 100.0), _VM(2, "b", 500.0, selected=False)])
        self.assertEqual(p["vm_count"], 1)

    def test_selection_override_wins(self):
        vms = [_VM(1, "a", 100.0, selected=False), _VM(2, "b", 50.0, selected=True)]
        p = self._project(vms, selection={1: True, 2: False})
        self.assertEqual([r["vm_name"] for r in p["vms"]], ["a"])

    def test_rows_sorted_by_projection_desc(self):
        p = self._project([_VM(1, "small", 10.0), _VM(2, "big", 500.0)])
        self.assertEqual(p["vms"][0]["vm_name"], "big")

    def test_measured_delta_used_when_available(self):
        with patch.object(capacity, "get_storage", return_value=object()), \
             patch.object(capacity, "_measured_daily_delta_gb", return_value=2.5):
            p = capacity.project_usage(_DB([_VM(1, "a", 100.0, retention=4)]), config=None)
        expected = 2 * 100.0 * capacity.FULL_RATIO + 4 * 2.5
        self.assertAlmostEqual(p["projected_gb"], round(expected, 1))
        self.assertEqual(p["measured_count"], 1)
        self.assertEqual(p["vms"][0]["delta_source"], "measured")


if __name__ == "__main__":
    unittest.main()


class TestDiskExclusion(unittest.TestCase):
    """exclude_disk_patterns skips CNS/FCD disks from backup collection."""

    def test_fcd_prefix_excluded(self):
        import cbt_core
        self.assertTrue(cbt_core.disk_excluded("fcd/abc.vmdk", "fcd/"))
        self.assertFalse(cbt_core.disk_excluded("myvm/myvm.vmdk", "fcd/"))

    def test_multiple_patterns_and_whitespace(self):
        import cbt_core
        self.assertTrue(cbt_core.disk_excluded("scratch/x.vmdk", "fcd/, scratch/"))
        self.assertFalse(cbt_core.disk_excluded("prod/x.vmdk", "fcd/, scratch/"))

    def test_empty_patterns_exclude_nothing(self):
        import cbt_core
        self.assertFalse(cbt_core.disk_excluded("fcd/abc.vmdk", ""))
        self.assertFalse(cbt_core.disk_excluded("fcd/abc.vmdk", None))

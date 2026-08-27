import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cbt_transport
import vsphere_context
import vddk_transport


def _snap_node(children=None):
    return SimpleNamespace(childSnapshotList=children or [])


class TestCountVmSnapshots(unittest.TestCase):
    def test_no_snapshots(self):
        self.assertEqual(vsphere_context.count_vm_snapshots(SimpleNamespace(snapshot=None)), 0)

    def test_single(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=[_snap_node()]))
        self.assertEqual(vsphere_context.count_vm_snapshots(vm), 1)

    def test_nested_tree(self):
        tree = [_snap_node(children=[_snap_node(), _snap_node(children=[_snap_node()])])]
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=tree))
        self.assertEqual(vsphere_context.count_vm_snapshots(vm), 4)


class TestHttpFrozenBaseReader(unittest.TestCase):
    """The VDDK-free extent reader must chunk large areas and keep offsets exact."""

    def setUp(self):
        self.disk = {"rel_path": "vm/vm.vmdk", "ds_name": "ds1"}
        self.reads = []

        def fake_range(si, ds_name, flat_rel, start, length, vm=None, connection_type=None):
            self.reads.append((start, length))
            return b"x" * length

        self.fake_range = fake_range

    def test_small_area_single_read(self):
        extents = cbt_transport._read_extents_http_frozen_base(
            None, None, self.disk, [(0, 4096)], self.fake_range, "vcenter", None)
        self.assertEqual([(0, 4096)], [(o, len(d)) for o, d in extents])

    def test_large_area_is_chunked(self):
        with patch.object(cbt_transport, "HTTP_EXTENT_CHUNK", 1000):
            extents = cbt_transport._read_extents_http_frozen_base(
                None, None, self.disk, [(500, 2500)], self.fake_range, "vcenter", None)
        self.assertEqual([(500, 1000), (1500, 1000), (2500, 500)],
                         [(o, len(d)) for o, d in extents])
        self.assertEqual(self.reads, [(500, 1000), (1500, 1000), (2500, 500)])

    def test_empty_read_raises(self):
        def empty(si, ds, rel, start, length, vm=None, connection_type=None):
            return b""
        with self.assertRaises(RuntimeError):
            cbt_transport._read_extents_http_frozen_base(
                None, None, self.disk, [(0, 10)], empty, "vcenter", None)

    def test_cancel_raises(self):
        with self.assertRaises(RuntimeError):
            cbt_transport._read_extents_http_frozen_base(
                None, None, self.disk, [(0, 10)], self.fake_range, "vcenter", lambda: True)


class TestCaptureDispatch(unittest.TestCase):
    """VDDK when present; frozen-base HTTP when the chain is provably safe; refuse otherwise."""

    def setUp(self):
        self.disk = {"rel_path": "vm/vm.vmdk", "ds_name": "ds1"}
        self.areas = [(0, 4096)]

    def _capture(self, vm):
        def fake_range(si, ds, rel, start, length, vm=None, connection_type=None):
            return b"y" * length
        return cbt_transport._capture_changed_extents(
            None, vm, None, self.disk, self.areas, False,
            "h", "u", "p", None, None, "vcenter", fake_range, None)

    def test_vddk_used_when_available(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=[_snap_node()]))
        with patch.object(vddk_transport, "is_available", return_value=True), \
             patch.object(vddk_transport, "read_snapshot_extents", return_value=[(0, b"z")]) as rse:
            self.assertEqual(self._capture(vm), [(0, b"z")])
        rse.assert_called_once()

    def test_http_used_when_vddk_absent_and_single_snapshot(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=[_snap_node()]))
        with patch.object(vddk_transport, "is_available", return_value=False):
            extents = self._capture(vm)
        self.assertEqual([(0, 4096)], [(o, len(d)) for o, d in extents])

    def test_vddk_runtime_failure_falls_back_to_http_when_safe(self):
        # Installed-but-broken VDDK (e.g. 9.x against vCenter 7) must not fail
        # the backup when the chain guard says HTTP is safe.
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=[_snap_node()]))
        with patch.object(vddk_transport, "is_available", return_value=True), \
             patch.object(vddk_transport, "read_snapshot_extents",
                          side_effect=RuntimeError("nbdkit: vddk: connect refused")):
            extents = self._capture(vm)
        self.assertEqual([(0, 4096)], [(o, len(d)) for o, d in extents])

    def test_vddk_runtime_failure_reraises_when_chain_unsafe(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(
            rootSnapshotList=[_snap_node(children=[_snap_node()])]))
        with patch.object(vddk_transport, "is_available", return_value=True), \
             patch.object(vddk_transport, "read_snapshot_extents",
                          side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError) as ctx:
                self._capture(vm)
        self.assertIn("boom", str(ctx.exception))

    def test_refuses_when_other_snapshots_exist(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(
            rootSnapshotList=[_snap_node(children=[_snap_node()])]))
        with patch.object(vddk_transport, "is_available", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                self._capture(vm)
        self.assertIn("stale", str(ctx.exception))


class TestDiskProgressBands(unittest.TestCase):
    """Progress bands must be weighted by capacity, not disk count."""

    def test_bands_weighted_by_capacity(self):
        gib = 1024 ** 3
        disks = [
            {"capacity_bytes": 100 * gib},
            {"capacity_bytes": 5 * gib},
            {"capacity_bytes": 5 * gib},
        ]
        bands = cbt_transport._disk_progress_bands(disks)
        # 100/110 of the 5..90 span → the large disk owns most of the bar.
        self.assertEqual(bands[0][0], 5)
        self.assertGreaterEqual(bands[0][1], 80)
        self.assertEqual(bands[-1][1], 90)

    def test_bands_contiguous_and_monotonic(self):
        disks = [{"capacity_bytes": c} for c in (7, 1, 3, 9)]
        bands = cbt_transport._disk_progress_bands(disks)
        for (a_base, a_end), (b_base, b_end) in zip(bands, bands[1:]):
            self.assertEqual(a_end, b_base)
            self.assertLessEqual(a_base, a_end)

    def test_missing_capacity_falls_back_to_equal_split(self):
        disks = [{"capacity_bytes": 0}, {}, {"capacity_bytes": None}]
        bands = cbt_transport._disk_progress_bands(disks)
        self.assertEqual(bands[0][0], 5)
        self.assertEqual(bands[-1][1], 90)
        widths = [end - base for base, end in bands]
        self.assertLessEqual(max(widths) - min(widths), 1)

    def test_single_disk_spans_whole_range(self):
        self.assertEqual(
            cbt_transport._disk_progress_bands([{"capacity_bytes": 1}]), [(5, 90)]
        )


class TestFrozenBaseReaderProgress(unittest.TestCase):
    """Byte-level progress from the HTTP extent reader."""

    def test_progress_reaches_band_end(self):
        disk = {"rel_path": "vm/vm.vmdk", "ds_name": "ds1"}

        def fake_range(si, ds_name, flat_rel, start, length, vm=None, connection_type=None):
            return b"x" * length

        seen = []
        cbt_transport._read_extents_http_frozen_base(
            None, None, disk, [(0, 1024), (4096, 1024)], fake_range, None, None,
            progress_callback=seen.append, progress_base=10, progress_total=20,
        )
        self.assertEqual(seen[-1], 30)
        self.assertEqual(seen, sorted(seen))
        self.assertTrue(all(10 <= p <= 30 for p in seen))


class TestCancelPropagation(unittest.TestCase):
    """A user cancel must abort the backup, not degrade to another transport."""

    def test_cancel_during_vddk_read_is_not_retried_over_http(self):
        vm = SimpleNamespace(snapshot=SimpleNamespace(rootSnapshotList=[_snap_node()]))
        cancelled = {"flag": False}

        def read_then_cancel(*a, **k):
            cancelled["flag"] = True
            raise RuntimeError("Backup cancelled by user")

        def fake_range(si, ds, rel, start, length, vm=None, connection_type=None):
            self.fail("HTTP fallback must not run after a cancel")

        with patch.object(vddk_transport, "is_available", return_value=True), \
             patch.object(vddk_transport, "read_snapshot_extents",
                          side_effect=read_then_cancel):
            with self.assertRaises(RuntimeError) as ctx:
                cbt_transport._capture_changed_extents(
                    None, vm, None, {"rel_path": "vm/vm.vmdk", "ds_name": "ds1"},
                    [(0, 4096)], False, "h", "u", "p", None, None, "vcenter",
                    fake_range, lambda: cancelled["flag"])
        self.assertIn("cancelled", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

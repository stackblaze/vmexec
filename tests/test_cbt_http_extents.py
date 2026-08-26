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


if __name__ == "__main__":
    unittest.main()

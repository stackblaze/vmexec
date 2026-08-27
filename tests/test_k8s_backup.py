import base64
import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import backup_manifest as bm
from services import k8s_backup
from storage_util import LocalStorageProvider


class TestResolveTarget(unittest.TestCase):
    def test_kubeadm_profile_fills_defaults(self):
        t = k8s_backup.resolve_target({"name": "mgmt", "profile": "kubeadm"})
        self.assertEqual(t["namespace"], "kube-system")
        self.assertEqual(t["selector"], "component=etcd")
        self.assertTrue(t["cacert"].startswith("/etc/kubernetes/pki/etcd/"))

    def test_overrides_win_over_profile(self):
        t = k8s_backup.resolve_target(
            {"name": "ds", "profile": "kamaji", "namespace": "tenants"})
        self.assertEqual(t["namespace"], "tenants")

    def test_custom_requires_all_fields(self):
        with self.assertRaises(ValueError) as ctx:
            k8s_backup.resolve_target({"name": "x", "profile": "custom"})
        self.assertIn("missing fields", str(ctx.exception))


class TestSnapshotAndPrune(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = LocalStorageProvider(self.tmp.name)
        self.payload = b"fake-etcd-snapshot-bytes" * 100

    def tearDown(self):
        self.tmp.cleanup()

    def _snapshot_once(self):
        def fake_exec(core, ns, pod, container, command, timeout=600):
            if "snapshot save" in command:
                return "", ""
            if "snapshot status" in command:
                return json.dumps({"hash": 42, "revision": 1234, "totalKey": 99}), ""
            if command.startswith("base64"):
                return base64.b64encode(self.payload).decode(), ""
            return "", ""

        with patch.object(k8s_backup, "_find_pod", return_value="etcd-0"), \
             patch.object(k8s_backup, "_exec", side_effect=fake_exec):
            return k8s_backup.snapshot_target(
                None, "kmj", {"name": "mgmt", "profile": "kubeadm"},
                self.storage, retention_count=3)

    def test_snapshot_stores_point_with_manifest(self):
        point = self._snapshot_once()
        name = k8s_backup.chain_name("kmj", "mgmt")
        chain = bm.load_chain(self.storage, name)
        self.assertEqual(chain["latest"], point)
        manifest = bm.load_manifest(self.storage, name, point)
        self.assertEqual(manifest["type"], "etcd_snapshot")
        self.assertEqual(manifest["size_bytes"], len(self.payload))
        self.assertEqual(manifest["sha256"],
                         hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(manifest["etcd_status"]["revision"], 1234)
        snap = os.path.join(self.tmp.name, name, "_chain", "points", point, "snapshot.db")
        self.assertEqual(open(snap, "rb").read(), self.payload)

    def test_prune_keeps_newest_n(self):
        points = [self._snapshot_once() for _ in range(5)]
        name = k8s_backup.chain_name("kmj", "mgmt")
        chain = bm.load_chain(self.storage, name)
        self.assertEqual(len(chain["points"]), 3)
        kept = [p["id"] for p in chain["points"]]
        self.assertEqual(kept, points[-3:])
        for pid in points[:2]:
            self.assertFalse(self.storage.exists(bm.point_rel(name, pid)))

    def test_empty_transfer_raises(self):
        def fake_exec(core, ns, pod, container, command, timeout=600):
            if command.startswith("base64"):
                return "", ""
            if "snapshot status" in command:
                return "{}", ""
            return "", ""
        with patch.object(k8s_backup, "_find_pod", return_value="etcd-0"), \
             patch.object(k8s_backup, "_exec", side_effect=fake_exec):
            with self.assertRaises(RuntimeError):
                k8s_backup.snapshot_target(
                    None, "kmj", {"name": "mgmt", "profile": "kubeadm"},
                    self.storage, retention_count=3)


if __name__ == "__main__":
    unittest.main()


class TestK3sProfile(unittest.TestCase):
    def test_k3s_profile_uses_hostpath_not_secret(self):
        t = k8s_backup.resolve_target({"name": "mgmt", "profile": "k3s"})
        self.assertEqual(t["host_certs_dir"], "/var/lib/rancher/k3s/server/tls/etcd")
        self.assertTrue(t["host_network"])
        self.assertEqual(t["node_selector"], {"node-role.kubernetes.io/etcd": "true"})
        self.assertNotIn("certs_secret", t)

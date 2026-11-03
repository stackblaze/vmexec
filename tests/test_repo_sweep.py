"""repo_sweep: leftovers of interrupted backups/restores are removed, nothing else."""
import json
import os
import tempfile
import time
import unittest

import repo_sweep


class Storage:
    def __init__(self, root):
        self.root = root

    def _full_path(self, p):
        return os.path.join(self.root, p)

    def exists(self, p):
        return os.path.exists(self._full_path(p))

    def list_dirs(self, p):
        full = self._full_path(p)
        return sorted(d for d in os.listdir(full) if os.path.isdir(os.path.join(full, d))) if os.path.isdir(full) else []

    def delete_dir(self, p):
        import shutil
        shutil.rmtree(self._full_path(p), ignore_errors=True)

    def open_read(self, p):
        return open(self._full_path(p), "rb")


class TestSweep(unittest.TestCase):
    def setUp(self):
        self.st = Storage(tempfile.mkdtemp())
        for pid in ("p-good", "p-orphan"):
            os.makedirs(self.st._full_path(f"vm/_chain/points/{pid}"))
        os.makedirs(self.st._full_path("vm/_chain/points/p-good/_materialized"))
        with open(self.st._full_path("vm/_chain/chain.json"), "w") as f:
            json.dump({"vm_name": "vm", "points": [{"id": "p-good", "type": "full", "parent": None}]}, f)
        old = time.time() - 3600
        for rel in ("vm/_chain/points/p-orphan", "vm/_chain/points/p-good/_materialized"):
            os.utime(self.st._full_path(rel), (old, old))

    def test_removes_orphan_point_and_materialized_only(self):
        removed = repo_sweep.sweep_repository(self.st, running_vm_names=set())
        self.assertEqual(sorted(removed), ["vm/_chain/points/p-good/_materialized", "vm/_chain/points/p-orphan"])
        self.assertTrue(self.st.exists("vm/_chain/points/p-good"))

    def test_running_vm_and_young_folders_untouched(self):
        self.assertEqual(repo_sweep.sweep_repository(self.st, running_vm_names={"vm"}), [])
        self.assertEqual(repo_sweep.sweep_repository(self.st, set(), min_age=7200), [])
        self.assertTrue(self.st.exists("vm/_chain/points/p-orphan"))


if __name__ == "__main__":
    unittest.main()

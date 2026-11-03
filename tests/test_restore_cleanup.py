"""A restore removes the temporary rebuilt disk (_materialized), success or failure."""
import unittest
from unittest.mock import MagicMock, patch

import backup_engine


class TestRestoreCleanup(unittest.TestCase):
    def _run(self, fail):
        storage = MagicMock()
        si = MagicMock()
        if fail:
            si.RetrieveContent.side_effect = RuntimeError("vCenter gone")
        with patch("chain_restore.resolve_restore_source", return_value=("vm/_chain/points/p/_materialized",
                                                                         "vm/_chain/points/p/_materialized")):
            if fail:
                # resolve runs after RetrieveContent; make RetrieveContent pass and fail later instead
                si.RetrieveContent.side_effect = None
                si.RetrieveContent.return_value.rootFolder.childEntity = []
            ok, _ = backup_engine.import_vm_native(si, storage, "vm/_chain/points/p", "ds", "copy")
        return ok, storage

    def test_temporary_disk_removed_when_restore_fails(self):
        ok, storage = self._run(fail=True)
        self.assertFalse(ok)
        storage.delete_dir.assert_called_with("vm/_chain/points/p/_materialized")


if __name__ == "__main__":
    unittest.main()

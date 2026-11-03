"""Preflight must not change the VM's configuration (it froze vault-us-central-1)."""
import unittest
from unittest.mock import MagicMock, patch

import backup_engine


class TestPreflight(unittest.TestCase):
    def test_no_reconfigure_of_the_vm(self):
        vm = MagicMock()
        vm.config.files.vmPathName = "[ds] vault/vault.vmx"
        with patch.object(backup_engine, "_get_vm", return_value=vm), \
             patch.object(backup_engine, "_cleanup_stale_temp_dirs"), \
             patch.object(backup_engine, "_remove_stale_snapshots", return_value=True), \
             patch.object(backup_engine, "_handle_consolidation", return_value=True), \
             patch.object(backup_engine, "_is_infra_vm", return_value=False):
            backup_engine.preflight_check(MagicMock(), "vault-us-central-1")
        vm.ReconfigVM_Task.assert_not_called()
        self.assertFalse(hasattr(backup_engine, "_disconnect_removable_devices"))


if __name__ == "__main__":
    unittest.main()

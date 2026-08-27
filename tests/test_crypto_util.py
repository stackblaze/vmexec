import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class TestCryptoUtil(unittest.TestCase):
    """Credentials for OTHER systems must not sit in the DB in the clear."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {"DATA_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        import crypto_util
        crypto_util._fernet = None
        crypto_util.KEY_FILE = os.path.join(self.tmp.name, "secret.key")
        self.crypto = crypto_util

    def test_roundtrip(self):
        self.assertEqual(self.crypto.decrypt(self.crypto.encrypt("Fr03en33#")), "Fr03en33#")

    def test_ciphertext_does_not_contain_the_secret(self):
        token = self.crypto.encrypt("hunter2")
        self.assertNotIn("hunter2", token)
        self.assertTrue(token.startswith(self.crypto.PREFIX))

    def test_empty_and_none_pass_through(self):
        for value in ("", None):
            self.assertEqual(self.crypto.encrypt(value), value)
            self.assertEqual(self.crypto.decrypt(value), value)

    def test_legacy_plaintext_reads_back_unchanged(self):
        # An upgraded DB is full of untagged plaintext; it must stay readable.
        self.assertEqual(self.crypto.decrypt("plaintext-from-v1"), "plaintext-from-v1")

    def test_encrypt_is_idempotent(self):
        once = self.crypto.encrypt("s3cret")
        self.assertEqual(self.crypto.encrypt(once), once)

    def test_key_file_is_not_world_readable(self):
        self.crypto.encrypt("x")  # forces key creation
        mode = os.stat(self.crypto.KEY_FILE).st_mode & 0o777
        self.assertEqual(mode, 0o600, f"key file mode {oct(mode)} should be 0o600")

    def test_wrong_key_degrades_instead_of_crashing(self):
        token = self.crypto.encrypt("secret")
        from cryptography.fernet import Fernet
        self.crypto._fernet = Fernet(Fernet.generate_key())
        self.assertEqual(self.crypto.decrypt(token), "")

    def test_env_key_overrides_file(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {self.crypto.KEY_ENV: key}):
            self.crypto._fernet = None
            token = self.crypto.encrypt("via-env")
            self.crypto._fernet = None
            self.assertEqual(self.crypto.decrypt(token), "via-env")

    def test_migrate_plaintext_secrets(self):
        db = os.path.join(self.tmp.name, "backup_system.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE esxi_hosts (id INTEGER PRIMARY KEY, password TEXT)")
        conn.execute("INSERT INTO esxi_hosts (id, password) VALUES (1, 'plaintext-pw')")
        conn.commit(); conn.close()

        n = self.crypto.migrate_plaintext_secrets(db)
        self.assertEqual(n, 1)

        conn = sqlite3.connect(db)
        stored = conn.execute("SELECT password FROM esxi_hosts WHERE id=1").fetchone()[0]
        conn.close()
        self.assertNotIn("plaintext-pw", stored)
        self.assertEqual(self.crypto.decrypt(stored), "plaintext-pw")

    def test_migrate_is_idempotent(self):
        db = os.path.join(self.tmp.name, "backup_system.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE esxi_hosts (id INTEGER PRIMARY KEY, password TEXT)")
        conn.execute("INSERT INTO esxi_hosts (id, password) VALUES (1, 'pw')")
        conn.commit(); conn.close()
        self.assertEqual(self.crypto.migrate_plaintext_secrets(db), 1)
        self.assertEqual(self.crypto.migrate_plaintext_secrets(db), 0)

    def test_migrate_tolerates_missing_tables(self):
        db = os.path.join(self.tmp.name, "backup_system.db")
        sqlite3.connect(db).close()
        self.assertEqual(self.crypto.migrate_plaintext_secrets(db), 0)


class TestSmbPathValidation(unittest.TestCase):
    """SMB and NFS both resolve to a local path; a UNC path cannot work on posix."""

    def setUp(self):
        import storage_util
        self.storage = storage_util

    def test_unc_rejected_on_posix(self):
        with patch("storage_util.os.name", "posix"):
            problem = self.storage.check_smb_path(r"\\server\share\backups")
        self.assertIsNotNone(problem)
        self.assertIn("UNC", problem)
        self.assertIn("/mnt/backups", problem)

    def test_unc_allowed_on_windows(self):
        with patch("storage_util.os.name", "nt"):
            self.assertIsNone(self.storage.check_smb_path(r"\\server\share\backups"))

    def test_mounted_path_accepted(self):
        with patch("storage_util.os.name", "posix"):
            self.assertIsNone(self.storage.check_smb_path("/mnt/backups"))

    def test_empty_path_reported(self):
        self.assertIsNotNone(self.storage.check_smb_path(""))


if __name__ == "__main__":
    unittest.main()

import os
import stat
import tempfile
import unittest
from unittest import mock

import auth


class SessionSecretTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key_file = os.path.join(self.tmp.name, "session.key")
        patcher = mock.patch.object(auth, "SESSION_KEY_FILE", self.key_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_not_the_old_public_constant(self):
        self.assertNotEqual(auth.SECRET_KEY, "super-secure-backup-manager-secret")

    def test_generates_once_with_0600_and_reuses(self):
        with mock.patch.dict(os.environ, {auth.SESSION_KEY_ENV: ""}):
            first = auth._load_or_create_session_secret()
            second = auth._load_or_create_session_secret()
        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 48)
        self.assertEqual(stat.S_IMODE(os.stat(self.key_file).st_mode), 0o600)

    def test_env_overrides_file(self):
        with mock.patch.dict(os.environ, {auth.SESSION_KEY_ENV: "from-env"}):
            self.assertEqual(auth._load_or_create_session_secret(), "from-env")
        self.assertFalse(os.path.exists(self.key_file))

    def test_token_signed_with_old_constant_is_rejected(self):
        from jose import jwt
        forged = jwt.encode({"sub": "admin"}, "super-secure-backup-manager-secret", algorithm=auth.ALGORITHM)
        self.assertIsNone(auth.decode_access_token(forged))

    def test_session_token_round_trip(self):
        self.assertEqual(auth.decode_access_token(auth.create_access_token("admin")), "admin")

    def test_mfa_pending_token_is_not_a_session(self):
        pending = auth.create_mfa_pending_token("admin")
        self.assertIsNone(auth.decode_access_token(pending))
        self.assertEqual(auth.decode_mfa_pending_token(pending), "admin")


if __name__ == "__main__":
    unittest.main()

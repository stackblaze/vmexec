"""services/appliance_setup.py: the database copy install.sh --recover restores."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import appliance_setup


class TestCopyDb(unittest.TestCase):
    def test_copies_db_and_keys_0600(self):
        data = tempfile.mkdtemp()
        dest = os.path.join(tempfile.mkdtemp(), "_appliance")
        with sqlite3.connect(os.path.join(data, "backup_system.db")) as c:
            c.execute("create table t (x)")
            c.execute("insert into t values (42)")
        for k in ("secret.key", "session.key"):
            with open(os.path.join(data, k), "w") as f:
                f.write("k")
        with patch.object(appliance_setup, "DATA_DIR", data):
            appliance_setup.copy_db(dest)
            appliance_setup.copy_db(dest)  # again: replaces, no leftovers
        self.assertEqual(sorted(os.listdir(dest)), ["backup_system.db", "secret.key", "session.key"])
        with sqlite3.connect(os.path.join(dest, "backup_system.db")) as c:
            self.assertEqual(c.execute("select x from t").fetchone(), (42,))
        for f in os.listdir(dest):
            self.assertEqual(os.stat(os.path.join(dest, f)).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()

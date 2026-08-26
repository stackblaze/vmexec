"""
crypto_util.py — encryption at rest for third-party credentials.

The database stores credentials that belong to OTHER systems: vCenter/ESXi
logins, SMB and S3 keys, SMTP and IMAP passwords. Unlike a user password these
cannot be hashed, because the backup engine has to replay them verbatim. They
were previously written to SQLite in the clear, which made data/backup_system.db
equivalent to the vSphere estate it protects — anyone who could read the file,
a stray copy, or a backup of the appliance itself held every host credential.

Values are encrypted with Fernet (AES-128-CBC + HMAC, from `cryptography`,
already a dependency) and tagged with a version prefix so plaintext written by
earlier versions is still readable. Nothing has to be migrated up front: a
legacy value reads back as-is and is re-written encrypted the next time it is
saved. migrate_plaintext_secrets() below does it eagerly.

KEY MANAGEMENT
    The key lives in data/secret.key, created 0600 on first use. Set
    VMEXEC_SECRET_KEY to supply it from a secret store / Docker secret instead,
    which is what you want if data/ is on shared or replicated storage.

    Losing the key means losing the stored credentials — they must be re-entered.
    It does NOT affect existing backups, which are not encrypted with it.
"""

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from config_env import DATA_DIR
from logger_util import log_info, log_warn

# Version tag, so the column can hold both encrypted and legacy plaintext and
# a future scheme can be told apart from this one.
PREFIX = "enc:v1:"
KEY_FILE = os.path.join(DATA_DIR, "secret.key")
KEY_ENV = "VMEXEC_SECRET_KEY"

_fernet = None


def _load_or_create_key():
    env_key = os.environ.get(KEY_ENV, "").strip()
    if env_key:
        return env_key.encode()

    if os.path.isfile(KEY_FILE):
        with open(KEY_FILE, "rb") as fh:
            key = fh.read().strip()
        if key:
            return key
        log_warn(f"[CRYPTO] {KEY_FILE} is empty; generating a new key")

    key = Fernet.generate_key()
    # Create with 0600 from the outset rather than chmod-ing afterwards, so the
    # key is never briefly world-readable on a shared box.
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    log_info(f"[CRYPTO] Generated credential encryption key at {KEY_FILE} (0600). "
             f"Back it up: without it, stored credentials must be re-entered.")
    return key


def get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value):
    """Encrypt a str. None and "" pass through so empty config stays empty."""
    if value is None or value == "":
        return value
    if is_encrypted(value):
        return value
    token = get_fernet().encrypt(str(value).encode()).decode()
    return PREFIX + token


def decrypt(value):
    """
    Decrypt a tagged value. Untagged input is plaintext from an older version
    and is returned unchanged, which is what makes the upgrade seamless.
    """
    if value is None or value == "":
        return value
    if not is_encrypted(value):
        return value
    try:
        return get_fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        # Wrong or replaced key. Returning "" rather than raising keeps the app
        # usable — the affected credential simply has to be re-entered.
        log_warn("[CRYPTO] Could not decrypt a stored credential — the key in "
                 f"{KEY_FILE} does not match the one it was written with. "
                 "Re-enter that credential to repair it.")
        return ""


class EncryptedString(TypeDecorator):
    """A String column encrypted on write and decrypted on read."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)


# Columns holding third-party credentials, as (table, column) pairs. Used by the
# eager migration below. User.hashed_password is deliberately absent: it is a
# bcrypt hash, verified not replayed, and must not be encrypted.
SECRET_COLUMNS = [
    ("esxi_hosts", "password"),
    ("config", "smb_password"),
    ("config", "smtp_password"),
    ("config", "imap_password"),
    ("config", "s3_secret_key"),
    ("config", "secondary_smb_password"),
    ("config", "secondary_s3_secret_key"),
]


def migrate_plaintext_secrets(db_path):
    """
    Encrypt any credential still stored in the clear.

    Runs at startup. Reads and writes raw SQL rather than going through the ORM
    so it sees the stored bytes, not the decrypted view of them.
    """
    import sqlite3

    if not os.path.exists(db_path):
        return 0

    migrated = 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for table, column in SECRET_COLUMNS:
            try:
                cur.execute(f"SELECT id, {column} FROM {table}")
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                continue  # column/table not present in this schema version
            for row_id, value in rows:
                if not value or is_encrypted(value):
                    continue
                cur.execute(
                    f"UPDATE {table} SET {column} = ? WHERE id = ?",
                    (encrypt(value), row_id),
                )
                migrated += 1
        if migrated:
            conn.commit()
            log_info(f"[CRYPTO] Encrypted {migrated} credential(s) previously "
                     f"stored in plaintext.")
    finally:
        conn.close()
    return migrated

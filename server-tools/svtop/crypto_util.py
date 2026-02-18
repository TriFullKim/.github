"""Password encryption/decryption utility using Fernet symmetric encryption.

Passwords are encrypted with a machine-local key stored in .secret_key file.
This allows storing SSH passwords securely in config.yaml.
"""

import os
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")


def _get_or_create_key() -> bytes:
    """Load or generate a Fernet key stored locally."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read().strip()
    # Generate a new key
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    os.chmod(KEY_FILE, 0o600)  # owner read/write only
    logger.info("Generated new encryption key at .secret_key")
    return key


def encrypt_password(plaintext: str) -> str:
    """Encrypt a password and return base64-encoded ciphertext."""
    key = _get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_password(encrypted: str) -> str:
    """Decrypt an encrypted password back to plaintext."""
    key = _get_or_create_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode("utf-8"))
    return decrypted.decode("utf-8")

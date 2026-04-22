"""
security.py – Fernet encryption helpers for private keys.

Private keys are NEVER stored in plaintext.  They are always encrypted with
the ENCRYPTION_KEY from the environment before being written to the database,
and decrypted only when a signing operation requires them.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """Return a Fernet cipher using the key from the environment."""
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_key(plain_key: str) -> str:
    """Encrypt a private key string and return the ciphertext as a string."""
    fernet = _get_fernet()
    return fernet.encrypt(plain_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    """Decrypt a previously encrypted private key and return the plaintext."""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(encrypted_key.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt private key – invalid token or key.") from exc

"""Symmetric encryption for storing sensitive values (API keys) in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed from the app SECRET_KEY.
The key is derived via PBKDF2-HMAC-SHA256 with a fixed salt so it is
deterministic across restarts.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    from app.core.config import get_settings
    secret = get_settings().SECRET_KEY.encode()
    # Derive a 32-byte key from SECRET_KEY, then base64-url-encode for Fernet
    derived = hashlib.pbkdf2_hmac("sha256", secret, b"scenecraft-ai-salt", iterations=100_000)
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a base64-encoded ciphertext string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string produced by encrypt()."""
    return _fernet().decrypt(ciphertext.encode()).decode()

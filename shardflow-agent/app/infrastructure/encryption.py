"""AES-256-GCM encryption/decryption matching Java AesEncryptionUtil.

Master key loaded from SF_MODEL_KEY_MASTER environment variable.
"""
import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_master_key: bytes | None = None


def _get_master_key() -> bytes:
    global _master_key
    if _master_key is not None:
        return _master_key
    key_b64 = os.getenv("SF_MODEL_KEY_MASTER")
    if not key_b64:
        raise RuntimeError("SF_MODEL_KEY_MASTER environment variable is not set")
    key_bytes = base64.b64decode(key_b64)
    if len(key_bytes) != 32:
        raise ValueError("SF_MODEL_KEY_MASTER must decode to 32 bytes (256 bits)")
    _master_key = key_bytes
    return _master_key


def decrypt(encrypted: str) -> str:
    """Decrypt a base64-encoded AES-256-GCM ciphertext (IV prepended)."""
    combined = base64.b64decode(encrypted)
    iv = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(_get_master_key())
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode("utf-8")


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext with AES-256-GCM, returning base64(IV + ciphertext)."""
    iv = secrets.token_bytes(12)
    aesgcm = AESGCM(_get_master_key())
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    combined = iv + ciphertext
    return base64.b64encode(combined).decode("ascii")


def mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]

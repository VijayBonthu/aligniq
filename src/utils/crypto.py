"""Symmetric encryption for secrets at rest (e.g. stored OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC). The key comes from JIRA_TOKEN_ENC_KEY when set
(a urlsafe-base64 32-byte Fernet key, rotatable independently in prod); otherwise it
is derived deterministically from SECRET_KEY_J so encryption is on in every environment
with zero extra config.

Ciphertext is stored with an `enc:v1:` prefix so decrypt_secret() can transparently
pass through any legacy plaintext value (no data migration needed).
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from config import settings

_PREFIX = "enc:v1:"


def _build_fernet() -> Fernet:
    key = getattr(settings, "JIRA_TOKEN_ENC_KEY", None)
    if key:
        # Expect a valid urlsafe-base64 32-byte Fernet key.
        return Fernet(key if isinstance(key, bytes) else key.encode())
    # Derive a stable 32-byte key from the app secret.
    secret = (settings.SECRET_KEY_J or "").encode()
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(derived)


# Build once at import — the key is stable for the process lifetime.
_fernet = _build_fernet()


def encrypt_secret(plaintext) -> str:
    """Encrypt a secret string for storage. Returns an `enc:v1:`-prefixed token.
    Passes through falsy values unchanged (None/'' stay as-is)."""
    if not plaintext:
        return plaintext
    token = _fernet.encrypt(str(plaintext).encode()).decode()
    return _PREFIX + token


def decrypt_secret(value):
    """Decrypt a value produced by encrypt_secret. Values without the `enc:v1:`
    prefix are returned unchanged (legacy plaintext / None)."""
    if not value or not isinstance(value, str) or not value.startswith(_PREFIX):
        return value
    return _fernet.decrypt(value[len(_PREFIX):].encode()).decode()

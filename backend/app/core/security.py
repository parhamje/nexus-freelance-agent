"""Password hashing, credential encryption and signed tokens (stdlib + cryptography)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


# --------------------------------------------------------------------------- #
# Credential encryption (Fernet, authenticated symmetric)                     #
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    if settings.encryption_key:
        key = settings.encryption_key.encode()
    else:
        digest = hashlib.sha256(settings.secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(value: str) -> str:
    if value is None:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    tail = value[-4:] if len(value) >= 4 else value
    return "••••" + tail


# --------------------------------------------------------------------------- #
# Password hashing (scrypt)                                                   #
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Signed access tokens (HMAC-SHA256, no external dependency)                  #
# --------------------------------------------------------------------------- #
def _sign(payload: bytes) -> str:
    return hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()


def create_access_token(subject: str, extra: dict | None = None) -> str:
    payload = {
        "sub": subject,
        "exp": int(time.time()) + settings.access_token_expire_minutes * 60,
        **(extra or {}),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return raw + "." + _sign(raw.encode())


def decode_access_token(token: str) -> dict | None:
    try:
        raw, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(_sign(raw.encode()), sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

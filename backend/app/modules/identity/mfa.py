"""RFC 6238 TOTP, encrypted at rest; counters cannot be replayed."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.config import settings


def cipher():
    key = settings().mfa_encryption_key
    if not key:
        raise HTTPException(503, "MFA key management is not configured")
    return Fernet(key.encode())


def code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def enroll(user):
    if user.mfa_enabled:
        raise HTTPException(
            409, "MFA is already enabled; recovery requires a separately verified process"
        )
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    user.mfa_secret = cipher().encrypt(secret.encode()).decode()
    user.mfa_last_counter = -1
    return {
        "secret": secret,
        "uri": f"otpauth://totp/AuditOS:{quote(user.email)}?secret={secret}&issuer=AuditOS&algorithm=SHA1&digits=6&period=30",
    }


def verify(user, supplied: str):
    if (
        not user.mfa_secret
        or len(supplied) != 6
        or not supplied.isascii()
        or not supplied.isdigit()
    ):
        raise HTTPException(401, "Invalid authenticator code")
    secret = cipher().decrypt(user.mfa_secret.encode()).decode()
    now = int(time.time()) // 30
    for counter in (now, now - 1, now + 1):
        if counter > user.mfa_last_counter and hmac.compare_digest(code(secret, counter), supplied):
            user.mfa_last_counter = counter
            return
    raise HTTPException(401, "Invalid or replayed authenticator code")

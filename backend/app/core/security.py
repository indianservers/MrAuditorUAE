import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token() -> str:
    return secrets.token_urlsafe(48)


def access_token(user_id: uuid.UUID, session_id: uuid.UUID | None = None, mfa: bool = False) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings().access_minutes),
            "iss": "auditos",
            "aud": "auditos-api",
            "type": "access",
            **({"sid": str(session_id), "mfa": mfa} if session_id else {}),
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> uuid.UUID:
    return uuid.UUID(decode_claims(token)["sub"])


def decode_claims(token: str) -> dict:
    data = jwt.decode(
        token,
        settings().jwt_secret,
        algorithms=["HS256"],
        audience="auditos-api",
        issuer="auditos",
        options={"require": ["exp", "sub", "iat"]},
    )
    if data.get("type") != "access":
        raise ValueError("Invalid token type")
    return data

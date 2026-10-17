import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def cipher() -> Fernet:
    key = settings().connector_encryption_key
    if not key:
        raise ValueError("CONNECTOR_ENCRYPTION_KEY is required for connector credential storage")
    return Fernet(key.encode())


def encrypt(values: dict) -> str:
    return cipher().encrypt(json.dumps(values).encode()).decode()


def decrypt(value: str) -> dict:
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except InvalidToken:
        raise ValueError("Connector credentials cannot be decrypted") from None

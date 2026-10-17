import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import (
    access_token,
    decode_token,
    digest,
    hash_password,
    refresh_token,
    verify_password,
)
from app.modules.clients.schemas import ClientCreate, EntityCreate, PeriodCreate


@pytest.mark.parametrize("password", ["correct horse battery staple", "unicode-password-é€"])
def test_argon2(password):
    encoded = hash_password(password)
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded)
    assert not verify_password("wrong", encoded)


def test_malformed_hash():
    assert not verify_password("secret", "broken")


def test_random_refresh_and_digest():
    first, second = refresh_token(), refresh_token()
    assert first != second
    assert len(first) >= 48 and len(digest(first)) == 64 and first != digest(first)


def test_access_roundtrip():
    user = uuid.uuid4()
    assert decode_token(access_token(user)) == user


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"aud": "other-service"},
        {"iss": "other-issuer"},
        {"type": "refresh"},
        {"sub": "not-a-uuid"},
    ],
)
def test_access_claim_validation(claims):
    payload = {
        "sub": str(uuid.uuid4()),
        "exp": datetime.now(UTC) + timedelta(minutes=1),
        "iat": datetime.now(UTC),
        "aud": "auditos-api",
        "iss": "auditos",
        "type": "access",
    }
    payload.update(claims)
    raw = jwt.encode(payload, settings().jwt_secret, algorithm="HS256")
    with pytest.raises((jwt.InvalidTokenError, ValueError)):
        decode_token(raw)


def test_signature_and_missing_claims():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(
            jwt.encode(
                {"sub": str(uuid.uuid4())},
                "other-key-with-sufficient-length-12345",
                algorithm="HS256",
            )
        )


def test_platform_role_cannot_read_clients():
    assert ROLE_PERMISSIONS["Platform Administrator"] == ["platform.manage"]
    assert "clients.write" not in ROLE_PERMISSIONS["Client Viewer"]


def test_production_config_rejects_bootstrap():
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="x" * 64, bootstrap_secret="enabled")


def test_period_range():
    with pytest.raises(ValidationError):
        PeriodCreate(entity_id=uuid.uuid4(), start_date="2026-12-31", end_date="2026-01-01")


@pytest.mark.parametrize("field,value", [("code", "bad code"), ("name", ""), ("kind", "unknown")])
def test_client_validation(field, value):
    data = {"code": "TEST", "name": "Test client"}
    data[field] = value
    with pytest.raises(ValidationError):
        ClientCreate(**data)


def test_currency_and_country_validation():
    with pytest.raises(ValidationError):
        EntityCreate(
            client_id=uuid.uuid4(),
            name="Test",
            country="UAE",
            jurisdiction="Test",
            functional_currency="aed",
            presentation_currency="AED",
        )


@pytest.mark.parametrize("field,value", [("country", "ZZ"), ("functional_currency", "ZZZ")])
def test_unknown_iso_codes(field, value):
    data = {
        "client_id": uuid.uuid4(),
        "name": "Test",
        "country": "AE",
        "jurisdiction": "Test",
        "functional_currency": "AED",
        "presentation_currency": "USD",
    }
    data[field] = value
    with pytest.raises(ValidationError):
        EntityCreate(**data)

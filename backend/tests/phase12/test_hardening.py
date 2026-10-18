import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, settings
from app.modules.enterprise_ai.documents import match_signals, validate_corrections
from app.modules.identity.mfa import code, enroll, verify
from app.modules.saas.service import writable
from tests.integration.test_platform import environment as environment
from tests.integration.test_platform import setup


def test_totp_rfc6238_known_vector_and_replay(monkeypatch):
    # RFC 6238 appendix B, SHA1 vector at timestamp 59, truncated to six digits.
    assert code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1) == "287082"
    monkeypatch.setattr(settings(), "mfa_encryption_key", Fernet.generate_key().decode())
    user = SimpleNamespace(
        email="test@example.test", mfa_enabled=False, mfa_secret=None, mfa_last_counter=-1
    )
    enrollment = enroll(user)
    assert enrollment["secret"] not in user.mfa_secret
    import time

    counter = int(time.time()) // 30
    current = code(enrollment["secret"], counter)
    verify(user, current)
    with pytest.raises(HTTPException):
        verify(user, current)
    assert user.mfa_last_counter == counter


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "NaN"),
        ("amount", "Infinity"),
        ("amount", "oops"),
        ("tax_amount", "1e100"),
        ("date", "2026-02-30"),
        ("currency", "ZZZ"),
        ("amount", "0.0000000001"),
    ],
)
def test_invalid_correction_rejected(field, value):
    with pytest.raises(HTTPException) as exc:
        validate_corrections({field: value})
    assert exc.value.status_code == 422


def test_legacy_invalid_amount_does_not_crash_matching():
    for value in ["oops", "NaN", "Infinity"]:
        assert not match_signals({"amount": {"value": value}}, {"debit": "100", "credit": "0"})[
            "signals"
        ]["amount"]


@pytest.mark.parametrize("flag", ["synthetic_data_enabled", "demo_database_name", "demo_tenant_id"])
def test_production_demo_configuration_forbidden(flag):
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://test/test",
            environment="production",
            jwt_secret="x" * 64,
            bootstrap_secret="",
            mfa_encryption_key=Fernet.generate_key().decode(),
            **{flag: True if flag == "synthetic_data_enabled" else "demo"},
        )


def test_subscription_expiry_grace_and_cancellation():
    now = datetime.now(UTC)
    subscription = SimpleNamespace(
        status="active", valid_until=now - timedelta(seconds=1), grace_until=now + timedelta(days=1)
    )
    assert not writable(subscription, now)
    subscription.status = "past_due"
    assert writable(subscription, now)
    subscription.status = "cancelled"
    assert not writable(subscription, now)


integration = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated PostgreSQL required"
)


@integration
async def test_logout_immediately_revokes_access(environment):
    c = environment
    h, tokens = await setup(c)
    assert (await c.get("/api/v1/auth/me", headers=h)).status_code == 200
    assert (
        await c.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    assert (await c.get("/api/v1/auth/me", headers=h)).status_code == 401


@integration
async def test_mfa_enrollment_login_replay_and_platform_boundary(environment, monkeypatch):
    import time

    from app.db.models.platform import User
    from app.db.session import Session
    from app.modules.saas.models import PlatformOperator

    c = environment
    h, _ = await setup(c)
    monkeypatch.setattr(settings(), "mfa_encryption_key", Fernet.generate_key().decode())
    assert (await c.get("/api/v1/platform/tenants", headers=h)).status_code == 403
    result = await c.post(
        "/api/v1/auth/mfa/enroll", headers=h, json={"password": "test-strong-password-123"}
    )
    assert result.status_code == 200
    secret = result.json()["secret"]
    counter = int(time.time()) // 30
    result = await c.post(
        "/api/v1/auth/mfa/confirm", headers=h, json={"code": code(secret, counter)}
    )
    assert result.status_code == 200
    assert (await c.get("/api/v1/auth/me", headers=h)).status_code == 401
    credentials = {"username": "admin@example.com", "password": "test-strong-password-123"}
    assert (await c.post("/api/v1/auth/login", data=credentials)).status_code == 401
    monkeypatch.setattr("app.modules.identity.mfa.time.time", lambda: (counter + 1) * 30)
    credentials["otp"] = code(secret, counter + 1)
    login = await c.post("/api/v1/auth/login", data=credentials)
    assert login.status_code == 200
    assert (await c.post("/api/v1/auth/login", data=credentials)).status_code == 401
    verified = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert (await c.get("/api/v1/platform/tenants", headers=verified)).status_code == 403
    async with Session() as db, db.begin():
        user = await db.scalar(select(User).where(User.email == credentials["username"]))
        db.add(PlatformOperator(user_id=user.id, active=True))
    assert (await c.get("/api/v1/platform/tenants", headers=verified)).status_code == 200
    # A platform grant does not confer membership in another tenant.
    assert (
        await c.get("/api/v1/clients", headers={**verified, "X-Tenant-ID": str(uuid.uuid4())})
    ).status_code == 403


@integration
async def test_tenant_entitlements_quota_readonly_and_forced_rls(environment):
    from app.db.session import Session, tenant_context
    from app.modules.saas.models import Subscription

    c = environment
    h, _ = await setup(c)
    tid = uuid.UUID(h["X-Tenant-ID"])
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        db.add(
            Subscription(
                tenant_id=tid,
                created_by=None,
                plan="Starter",
                status="active",
                valid_until=datetime.now(UTC) + timedelta(days=1),
                grace_until=datetime.now(UTC) + timedelta(days=2),
                features=["accounting"],
                limits={
                    "users": 1,
                    "clients": 1,
                    "ai_requests": 0,
                    "ml_requests": 0,
                    "storage_bytes": 1000,
                },
            )
        )
    result = await c.post(
        "/api/v1/clients", headers=h, json={"code": "P12", "name": "Synthetic quota client"}
    )
    assert result.status_code == 201, result.text
    assert (
        await c.post("/api/v1/clients", headers=h, json={"code": "P12B", "name": "Over quota"})
    ).status_code == 409
    assert (await c.get("/api/v1/ai/tools", headers=h)).status_code == 403
    async with Session() as db, db.begin():
        await tenant_context(db, str(uuid.uuid4()))
        assert await db.scalar(select(Subscription).where(Subscription.tenant_id == tid)) is None
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tid))
        sub.status = "cancelled"
    assert (await c.get("/api/v1/clients", headers=h)).status_code == 200
    assert (
        await c.patch(
            "/api/v1/clients/" + result.json()["id"],
            headers=h,
            json={"name": "Forbidden change", "version": 1},
        )
    ).status_code == 403

"""Real PostgreSQL and Redis tests. Run only against a disposable migrated database."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text, update

from app.db.models.platform import (
    AIExecution,
    AIUsageRecord,
    BackgroundJob,
    Client,
    Engagement,
    LegalEntity,
    Membership,
    MembershipRole,
    Role,
    Tenant,
    User,
)
from app.db.session import Session, tenant_context
from app.main import app
from app.workers.tasks import process

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="Requires disposable PostgreSQL and Redis; set INTEGRATION_TESTS=1",
)


@pytest.fixture
async def environment():
    # Database is reset through Alembic externally, not ORM create_all.
    async with Session() as db:
        async with db.begin():
            from app.core.config import settings
            from app.modules.demo.guard import test_database_guard

            test_database_guard(settings(), await db.scalar(text("SELECT current_database()")))
            await db.execute(
                text(
                    "TRUNCATE users, tenants, roles, permissions, refresh_sessions, tenant_memberships, membership_roles, role_permissions CASCADE"
                )
            )
    from redis.asyncio import Redis

    from app.core.config import settings

    async with Redis.from_url(settings().redis_url) as redis:
        await redis.delete("auth-rate:127.0.0.1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    # asyncpg pooled connections belong to the fixture event loop.
    from app.db.session import engine

    await engine.dispose()


async def setup(client):
    from app.core.config import settings

    response = await client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Secret": settings().bootstrap_secret},
        json={
            "email": "admin@example.com",
            "password": "test-strong-password-123",
            "tenant_name": "TEST ONLY Firm A",
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    response = await client.get("/api/v1/tenants", headers=headers)
    tenant = response.json()[0]["id"]
    headers["X-Tenant-ID"] = tenant
    return headers, tokens


async def test_auth_rotation_logout_and_bootstrap(environment):
    client = environment
    headers, tokens = await setup(client)
    response = await client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Secret": os.environ["BOOTSTRAP_SECRET"]},
        json={
            "email": "again@example.com",
            "password": "test-strong-password-123",
            "tenant_name": "Test",
        },
    )
    assert response.status_code == 409
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login", data={"username": "admin@example.com", "password": "wrong"}
        )
    ).status_code == 401
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@example.com", "password": "test-strong-password-123"},
    )
    assert login.status_code == 200
    rotation = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotation.status_code == 200
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotation.json()["refresh_token"]}
        )
    ).status_code == 401
    fresh = login.json()["refresh_token"]
    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": fresh})
    ).status_code == 204
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": fresh})
    ).status_code == 401


async def test_clients_entities_engagements_and_ai(environment):
    client = environment
    headers, _ = await setup(client)
    response = await client.post(
        "/api/v1/clients", headers=headers, json={"code": "TEST-001", "name": "TEST ONLY Client"}
    )
    assert response.status_code == 201, response.text
    obj = response.json()
    assert (await client.get("/api/v1/clients/" + obj["id"], headers=headers)).status_code == 200
    assert (
        await client.post(
            "/api/v1/clients", headers=headers, json={"code": "TEST-001", "name": "Duplicate"}
        )
    ).status_code == 409
    page = (
        await client.get(
            "/api/v1/clients?limit=1&search=TEST&status=active&sort=name", headers=headers
        )
    ).json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert (
        await client.patch(
            "/api/v1/clients/" + obj["id"], headers=headers, json={"name": "Updated", "version": 1}
        )
    ).status_code == 200
    assert (
        await client.patch(
            "/api/v1/clients/" + obj["id"], headers=headers, json={"name": "Stale", "version": 1}
        )
    ).status_code == 409
    entity = await client.post(
        "/api/v1/entities",
        headers=headers,
        json={
            "client_id": obj["id"],
            "name": "TEST ONLY Entity",
            "country": "AE",
            "jurisdiction": "Test",
            "functional_currency": "AED",
            "presentation_currency": "USD",
        },
    )
    assert entity.status_code == 201, entity.text
    period = await client.post(
        "/api/v1/financial-periods",
        headers=headers,
        json={
            "entity_id": entity.json()["id"],
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    assert period.status_code == 201, period.text
    engagement = await client.post(
        "/api/v1/engagements",
        headers=headers,
        json={
            "entity_id": entity.json()["id"],
            "period_id": period.json()["id"],
            "name": "TEST ONLY Engagement",
            "engagement_type": "External Audit",
        },
    )
    assert engagement.status_code == 201, engagement.text
    ai = await client.post(
        "/api/v1/ai/execute",
        headers=headers,
        json={"task_type": "summarize_text", "input": {"text": "Non-confidential test input"}},
    )
    assert ai.status_code == 200, ai.text
    assert ai.json()["status"] == "completed"
    assert (
        await client.get("/api/v1/ai/executions/" + ai.json()["execution_id"], headers=headers)
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/ai/execute",
            headers=headers,
            json={"model": "unapproved", "task_type": "summarize_text", "input": {"text": "Test"}},
        )
    ).status_code == 422
    async with Session() as db:
        await tenant_context(db, headers["X-Tenant-ID"])
        assert await db.scalar(
            select(AIUsageRecord).where(
                AIUsageRecord.execution_id == uuid.UUID(ai.json()["execution_id"])
            )
        )


async def test_tenant_isolation_rls_and_permissions(environment):
    client = environment
    headers, _ = await setup(client)
    tenant_a = uuid.UUID(headers["X-Tenant-ID"])
    obj = (
        await client.post("/api/v1/clients", headers=headers, json={"code": "A", "name": "TEST A"})
    ).json()
    async with Session() as db:
        async with db.begin():
            user = await db.scalar(select(User))
            tenant_b = Tenant(name="TEST ONLY Firm B")
            db.add(tenant_b)
            await db.flush()
            member = Membership(tenant_id=tenant_b.id, user_id=user.id)
            db.add(member)
            await db.flush()
            role = await db.scalar(select(Role).where(Role.name == "Client Viewer"))
            db.add(MembershipRole(membership_id=member.id, role_id=role.id))
            b_id = tenant_b.id
    b_headers = {**headers, "X-Tenant-ID": str(b_id)}
    # Phase 4 client identities are restricted to allowlisted portal responses.
    assert (await client.get("/api/v1/clients/" + obj["id"], headers=b_headers)).status_code == 403
    assert (
        await client.post("/api/v1/clients", headers=b_headers, json={"code": "B", "name": "Test"})
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/ai/execute",
            headers=b_headers,
            json={"task_type": "summarize_text", "input": {"text": "Test"}},
        )
    ).status_code == 403
    assert (
        await client.get("/api/v1/clients", headers={**headers, "X-Tenant-ID": str(uuid.uuid4())})
    ).status_code == 403
    async with Session() as db:
        await tenant_context(db, str(b_id))
        assert not (await db.scalars(select(Client))).all()
        role = await db.execute(
            text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
        )
        assert tuple(role.one()) == (False, False)
    async with Session() as db:
        await tenant_context(db, str(tenant_a))
        assert len((await db.scalars(select(Client))).all()) == 1


async def test_disabled_identity(environment):
    client = environment
    headers, tokens = await setup(client)
    async with Session() as db:
        async with db.begin():
            await db.execute(update(User).values(status="disabled"))
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "test-strong-password-123"},
        )
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401


async def test_job_persistence_and_idempotency(environment, monkeypatch):
    client = environment
    headers, _ = await setup(client)
    from app.workers.tasks import diagnostic

    monkeypatch.setattr(diagnostic, "apply_async", lambda **kwargs: None)
    first = await client.post(
        "/api/v1/jobs/diagnostic", headers={**headers, "Idempotency-Key": "test-job"}
    )
    assert first.status_code == 202, first.text
    second = await client.post(
        "/api/v1/jobs/diagnostic", headers={**headers, "Idempotency-Key": "test-job"}
    )
    assert first.json()["id"] == second.json()["id"]
    async with Session() as db:
        user = await db.scalar(select(User))
    await process(first.json()["id"], headers["X-Tenant-ID"], str(user.id))
    response = await client.get("/api/v1/jobs/" + first.json()["id"], headers=headers)
    assert response.json()["status"] == "completed"
    assert response.json()["finished_at"]
    await process(first.json()["id"], headers["X-Tenant-ID"], str(user.id))


async def test_ai_failure_metadata(environment, monkeypatch):
    from app.infrastructure.ai_providers.adapters import MockProvider

    client = environment
    headers, _ = await setup(client)

    async def fail(self, request):
        raise TimeoutError("sensitive-provider-message")

    monkeypatch.setattr(MockProvider, "generate", fail)
    response = await client.post(
        "/api/v1/ai/execute",
        headers=headers,
        json={
            "task_type": "summarize_text",
            "input": {"text": "Sensitive content must not be persisted"},
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and response.json()["error_category"] == "timeout"
    assert "sensitive-provider-message" not in response.text
    async with Session() as db:
        await tenant_context(db, headers["X-Tenant-ID"])
        execution = await db.get(AIExecution, uuid.UUID(response.json()["execution_id"]))
        assert execution.status == "failed" and execution.duration_ms is not None
        assert not hasattr(execution, "prompt")


async def test_job_failure_and_cross_tenant_access(environment, monkeypatch):
    client = environment
    headers, _ = await setup(client)
    from app.workers.tasks import diagnostic

    monkeypatch.setattr(diagnostic, "apply_async", lambda **kwargs: None)
    result = await client.post(
        "/api/v1/jobs/diagnostic", headers={**headers, "Idempotency-Key": "revoked-job"}
    )
    async with Session() as db:
        async with db.begin():
            user = await db.scalar(select(User))
            await db.execute(update(Membership).values(status="disabled"))
    await process(result.json()["id"], headers["X-Tenant-ID"], str(user.id))
    async with Session() as db:
        await tenant_context(db, headers["X-Tenant-ID"])
        row = await db.get(BackgroundJob, uuid.UUID(result.json()["id"]))
        assert row.status == "failed" and row.error_category == "authorization"
    assert (
        await client.get("/api/v1/jobs/" + result.json()["id"], headers=headers)
    ).status_code == 403


async def test_database_constraints_and_append_only(environment):
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from app.db.models.platform import AuditEvent

    client = environment
    headers, _ = await setup(client)
    async with Session() as db:
        async with db.begin():
            await tenant_context(db, headers["X-Tenant-ID"])
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        LegalEntity(
                            tenant_id=uuid.UUID(headers["X-Tenant-ID"]),
                            client_id=uuid.uuid4(),
                            name="Test invalid FK",
                            country="AE",
                            jurisdiction="Test",
                            functional_currency="AED",
                            presentation_currency="AED",
                        )
                    )
                    await db.flush()
            events = (await db.scalars(select(AuditEvent))).all()
            assert any(event.action == "identity.bootstrap" for event in events)
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(update(AuditEvent).values(action="tampered"))
    # RLS tenant setting must never leak after transaction ends.
    async with Session() as db:
        assert not (await db.scalars(select(Client))).all()


async def test_expired_refresh_and_rate_limit(environment):
    from app.db.models.platform import RefreshSession

    client = environment
    headers, tokens = await setup(client)
    async with Session() as db:
        async with db.begin():
            await db.execute(
                update(RefreshSession).values(expires_at=datetime.now(UTC) - timedelta(days=1))
            )
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    for _ in range(21):
        response = await client.post(
            "/api/v1/auth/login", data={"username": "unknown@example.com", "password": "incorrect"}
        )
    assert response.status_code == 429


async def test_ready_health_and_resource_updates(environment):
    client = environment
    headers, _ = await setup(client)
    assert (await client.get("/health/ready")).status_code == 200
    assert (await client.get("/api/v1/ai/health", headers=headers)).json()[
        "real_provider_connectivity"
    ] == "not_probed"
    assert (await client.get("/api/v1/ai/models", headers=headers)).json()[0][
        "name"
    ] == "mock-diagnostic"
    obj = (
        await client.post("/api/v1/clients", headers=headers, json={"code": "T", "name": "TEST"})
    ).json()
    entity = (
        await client.post(
            "/api/v1/entities",
            headers=headers,
            json={
                "client_id": obj["id"],
                "name": "TEST Entity",
                "country": "AE",
                "jurisdiction": "Test",
                "functional_currency": "AED",
                "presentation_currency": "AED",
            },
        )
    ).json()
    assert (await client.get("/api/v1/entities", headers=headers)).status_code == 200
    assert (
        await client.get("/api/v1/entities/" + entity["id"], headers=headers)
    ).status_code == 200
    assert (
        await client.patch(
            "/api/v1/entities/" + entity["id"],
            headers=headers,
            json={"version": 1, "name": "Updated entity"},
        )
    ).status_code == 200
    engagement = (
        await client.post(
            "/api/v1/engagements",
            headers=headers,
            json={"entity_id": entity["id"], "name": "TEST Engagement", "engagement_type": "VAT"},
        )
    ).json()
    assert (await client.get("/api/v1/engagements", headers=headers)).status_code == 200
    assert (
        await client.get("/api/v1/engagements/" + engagement["id"], headers=headers)
    ).status_code == 200
    assert (
        await client.patch(
            "/api/v1/engagements/" + engagement["id"],
            headers=headers,
            json={"version": 1, "name": "Updated engagement"},
        )
    ).status_code == 200
    assert (
        await client.get("/api/v1/clients?sort=password_hash", headers=headers)
    ).status_code == 422
    assert (
        await client.patch(
            "/api/v1/clients/" + obj["id"], headers=headers, json={"version": 1, "name": None}
        )
    ).status_code == 422
    assert (
        await client.get(
            "/api/v1/clients",
            headers={"Authorization": "Bearer invalid", "X-Tenant-ID": headers["X-Tenant-ID"]},
        )
    ).status_code == 401


async def test_cross_tenant_engagement_fk_and_denial(environment):
    from sqlalchemy.exc import IntegrityError

    client = environment
    headers, _ = await setup(client)
    tenant_a = uuid.UUID(headers["X-Tenant-ID"])
    async with Session() as db:
        async with db.begin():
            user = await db.scalar(select(User))
            other = Tenant(name="TEST ONLY Other Tenant")
            db.add(other)
            await db.flush()
            await tenant_context(db, str(other.id))
            other_client = Client(
                tenant_id=other.id, created_by=user.id, code="OTHER", name="TEST OTHER"
            )
            db.add(other_client)
            await db.flush()
            other_entity = LegalEntity(
                tenant_id=other.id,
                client_id=other_client.id,
                name="TEST",
                country="AE",
                jurisdiction="Test",
                functional_currency="AED",
                presentation_currency="AED",
            )
            db.add(other_entity)
            await db.flush()
            other_engagement = Engagement(
                tenant_id=other.id,
                entity_id=other_entity.id,
                name="TEST",
                engagement_type="External Audit",
            )
            db.add(other_engagement)
            await db.flush()
            entity_id, engagement_id = other_entity.id, other_engagement.id
            await tenant_context(db, str(tenant_a))
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        Engagement(
                            tenant_id=tenant_a,
                            entity_id=entity_id,
                            name="TEST invalid cross-tenant",
                            engagement_type="VAT",
                        )
                    )
                    await db.flush()
    assert (
        await client.get("/api/v1/engagements/" + str(engagement_id), headers=headers)
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/engagements",
            headers=headers,
            json={"entity_id": str(entity_id), "name": "TEST", "engagement_type": "VAT"},
        )
    ).status_code == 404

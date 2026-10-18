import os
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.dependencies import Context
from app.core.permissions import ROLE_PERMISSIONS
from app.db.models.platform import Membership
from app.db.session import Session, tenant_context
from app.modules.saas.models import Subscription, Usage
from tests.integration.test_platform import environment as environment
from tests.integration.test_platform import setup
from tests.phase4.test_workflows import actor

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database required"
)


async def test_ml_metadata_read_does_not_wait_for_training_engagement_lock(environment):
    import asyncio

    from app.db.models.platform import Engagement
    from tests.phase4.test_workflows import setup as audit_setup

    c = environment
    h, _, eid, _ = await audit_setup(c)
    async with Session() as held, held.begin():
        await tenant_context(held, h["X-Tenant-ID"])
        await held.scalar(
            select(Engagement).where(Engagement.id == uuid.UUID(eid)).with_for_update()
        )
        response = await asyncio.wait_for(
            c.get(f"/api/v1/ml/events?eid={eid}", headers=h), timeout=2
        )
        assert response.status_code == 200


async def test_cancel_own_training_bypasses_tenant_admission_lock(environment):
    import asyncio

    from sqlalchemy import text

    from app.db.models.platform import BackgroundJob
    from app.modules.ml.models import MLEvent
    from tests.phase4.test_workflows import setup as audit_setup

    c = environment
    h, _, eid, _ = await audit_setup(c)
    tid = uuid.UUID(h["X-Tenant-ID"])
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        member = await db.scalar(select(Membership).where(Membership.tenant_id == tid))
        source = MLEvent(
            tenant_id=tid,
            created_by=member.user_id,
            engagement_id=uuid.UUID(eid),
            kind="dataset",
            body={},
            sha256="a" * 64,
        )
        db.add(source)
        await db.flush()
        job = BackgroundJob(
            tenant_id=tid,
            created_by=member.user_id,
            job_type="ml.train",
            idempotency_key="p12-cancel-lock",
            status="running",
            payload={"source_id": str(source.id)},
        )
        db.add(job)
        await db.flush()
        identifier = job.id
    async with Session() as held, held.begin():
        await held.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"), {"key": str(tid)}
        )
        response = await asyncio.wait_for(
            c.post(f"/api/v1/ml/jobs/{identifier}/cancel", headers=h), timeout=2
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", sorted(ROLE_PERMISSIONS))
async def test_each_role_real_api_read_write_boundary(environment, role):
    c = environment
    h, _ = await setup(c)
    identity = await actor(h, role, "p12-role")
    own = identity[0]
    result = await c.get("/api/v1/clients", headers=own)
    assert result.status_code == (200 if "clients.read" in ROLE_PERMISSIONS[role] else 403)
    result = await c.post(
        "/api/v1/clients",
        headers=own,
        json={"code": "P12ROLE", "name": "SYNTHETIC role permission fixture"},
    )
    assert result.status_code == (201 if "clients.write" in ROLE_PERMISSIONS[role] else 403)
    assert (await c.get("/api/v1/platform/tenants", headers=own)).status_code == 403
    assert (
        await c.get("/api/v1/clients", headers={**own, "X-Tenant-ID": str(uuid.uuid4())})
    ).status_code == 403


async def test_storage_admission_before_object_write_and_lifetime_accounting(
    environment, monkeypatch
):
    from app.modules.lineage.storage import ObjectStore
    from app.modules.saas.storage import put_private

    c = environment
    h, _ = await setup(c)
    tid = uuid.UUID(h["X-Tenant-ID"])
    calls = []

    def store(self, tenant, stream):
        calls.append(stream.read())
        return {"size": len(calls[-1]), "object_key": tenant + "/synthetic-object"}

    monkeypatch.setattr(ObjectStore, "put", store)
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        sub = Subscription(
            tenant_id=tid,
            created_by=None,
            plan="Starter",
            status="active",
            valid_until=datetime.now(UTC) + timedelta(days=1),
            grace_until=datetime.now(UTC) + timedelta(days=2),
            features=["accounting"],
            limits={
                "users": 5,
                "clients": 10,
                "ai_requests": 10,
                "ml_requests": 0,
                "storage_bytes": 10,
            },
        )
        db.add(sub)
        await db.flush()
        ctx = Context(uuid.uuid4(), tid, frozenset())
        with pytest.raises(HTTPException) as denied:
            await put_private(db, ctx, BytesIO(b"12345678901"))
        assert denied.value.status_code == 413 and calls == []
        await put_private(db, ctx, BytesIO(b"1234567890"))
        counter = await db.scalar(
            select(Usage).where(Usage.tenant_id == tid, Usage.metric == "storage_bytes")
        )
        assert counter.quantity == 10
        with pytest.raises(HTTPException):
            await put_private(db, ctx, BytesIO(b"x"))
        assert len(calls) == 1


async def test_revoked_ai_worker_stops_durably_instead_of_retrying_forever(environment):
    from app.modules.enterprise_ai.models import Event, Workflow
    from app.workers.enterprise_ai import process
    from tests.phase4.test_workflows import setup as audit_setup

    c = environment
    h, _, eid, _ = await audit_setup(c)
    result = await c.post(
        "/api/v1/ai/command",
        headers=h,
        json={
            "engagement_id": eid,
            "task": "audit-planning",
            "prompt": "Synthetic worker revocation test",
            "idempotency_key": "phase12-worker-revocation",
        },
    )
    assert result.status_code == 201, result.text
    identifier = result.json()["id"]
    async with Session() as db, db.begin():
        member = await db.scalar(
            select(Membership).where(Membership.tenant_id == uuid.UUID(h["X-Tenant-ID"]))
        )
        uid = member.user_id
        member.status = "disabled"
    for _ in range(2):
        outcome = await process(h["X-Tenant-ID"], str(uid), eid, identifier)
        assert outcome["state"] == "FAILED"
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        run = await db.get(Workflow, uuid.UUID(identifier))
        assert run.state == "FAILED"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.run_id == run.id, Event.key == "worker.authorization-stopped")
            )
            == 1
        )

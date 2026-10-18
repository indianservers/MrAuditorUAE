import os
import uuid

import pytest
from sqlalchemy import select

from app.core.dependencies import Context
from app.db.models.platform import BackgroundJob, Role, User
from app.db.session import Session, tenant_context
from app.modules.audit_execution.models import RolePolicy
from app.modules.jobs.service import submit
from app.workers.accounting import authorized
from app.workers.tasks import process
from tests.integration.test_platform import environment as environment
from tests.integration.test_platform import setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_workers_obey_tenant_policy_revocation(environment):
    h, _ = await setup(environment)
    tid = uuid.UUID(h["X-Tenant-ID"])
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        role = await db.scalar(select(Role).where(Role.name == "Firm Administrator"))
        db.add(RolePolicy(tenant_id=tid, created_by=user.id, role_id=role.id, permissions=[]))
        job = BackgroundJob(tenant_id=tid, created_by=user.id, idempotency_key="revoked-policy")
        db.add(job)
        await db.flush()
        jid = job.id
        uid = user.id
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        assert not await authorized(db, tid, uid, "accounting.import")
    await process(str(jid), str(tid), str(uid))
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        job = await db.get(BackgroundJob, jid)
        assert job.status == "failed" and job.error_category == "authorization"


async def test_completed_job_idempotency_key_cannot_be_reused_by_another_user(environment):
    h, _ = await setup(environment)
    tid = uuid.UUID(h["X-Tenant-ID"])
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        db.add(
            BackgroundJob(
                tenant_id=tid,
                created_by=user.id,
                idempotency_key="completed-owned",
                status="completed",
            )
        )
    async with Session() as db, db.begin():
        await tenant_context(db, str(tid))
        with pytest.raises(Exception, match="409"):
            await submit(
                db,
                Context(uuid.uuid4(), tid, frozenset({"jobs.execute"})),
                "completed-owned",
                "test",
            )

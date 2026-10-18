import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import (
    BackgroundJob,
    Membership,
    Tenant,
    User,
)
from app.db.session import tenant_context
from app.modules.audit_log.service import record
from app.workers.celery_app import celery_app


async def process(job_id: str, tenant_id: str, user_id: str) -> None:
    # A fresh engine per task avoids sharing asyncpg connections across event loops.
    engine = create_async_engine(settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db, db.begin():
            await tenant_context(db, tenant_id)
            job = await db.scalar(
                select(BackgroundJob)
                .where(
                    BackgroundJob.id == uuid.UUID(job_id),
                    BackgroundJob.tenant_id == uuid.UUID(tenant_id),
                )
                .with_for_update()
            )
            if not job or job.status in {"completed", "failed"}:
                return
            membership = await db.scalar(
                select(Membership)
                .join(User, User.id == Membership.user_id)
                .join(Tenant, Tenant.id == Membership.tenant_id)
                .where(
                    Membership.user_id == uuid.UUID(user_id),
                    Membership.tenant_id == uuid.UUID(tenant_id),
                    Membership.status == "active",
                    User.status == "active",
                    Tenant.status == "active",
                )
            )
            allowed = None
            if membership:
                from app.modules.audit_execution.access import firm_roles, role_permissions

                roles = await firm_roles(db, uuid.UUID(tenant_id), uuid.UUID(user_id))
                effective = await role_permissions(
                    db, uuid.UUID(tenant_id), [role.id for role in roles]
                )
                allowed = "jobs.execute" if "jobs.execute" in effective else None
            job.started_at = datetime.now(UTC)
            try:
                if not allowed or job.created_by != uuid.UUID(user_id):
                    raise PermissionError("Job authorization revoked")
                # Harmless deterministic system diagnostic, no financial access.
                await db.execute(select(1))
                job.status = "completed"
            except Exception as exc:
                job.status = "failed"
                job.error_category = (
                    "authorization" if isinstance(exc, PermissionError) else "diagnostic"
                )
            job.finished_at = datetime.now(UTC)
            record(
                db,
                Context(uuid.UUID(user_id), uuid.UUID(tenant_id), frozenset()),
                "job." + job.status,
                job.id,
                str(job.id),
            )
    finally:
        await engine.dispose()


@celery_app.task(
    name="auditos.diagnostic", autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3
)
def diagnostic(job_id: str, tenant_id: str, user_id: str) -> None:
    asyncio.run(process(job_id, tenant_id, user_id))

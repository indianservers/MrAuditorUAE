"""Authorized, idempotent Phase 2 work dispatched through existing Celery/Redis."""

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import (
    BackgroundJob,
    Membership,
    MembershipRole,
    Permission,
    RolePermission,
    Tenant,
    User,
)
from app.db.session import tenant_context
from app.workers.celery_app import celery_app

PERMISSIONS = {
    "import.validate": "accounting.import",
    "analytics": "analytics.run",
    "reconciliation": "analytics.run",
    "sampling": "sampling.run",
    "financial_ai": "financial_ai.execute",
    "zoho.sync": "connectors.manage",
}


async def submit(db: AsyncSession, ctx: Context, kind: str, payload: dict, request_id: str):
    import hashlib
    import json

    if kind not in PERMISSIONS or PERMISSIONS[kind] not in ctx.permissions:
        raise HTTPException(403, "Task permission denied")
    key = (
        "phase2:"
        + hashlib.sha256(
            (str(ctx.user_id) + kind + json.dumps(payload, sort_keys=True)).encode()
        ).hexdigest()
    )
    from sqlalchemy import text

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(ctx.tenant_id) + key},
    )
    job = await db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == ctx.tenant_id, BackgroundJob.idempotency_key == key
        )
    )
    if not job:
        job = BackgroundJob(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            idempotency_key=key,
            job_type=kind,
            payload=payload,
        )
        db.add(job)
        await db.flush()
    await db.commit()
    if job.status == "pending":
        try:
            work.apply_async(
                args=[str(job.id), str(ctx.tenant_id), str(ctx.user_id)], task_id=str(job.id)
            )
        except Exception:
            raise HTTPException(
                503, "Broker unavailable; retry to redispatch pending work"
            ) from None
    return {"id": str(job.id), "status": job.status, "progress": job.progress}


async def authorized(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, permission: str
) -> bool:
    value = await db.scalar(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .join(User, User.id == Membership.user_id)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.status == "active",
            User.status == "active",
            Tenant.status == "active",
            Permission.code == permission,
        )
    )
    return value is not None


async def process(job_id: str, tenant_id: str, user_id: str):
    engine = create_async_engine(settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant, user, identifier = uuid.UUID(tenant_id), uuid.UUID(user_id), uuid.UUID(job_id)
    try:
        async with factory() as db, db.begin():
            await tenant_context(db, tenant_id)
            job = await db.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.tenant_id == tenant, BackgroundJob.id == identifier)
                .with_for_update()
            )
            if not job or job.status in {"completed", "failed", "cancelled"}:
                return
            job.status = "running"
            job.started_at = datetime.now(UTC)
            job.progress = 10
        try:
            async with factory() as db, db.begin():
                await tenant_context(db, tenant_id)
                job = await db.scalar(
                    select(BackgroundJob)
                    .where(BackgroundJob.tenant_id == tenant, BackgroundJob.id == identifier)
                    .with_for_update()
                )
                if not job or job.status in {"completed", "failed", "cancelled"}:
                    return
                permission = PERMISSIONS.get(job.job_type)
                if (
                    not permission
                    or job.created_by != user
                    or not await authorized(db, tenant, user, permission)
                ):
                    raise PermissionError("Authorization revoked")
                ctx = Context(user, tenant, frozenset([permission]))
                payload = job.payload
                if job.job_type == "import.validate":
                    from app.modules.accounting.service import validate

                    result = await validate(db, ctx, uuid.UUID(payload["batch_id"]), job_id)
                    result = {"batch_id": str(result.id), "status": result.status}
                elif job.job_type == "analytics":
                    from app.modules.audit_analytics.schemas import AnalyticsRequest
                    from app.modules.audit_analytics.service import analytics

                    result = await analytics(db, ctx, AnalyticsRequest.model_validate(payload))
                elif job.job_type == "reconciliation":
                    from app.modules.accounting.schemas import ReconcileRequest
                    from app.modules.reconciliation.service import run_reconciliation

                    request = ReconcileRequest.model_validate(payload)
                    result = await run_reconciliation(
                        db,
                        ctx,
                        request.snapshot_id,
                        request.comparison_snapshot_id,
                        request.tolerance,
                    )
                elif job.job_type == "sampling":
                    from app.modules.accounting.schemas import SamplingRequest
                    from app.modules.audit_analytics.service import sampling

                    result = await sampling(db, ctx, SamplingRequest.model_validate(payload))
                elif job.job_type == "financial_ai":
                    from app.modules.financial_ai.schemas import FinancialRequest
                    from app.modules.financial_ai.service import suggest

                    result = await suggest(
                        db,
                        ctx,
                        payload["task"],
                        FinancialRequest.model_validate(payload["request"]),
                        job_id,
                    )
                else:
                    from app.modules.connectors.service import zoho_sync

                    result = await zoho_sync(db, ctx, uuid.UUID(payload["connection_id"]))
                job.status = "completed"
                job.progress = 100
                job.finished_at = datetime.now(UTC)
                # Only resource references/status, never AI content or connector secrets in jobs.
                job.result = {
                    "resource_id": str(
                        result.get("id", result.get("batch_id", result.get("suggestion_id", "")))
                    ),
                    "status": result.get("status", "completed"),
                }
        except Exception as exc:
            async with factory() as db, db.begin():
                await tenant_context(db, tenant_id)
                await db.execute(
                    update(BackgroundJob)
                    .where(BackgroundJob.id == identifier, BackgroundJob.tenant_id == tenant)
                    .values(
                        status="failed",
                        error_category="authorization"
                        if isinstance(exc, PermissionError)
                        else "processing",
                        finished_at=datetime.now(UTC),
                        progress=100,
                    )
                )
    finally:
        await engine.dispose()


@celery_app.task(name="auditos.accounting", soft_time_limit=1800, time_limit=1900, acks_late=True)
def work(job_id: str, tenant_id: str, user_id: str):
    asyncio.run(process(job_id, tenant_id, user_id))

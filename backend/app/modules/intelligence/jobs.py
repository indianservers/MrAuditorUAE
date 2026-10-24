"""Recoverable queue execution with authorization and source rechecks at publication."""

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.dependencies import Context
from app.db.models.platform import Membership, Tenant, User
from app.db.session import tenant_context
from app.modules.audit_execution.access import firm_roles, role_permissions
from app.modules.audit_log.service import record
from app.modules.intelligence import service
from app.modules.intelligence.models import IntelligenceJob
from app.modules.jurisdictions.packages import fingerprint


async def actor(db, tenant, user):
    membership = await db.scalar(
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.tenant_id == tenant,
            Membership.user_id == user,
            Membership.status == "active",
            Tenant.status == "active",
            User.status == "active",
        )
    )
    if not membership:
        raise HTTPException(403, "Job authorization revoked")
    roles = await firm_roles(db, tenant, user)
    return Context(
        user, tenant, frozenset(await role_permissions(db, tenant, [r.id for r in roles]))
    )


async def submit(db, ctx, eid, data, key, request_id):
    await service.scope(db, ctx, eid, data.operation, True)
    await service.restricted_permission(db, ctx, eid, data.payload)
    digest = fingerprint({"operation": data.operation, "payload": data.payload, "eid": str(eid)})
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"intelligence-job:{ctx.tenant_id}:{ctx.user_id}:{key}"},
    )
    job = await db.scalar(
        select(IntelligenceJob).where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.created_by == ctx.user_id,
            IntelligenceJob.idempotency_key == key,
        )
    )
    if job:
        if job.payload_sha256 != digest:
            raise HTTPException(409, "Idempotency key reused for a different operation")
    else:
        job = IntelligenceJob(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            engagement_id=eid,
            idempotency_key=key,
            operation=data.operation,
            payload=data.payload,
            payload_sha256=digest,
        )
        db.add(job)
        await db.flush()
        record(
            db,
            ctx,
            "intelligence.job.submitted",
            job.id,
            request_id,
            {"engagement_id": str(eid), "operation": data.operation},
        )
    await db.commit()
    if job.status == "pending":
        from app.workers.intelligence import run

        try:
            run.apply_async(
                args=[str(job.id), str(ctx.tenant_id)], task_id=str(job.id), queue="intelligence"
            )
        except Exception:
            raise HTTPException(
                503, "Broker unavailable; job remains pending and recoverable"
            ) from None
    return job


async def process(identifier, tenant):
    engine = create_async_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant = uuid.UUID(str(tenant))
    identifier = uuid.UUID(str(identifier))
    try:
        async with sessions() as db, db.begin():
            await tenant_context(db, str(tenant))
            job = await db.scalar(
                select(IntelligenceJob)
                .where(IntelligenceJob.tenant_id == tenant, IntelligenceJob.id == identifier)
                .with_for_update()
            )
            if not job or job.status != "pending":
                return
            try:
                ctx = await actor(db, tenant, job.created_by)
                await service.scope(db, ctx, job.engagement_id, job.operation)
            except HTTPException:
                job.status = "failed"
                job.error_category = "authorization"
                job.error_details = {
                    "message": "Current user/engagement permission no longer permits execution"
                }
                return
            job.status = "running"
            job.progress = 10
            job.attempts += 1
            user = job.created_by
            eid = job.engagement_id
            operation = job.operation
            payload = dict(job.payload)
        try:
            async with sessions() as db, db.begin():
                await tenant_context(db, str(tenant))
                ctx = await actor(db, tenant, user)
                eng = await service.scope(db, ctx, eid, operation)
                started = time.monotonic()
                body, dependencies = await service.compute(db, ctx, eng, operation, payload)
                body = {**body, "processing_duration_seconds": round(time.monotonic() - started, 6)}
            async with sessions() as db, db.begin():
                await tenant_context(db, str(tenant))
                ctx = await actor(db, tenant, user)
                job = await db.scalar(
                    select(IntelligenceJob)
                    .where(IntelligenceJob.tenant_id == tenant, IntelligenceJob.id == identifier)
                    .with_for_update()
                )
                if not job or job.status != "running":
                    return
                eng = await service.scope(db, ctx, eid, operation, True)
                # Persist a result only after the entire operation succeeded.
                result = await service.append(
                    db,
                    ctx,
                    eng,
                    "workflow-source"
                    if operation in {"workflow-ledger", "workflow-vat"}
                    else operation,
                    {
                        **body,
                        "job_id": str(job.id),
                        "contributors": body.get("contributors", [str(user)]),
                    },
                    dependencies,
                    str(job.id),
                )
                if not await service.current(db, ctx, result):
                    raise HTTPException(
                        409, "Sources changed during execution; regenerate from current sources"
                    )
                job.result_id = result.id
                job.status = "completed"
                job.progress = 100
                job.error_category = None
                job.error_details = None
                record(
                    db,
                    ctx,
                    "intelligence.job.completed",
                    job.id,
                    str(job.id),
                    {"result_id": str(result.id), "engagement_id": str(eid)},
                )
        except Exception as exc:
            async with sessions() as db, db.begin():
                await tenant_context(db, str(tenant))
                job = await db.scalar(
                    select(IntelligenceJob)
                    .where(IntelligenceJob.tenant_id == tenant, IntelligenceJob.id == identifier)
                    .with_for_update()
                )
                if job and job.status != "canceled":
                    job.status = "failed"
                    job.error_category = (
                        "source_or_validation"
                        if isinstance(exc, (HTTPException, ValueError))
                        else "execution"
                    )
                    job.error_details = {
                        "message": str(exc.detail)
                        if isinstance(exc, HTTPException)
                        else str(exc)[:300]
                        if isinstance(exc, ValueError)
                        else "Operation failed; inspect private server diagnostics and retry after correcting the source"
                    }
                    record(
                        db,
                        Context(ctx.user_id, tenant, frozenset()),
                        "intelligence.job.failed",
                        job.id,
                        str(job.id),
                        {"category": job.error_category, "engagement_id": str(eid)},
                    )
    finally:
        await engine.dispose()


async def recover_due():
    """Recover committed outbox jobs and mark abandoned claims retryable, under tenant RLS."""
    engine = create_async_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    queued = []
    try:
        async with sessions() as db:
            tenants = (await db.scalars(select(Tenant.id).where(Tenant.status == "active"))).all()
        for tenant in tenants:
            async with sessions() as db, db.begin():
                await tenant_context(db, str(tenant))
                rows = (
                    await db.scalars(
                        select(IntelligenceJob)
                        .where(
                            IntelligenceJob.tenant_id == tenant,
                            IntelligenceJob.status.in_(["pending", "running"]),
                            IntelligenceJob.updated_at < datetime.now(UTC) - timedelta(minutes=5),
                        )
                        .order_by(IntelligenceJob.created_at)
                        .limit(100)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for job in rows:
                    if job.status == "running":
                        job.status = "failed"
                        job.error_category = "abandoned_claim"
                        job.error_details = {
                            "message": "Worker claim expired; manually retry after inspecting source and authorization"
                        }
                    else:
                        queued.append((str(job.id), str(tenant)))
        from app.workers.intelligence import run

        for identifier, tenant_id in queued:
            run.apply_async(args=[identifier, tenant_id], queue="intelligence")
        return len(queued)
    finally:
        await engine.dispose()

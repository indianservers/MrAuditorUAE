from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Context
from app.db.models.platform import BackgroundJob
from app.modules.audit_log.service import record


async def submit(db: AsyncSession, ctx: Context, key: str, request_id: str):
    # Serialize identical keys, including concurrent submissions before row creation.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": str(ctx.tenant_id) + ":" + key},
    )
    existing = await db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == ctx.tenant_id, BackgroundJob.idempotency_key == key
        )
    )
    if existing and existing.created_by != ctx.user_id:
        raise HTTPException(409, "Idempotency key belongs to another user")
    if existing and existing.status != "pending":
        return existing
    if existing:
        job = existing
        if job.created_by != ctx.user_id:
            raise HTTPException(409, "Idempotency key belongs to another user")
    else:
        job = BackgroundJob(tenant_id=ctx.tenant_id, created_by=ctx.user_id, idempotency_key=key)
        db.add(job)
        await db.flush()
        record(db, ctx, "job.submitted", job.id, request_id)
    # Commit before dispatch; pending rows form a recoverable outbox if broker is down.
    await db.commit()
    from app.workers.tasks import diagnostic

    try:
        diagnostic.apply_async(
            args=[str(job.id), str(ctx.tenant_id), str(ctx.user_id)], task_id=str(job.id)
        )
    except Exception:
        raise HTTPException(503, "Broker unavailable; job remains pending for redispatch") from None
    return job

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict

from app.core.dependencies import DB, Context, require
from app.db.models.platform import BackgroundJob
from app.modules.clients.service import ResourceService
from app.modules.jobs.service import submit

router = APIRouter(prefix="/jobs", tags=["Background jobs"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_type: str
    progress: int
    result: dict
    id: uuid.UUID
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_category: str | None


@router.post("/diagnostic", response_model=JobOut, status_code=202)
async def diagnostic(
    db: DB,
    ctx: Annotated[Context, Depends(require("jobs.execute"))],
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=100)],
):
    return await submit(db, ctx, idempotency_key, request.state.request_id)


@router.get("/{identifier}", response_model=JobOut)
async def get(
    identifier: uuid.UUID, db: DB, ctx: Annotated[Context, Depends(require("jobs.read"))]
):
    return await ResourceService(BackgroundJob).get(db, ctx, identifier)


@router.post("/{identifier}/retry", response_model=JobOut)
async def retry(
    identifier: uuid.UUID, db: DB, ctx: Annotated[Context, Depends(require("jobs.execute"))]
):
    from fastapi import HTTPException

    from app.modules.accounting.service import scoped
    from app.workers.accounting import PERMISSIONS, work

    job = await scoped(db, ctx, BackgroundJob, identifier, True)
    if job.created_by != ctx.user_id or PERMISSIONS.get(job.job_type) not in ctx.permissions:
        raise HTTPException(403, "Operation permission and original requesting identity required")
    if job.status != "failed":
        raise HTTPException(409, "Only failed jobs can be retried")
    job.status = "pending"
    job.progress = 0
    job.error_category = None
    job.started_at = None
    job.finished_at = None
    job.result = {}
    await db.commit()
    try:
        work.apply_async(
            args=[str(job.id), str(ctx.tenant_id), str(ctx.user_id)], task_id=str(job.id)
        )
    except Exception:
        raise HTTPException(503, "Broker unavailable; pending job is safely preserved") from None
    return job


@router.post("/{identifier}/cancel", response_model=JobOut)
async def cancel(
    identifier: uuid.UUID, db: DB, ctx: Annotated[Context, Depends(require("jobs.execute"))]
):
    from fastapi import HTTPException

    from app.modules.accounting.service import scoped
    from app.workers.accounting import PERMISSIONS

    job = await scoped(db, ctx, BackgroundJob, identifier, True)
    if job.created_by != ctx.user_id or PERMISSIONS.get(job.job_type) not in ctx.permissions:
        raise HTTPException(403, "Operation permission and original requesting identity required")
    if job.status != "pending":
        raise HTTPException(409, "Only pending jobs may be cancelled")
    from datetime import UTC

    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    job.progress = 100
    await db.flush()
    await db.refresh(job)
    return job

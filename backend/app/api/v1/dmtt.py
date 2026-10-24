import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from app.core.dependencies import DB, Context, require
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import BODIES, Action, RecordInput, RecordPatch
from app.modules.dmtt import schemas as s
from app.modules.dmtt import service

for key, value in s.BODIES.items():
    BODIES["dmtt-" + key] = value
    PREPARE["dmtt-" + key] = "dmtt.prepare"
    APPROVE["dmtt-" + key] = "dmtt.approve"
router = APIRouter(prefix="/dmtt", tags=["UAE Pillar Two"])
Actor = Annotated[Context, Depends(require("dmtt.read"))]


@router.post("/engagements/{eid}/scope-assessment", status_code=201)
async def scope_assessment(eid: uuid.UUID, data: s.ScopeInput, db: DB, ctx: Actor):
    from app.modules.dmtt.calculations import scope
    from app.modules.ml.service import event

    await audit.engagement(db, ctx, eid, "dmtt.prepare", True)
    for revenue in data.preceding_revenues:
        await service.evidence(db, ctx, eid, revenue.evidence_id)
    result = scope(data)
    return audit.serialize(await event(db, ctx, eid, "dmtt_scope", {
        "inputs": data.model_dump(mode="json"), "results": result,
        "execution_mode": "deterministic", "professional_review": "DRAFT_REQUIRES_REVIEW",
        "filing_status": "NOT_SUBMITTED"}))


@router.get("/legislation")
async def rules(ctx: Actor):
    return {
        "sources": service.SOURCES,
        "tasks": service.TASKS,
        "unsupported_guidance_applied": False,
    }


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "dmtt.read")
    return {
        "schemas": {k: v.model_json_schema() for k, v in s.BODIES.items()},
        "rules": service.SOURCES,
    }


@router.get("/engagements/{eid}/records/{kind}")
async def records(
    eid: uuid.UUID,
    kind: str,
    db: DB,
    ctx: Actor,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await audit.engagement(db, ctx, eid, "dmtt.read")
    where = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "dmtt-" + kind,
    ]
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(*where)
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [audit.serialize(x) for x in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*where)),
    }


@router.post("/engagements/{eid}/records/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    if kind not in s.BODIES:
        raise HTTPException(404, "Unknown DMTT workpaper")
    return await audit.create(db, ctx, eid, "dmtt-" + kind, data, request.state.request_id)


@router.patch("/engagements/{eid}/records/{rid}")
async def update(
    eid: uuid.UUID, rid: uuid.UUID, data: RecordPatch, db: DB, ctx: Actor, request: Request
):
    obj = await audit.get_record(db, ctx, eid, rid, "dmtt.prepare")
    if not obj.kind.startswith("dmtt-"):
        raise HTTPException(404, "DMTT paper not found")
    return await audit.update(db, ctx, eid, rid, data, request.state.request_id)


@router.post("/engagements/{eid}/records/{rid}/actions")
async def action(
    eid: uuid.UUID, rid: uuid.UUID, data: Action, db: DB, ctx: Actor, request: Request
):
    obj = await audit.get_record(db, ctx, eid, rid, "dmtt.read")
    if not obj.kind.startswith("dmtt-"):
        raise HTTPException(404, "DMTT paper not found")
    return await audit.action(db, ctx, eid, rid, data, request.state.request_id)


@router.post("/engagements/{eid}/groups/{gid}/calculate", status_code=201)
async def calculate(eid: uuid.UUID, gid: uuid.UUID, db: DB, ctx: Actor):
    return audit.serialize(await service.computation(db, ctx, eid, gid))


@router.get("/engagements/{eid}/calculations")
async def calculations(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.ml.models import MLEvent

    await audit.engagement(db, ctx, eid, "dmtt.read")
    rows = (
        await db.scalars(
            select(MLEvent)
            .where(
                MLEvent.tenant_id == ctx.tenant_id,
                MLEvent.engagement_id == eid,
                MLEvent.kind == "dmtt_calculation",
            )
            .order_by(MLEvent.created_at.desc())
            .limit(50)
        )
    ).all()
    return {"items": [{**audit.serialize(x), "freshness": "CURRENT" if await service.current(db, ctx, eid, x) else "STALE"} for x in rows]}

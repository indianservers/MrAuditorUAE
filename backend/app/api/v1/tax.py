import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from app.core.dependencies import DB, Context, require
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import BODIES as AUDIT_BODIES
from app.modules.audit_execution.schemas import RecordInput
from app.modules.tax import service
from app.modules.tax.catalogue import AI_TASKS, KINDS, SOURCES
from app.modules.tax.connected import ConnectedInput
from app.modules.tax.models import TaxRun
from app.modules.tax.schemas import BODIES

for name, schema in BODIES.items():
    AUDIT_BODIES["tax-" + name] = schema
for name, (prepare, approve) in KINDS.items():
    PREPARE["tax-" + name] = prepare
    APPROVE["tax-" + name] = approve
router = APIRouter(prefix="/tax", tags=["Corporate Tax"])
Actor = Annotated[Context, Depends(require(""))]


@router.post("/engagements/{eid}/connected-assessments", status_code=201)
async def connected_assessment(
    eid: uuid.UUID, data: ConnectedInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.tax.connected import assess

    eng = await audit.engagement(db, ctx, eid, "tax.computation.prepare", True)
    return audit.serialize(await assess(db, ctx, eng, data, request.state.request_id))


@router.get("/legislation")
async def legislation(ctx: Annotated[Context, Depends(require("tax.profile.read"))]):
    return {
        "items": [{"id": key, **value} for key, value in SOURCES.items()],
        "rules_automatically_approved": False,
        "verified_as_of": "2026-10-18",
    }


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    eng = await audit.engagement(db, ctx, eid, "tax.profile.read")
    from app.modules.audit_execution.access import engagement_permissions

    permissions, roles = await engagement_permissions(db, ctx, eid, "tax.profile.read")
    return {
        "engagement": audit.serialize(eng),
        "permissions": sorted(permissions),
        "roles": sorted(roles),
        "schemas": {k: v.model_json_schema() for k, v in BODIES.items()},
        "ai_tasks": AI_TASKS,
        "methodology_version": "auditos-ct/1.0",
    }


@router.get("/engagements/{eid}/records/{kind}")
async def records(
    eid: uuid.UUID,
    kind: str,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=200),
):
    await audit.engagement(db, ctx, eid, "tax.profile.read")
    if kind not in KINDS:
        raise HTTPException(404, "Unknown tax workbench")
    conditions = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "tax-" + kind,
        AuditRecord.title.icontains(search, autoescape=True),
    ]
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(*conditions)
            .order_by(AuditRecord.created_at.desc(), AuditRecord.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [audit.serialize(r) for r in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/records/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    if kind not in BODIES:
        raise HTTPException(422, "Unknown editable tax kind")
    return await audit.create(db, ctx, eid, "tax-" + kind, data, request.state.request_id)


@router.post("/engagements/{eid}/computations/{profile_id}", status_code=201)
async def compute(eid: uuid.UUID, profile_id: uuid.UUID, db: DB, ctx: Actor):
    try:
        return await service.compute(db, ctx, eid, profile_id)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/engagements/{eid}/calculate/{rid}", status_code=201)
async def calculate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    try:
        return await service.calculate_record(db, ctx, eid, rid)
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/engagements/{eid}/runs")
async def runs(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await audit.engagement(db, ctx, eid, "tax.profile.read")
    conditions = [TaxRun.tenant_id == ctx.tenant_id, TaxRun.engagement_id == eid]
    rows = (
        await db.scalars(
            select(TaxRun)
            .where(*conditions)
            .order_by(TaxRun.created_at.desc(), TaxRun.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {"id": str(r.id), "kind": r.kind, "sha256": r.sha256, "created_at": r.created_at}
            for r in rows
        ],
        "total": await db.scalar(select(func.count()).select_from(TaxRun).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/loss-transfers/{rid}/post", status_code=201)
async def post_transfer(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    return await service.post_transfer(db, ctx, eid, rid)


@router.get("/engagements/{eid}/runs/{rid}")
async def result(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    obj = await service.run(db, ctx, eid, rid)
    return {
        **audit.serialize(obj),
        "dependencies_current": await service.dependencies_current(db, ctx, eid, obj),
    }


@router.get("/engagements/{eid}/loss-ledger/{profile_id}")
async def losses(eid: uuid.UUID, profile_id: uuid.UUID, db: DB, ctx: Actor):
    eng = await audit.engagement(db, ctx, eid, "tax.profile.read")
    from app.modules.tax.schemas import TaxProfile

    profile = await service.record(db, ctx, eid, profile_id, "profile", True)
    lots, deps = await service.loss_lots(
        db, ctx, eng, TaxProfile.model_validate(service.clean(profile.body))
    )
    return {"items": lots, "dependencies": deps}


@router.get("/engagements/{eid}/runs/{rid}/export/{format}")
async def export(eid: uuid.UUID, rid: uuid.UUID, format: str, db: DB, ctx: Actor, request: Request):
    from app.modules.audit_log.service import record as event
    from app.modules.tax.exports import render

    eng = await audit.engagement(db, ctx, eid, "tax.return.export")
    if format not in {"pdf", "xlsx", "json", "docx"}:
        raise HTTPException(422, "Supported formats: pdf, xlsx, docx, json")
    obj = await service.run(db, ctx, eid, rid)
    release = await service.current_release(db, ctx, eng)
    released = bool(
        release
        and release.tax_run_id == rid
        and await service.dependencies_current(db, ctx, eid, obj)
    )
    approval = (
        await service.record(db, ctx, eid, release.approval_id, "computation", True)
        if released
        else None
    )
    content, mime = render(
        obj, format, released, approval.body.get("review_approvers", []) if approval else []
    )
    event(
        db,
        ctx,
        "tax.export",
        rid,
        request.state.request_id,
        {"format": format, "approved": released, "sha256": obj.sha256},
    )
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="AuditOS-CT-{rid}-{"approved" if released else "draft"}.{format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

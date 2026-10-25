import uuid
from datetime import date

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.modules.audit_execution import service as audit
from app.modules.intelligence import service as intelligence
from app.modules.regulatory import schemas as s
from app.modules.regulatory import service
from app.modules.regulatory.conversion import ConversionInput
from app.modules.regulatory.models import RuleVersion

router = APIRouter(prefix="/regulatory", tags=["Regulatory rule library"])


@router.post("/engagements/{eid}/conversions", status_code=201)
async def convert(eid: uuid.UUID, data: ConversionInput, db: DB, ctx: Actor, request: Request):
    from app.modules.regulatory.conversion import prepare

    eng = await intelligence.scope(db, ctx, eid, "lead", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.get("/rules")
async def library(
    db: DB,
    ctx: Actor,
    country: str | None = Query(None, pattern="^[A-Z]{2}$"),
    search: str = Query("", max_length=100),
    authority: str = Query("", max_length=200),
    effective_on: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await service.authorize_read(db, ctx)
    query = select(RuleVersion).where(RuleVersion.tenant_id == ctx.tenant_id)
    if country:
        query = query.where(RuleVersion.country == country)
    if search:
        query = query.where(
            or_(
                RuleVersion.rule_key.icontains(search, autoescape=True),
                RuleVersion.body["title"].astext.icontains(search, autoescape=True),
            )
        )
    if authority:
        query = query.where(RuleVersion.body["citations"].contains([{"authority": authority}]))
    if effective_on:
        query = query.where(RuleVersion.body["effective_from"].astext <= effective_on.isoformat())

        query = query.where(
            or_(
                RuleVersion.body["effective_to"].astext.is_(None),
                RuleVersion.body["effective_to"].astext >= effective_on.isoformat(),
            )
        )
    rows = (
        await db.scalars(
            query.order_by(RuleVersion.rule_key, RuleVersion.version.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                **audit.serialize(r),
                "state": (await service.state(db, ctx, r)).state,
                "current_sequence": await service.sequence(db, ctx, r.rule_key),
            }
            for r in rows
        ],
        "offset": offset,
        "limit": limit,
    }


@router.post("/rules", status_code=201)
async def propose(data: s.Rule, db: DB, ctx: Actor, request: Request):
    return audit.serialize(await service.propose(db, ctx, data, request.state.request_id))


@router.get("/rules/{identifier}")
async def detail(identifier: uuid.UUID, db: DB, ctx: Actor):
    await service.authorize_read(db, ctx)
    obj = await service.get(db, ctx, identifier)
    return {
        **audit.serialize(obj),
        "current_sequence": await service.sequence(db, ctx, obj.rule_key),
        "state": audit.serialize(await service.state(db, ctx, obj)),
        "validation_blockers": service.validation_blockers(s.Rule.model_validate(obj.body)),
    }


@router.post("/rules/{identifier}/decisions", status_code=201)
async def decide(identifier: uuid.UUID, data: s.Decision, db: DB, ctx: Actor, request: Request):
    return audit.serialize(
        await service.decide(
            db, ctx, await service.get(db, ctx, identifier), data, request.state.request_id
        )
    )


@router.post("/engagements/{eid}/assessments", status_code=201)
async def assess(eid: uuid.UUID, data: s.Assessment, db: DB, ctx: Actor, request: Request):
    eng = await intelligence.scope(db, ctx, eid, "lead", True)
    return audit.serialize(await service.assess(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/checklists", status_code=201)
async def checklist(eid: uuid.UUID, data: s.Checklist, db: DB, ctx: Actor, request: Request):
    eng = await audit.engagement(db, ctx, eid, "workingpaper.create", True)
    return audit.serialize(await service.checklist(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/india-statements", status_code=201)
async def india_statements(
    eid: uuid.UUID, data: s.IndiaStatements, db: DB, ctx: Actor, request: Request
):
    from app.modules.regulatory.india_reporting import statements

    eng = await intelligence.scope(db, ctx, eid, "lead", True)
    return audit.serialize(await statements(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/report-templates", status_code=201)
async def report_template(
    eid: uuid.UUID, data: s.ReportTemplate, db: DB, ctx: Actor, request: Request
):
    from app.modules.regulatory.reporting import template

    eng = await audit.engagement(db, ctx, eid, "workingpaper.create", True)
    return audit.serialize(await template(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/reports", status_code=201)
async def report_generate(
    eid: uuid.UUID, data: s.ReportGenerate, db: DB, ctx: Actor, request: Request
):
    from app.modules.regulatory.reporting import generate

    eng = await audit.engagement(db, ctx, eid, "workingpaper.create", True)
    return audit.serialize(await generate(db, ctx, eng, data, request.state.request_id))


@router.get("/rules/{identifier}/compare/{other}")
async def compare(identifier: uuid.UUID, other: uuid.UUID, db: DB, ctx: Actor):
    await service.authorize_read(db, ctx)
    from fastapi import HTTPException

    left, right = await service.get(db, ctx, identifier), await service.get(db, ctx, other)
    if left.rule_key != right.rule_key:
        raise HTTPException(422, "Compare versions of the same rule")
    return {
        "left_id": str(left.id),
        "right_id": str(right.id),
        "changes": [
            {"field": key, "left": left.body.get(key), "right": right.body.get(key)}
            for key in sorted(set(left.body) | set(right.body))
            if left.body.get(key) != right.body.get(key)
        ],
    }


@router.get("/rules/{identifier}/impact")
async def impact(identifier: uuid.UUID, db: DB, ctx: Actor, offset: int = Query(0, ge=0)):
    await service.authorize_read(db, ctx)
    from fastapi import HTTPException

    from app.modules.intelligence.models import IntelligenceEvent

    await service.get(db, ctx, identifier)
    rows = (
        await db.scalars(
            select(IntelligenceEvent)
            .where(
                IntelligenceEvent.tenant_id == ctx.tenant_id,
                IntelligenceEvent.dependencies.contains(
                    [{"type": "regulatory", "id": str(identifier)}]
                ),
            )
            .order_by(IntelligenceEvent.id)
            .offset(offset)
            .limit(101)
        )
    ).all()
    items = []
    for obj in rows[:100]:
        try:
            await intelligence.event(db, ctx, obj.engagement_id, obj.id)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        items.append(
            {
                "engagement_id": str(obj.engagement_id),
                "result_id": str(obj.id),
                "version": obj.version,
                "review_status": obj.body.get("review_status"),
                "freshness": "CURRENT" if await intelligence.current(db, ctx, obj) else "STALE",
                "sha256": obj.sha256,
            }
        )
    return {
        "items": items,
        "offset": offset,
        "next_offset": offset + 100 if len(rows) > 100 else None,
        "policy": "Historical outputs stay immutable; regeneration requires an explicit authorized action",
    }

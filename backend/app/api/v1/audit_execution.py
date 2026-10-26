import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select

from app.core.dependencies import DB, Context, require
from app.db.models.platform import Membership, Role
from app.modules.accounting.schemas import SamplingRequest
from app.modules.audit_execution import service as s
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.catalogue import (
    AI_TASKS,
    AREAS,
    ASSERTIONS,
    TRANSITIONS,
)
from app.modules.audit_execution.models import (
    AuditAccess,
    AuditRecord,
    AuditRevision,
    ReviewDecision,
)
from app.modules.audit_execution.schemas import (
    BODIES,
    Action,
    Grant,
    PolicyInput,
    RecordInput,
    RecordPatch,
)
from app.modules.audit_log.service import record

router = APIRouter(prefix="/engagements/{eid}/audit", tags=["Audit execution"])
Actor = Annotated[Context, Depends(require(""))]


@router.post("/ml-feedback/{identifier}/working-paper", status_code=201)
async def ml_review_workpaper(
    eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor, request: Request
):
    import hashlib

    from app.modules.lineage.freshness import require_ml_current
    from app.modules.ml import service as ml

    await s.engagement(db, ctx, eid, "workingpaper.create", True)
    feedback = await ml.get(db, ctx, identifier, "feedback")
    if feedback.engagement_id != eid or not feedback.parent_id:
        raise HTTPException(422, "Scoped prediction feedback required")
    await require_ml_current(db, ctx, feedback)
    prediction = await ml.get(db, ctx, feedback.parent_id, "inference")
    evidence = await s.get_record(db, ctx, eid, uuid.UUID(feedback.body["evidence_id"]))
    if evidence.status not in {"APPROVED", "LOCKED"}:
        raise HTTPException(409, "Current reviewed supporting audit evidence required")
    from app.modules.lineage.working_papers import require_current

    await require_current(db, ctx, evidence)
    key = ":".join(
        str(v)
        for v in [
            prediction.body.get("model_id", "explicit-baseline"),
            prediction.body.get("dataset_id", prediction.parent_id),
            feedback.body["transaction_id"],
        ]
    )
    reference = "MLR-" + hashlib.sha256(key.encode()).hexdigest()[:24]
    existing = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "working-papers",
            AuditRecord.reference == reference,
        )
    )
    if existing:
        return s.serialize(existing)
    return await s.create(
        db,
        ctx,
        eid,
        "working-papers",
        RecordInput(
            reference=reference,
            title="Journal analytics review: " + feedback.body["transaction_id"][:100],
            body={
                "folder": "Journal analytics",
                "sections": [
                    {
                        "heading": "Original prediction",
                        "text": f"Mode {prediction.body.get('execution_mode', 'unavailable')}; score {feedback.body.get('original_score')}. Indicator only; not a fraud probability or confirmed finding.",
                    },
                    {
                        "heading": "Retained human disposition",
                        "text": feedback.body["label"] + ": " + feedback.body["rationale"],
                    },
                ],
                "conclusion": feedback.body["rationale"],
                "sources": [
                    {"kind": "ml", "id": str(feedback.id)},
                    {"kind": "record", "id": str(evidence.id)},
                ],
            },
        ),
        request.state.request_id,
    )


@router.get("/records/{rid}")
async def record_detail(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    return s.serialize(await s.get_record(db, ctx, eid, rid))


@router.get("/dependencies")
async def dependencies(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    from app.modules.lineage.registry import registry

    return await registry(db, ctx, eid, offset, limit)


@router.get("/graph")
async def relationship_graph(
    eid: uuid.UUID, db: DB, ctx: Actor, limit: int = Query(300, ge=1, le=1000)
):
    from app.modules.lineage.working_papers import graph

    return await graph(db, ctx, eid, limit)


@router.get("/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    eng = await s.engagement(db, ctx, eid)
    codes, roles = await engagement_permissions(db, ctx, eid, "audit.read")
    p = await s.policy(db, ctx, eid)
    counts = (
        await db.execute(
            select(AuditRecord.kind, AuditRecord.status, func.count())
            .where(AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid)
            .group_by(AuditRecord.kind, AuditRecord.status)
        )
    ).all()
    return {
        "engagement": s.serialize(eng),
        "permissions": sorted(codes),
        "roles": sorted(roles),
        "policy": s.serialize(p),
        "counts": [{"kind": k, "status": st, "count": n} for k, st, n in counts],
        "transitions": sorted(TRANSITIONS.get(eng.status.upper(), [])),
        "areas": AREAS,
        "assertions": ASSERTIONS,
        "ai_tasks": AI_TASKS,
        "schemas": {k: v.model_json_schema() for k, v in BODIES.items() if k != "ai"},
    }


@router.get("/team")
async def team(eid: uuid.UUID, db: DB, ctx: Actor):
    await s.engagement(db, ctx, eid)
    rows = (
        await db.scalars(
            select(AuditAccess).where(
                AuditAccess.tenant_id == ctx.tenant_id, AuditAccess.engagement_id == eid
            )
        )
    ).all()
    from app.db.models.platform import User

    result = []
    for r in rows:
        member = await db.get(Membership, r.membership_id)
        user = await db.get(User, member.user_id) if member else None
        role = await db.get(Role, r.role_id)
        result.append(
            {
                **s.serialize(r),
                "user_id": str(user.id) if user else None,
                "email": user.email if user else None,
                "role_name": role.name if role else None,
            }
        )
    return {"items": result}


@router.get("/linkable-sources")
async def linkable_sources(
    eid: uuid.UUID, db: DB, ctx: Actor, search: str = Query("", max_length=200)
):
    eng = await s.engagement(db, ctx, eid)
    source_permissions, _ = await engagement_permissions(db, ctx, eid, "audit.read")
    from app.modules.accounting.models import Finding, ImportSnapshot, JournalLine, SamplingRun

    result: list[dict] = []
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.title.icontains(search, autoescape=True),
                AuditRecord.status != "ARCHIVED",
            )
            .order_by(AuditRecord.updated_at.desc())
            .limit(40)
        )
    ).all()
    result.extend(
        {"id": str(r.id), "kind": "record", "label": r.reference + " â€” " + r.title}
        for r in rows
        if "ifrs.read" in source_permissions or not r.kind.startswith("ifrs-")
        if "tax.profile.read" in source_permissions or not r.kind.startswith("tax-")
        if "vat.read" in source_permissions or not r.kind.startswith("vat-")
        if "tp.read" in source_permissions or not r.kind.startswith("tp-")
        if not r.kind.startswith("grc-")
        if "dmtt.read" in source_permissions or not r.kind.startswith("dmtt-")
    )
    source_models: list[tuple[str, Any]] = [
        ("snapshot", ImportSnapshot),
        ("sample", SamplingRun),
        ("finding", Finding),
        ("journal", JournalLine),
    ]
    for kind, model in source_models:
        scoped_rows = (
            await db.scalars(
                select(model)
                .where(
                    model.tenant_id == ctx.tenant_id,
                    model.entity_id == eng.entity_id,
                    model.period_id == eng.period_id,
                )
                .order_by(model.created_at.desc())
                .limit(15)
            )
        ).all()
        result.extend(
            {
                "id": str(r.id),
                "kind": kind,
                "label": kind.title() + " â€” " + getattr(r, "rule_id", str(r.id)[:8]),
            }
            for r in scoped_rows
        )
    return {"items": result}


@router.get("/team-candidates")
async def candidates(eid: uuid.UUID, db: DB, ctx: Actor, kind: str = "members"):
    from app.db.models.platform import User

    await s.engagement(db, ctx, eid, "engagement.assign")
    if kind == "roles":
        rows = (
            await db.scalars(
                select(Role)
                .where(~Role.name.startswith("Platform"), ~Role.name.startswith("Client"))
                .order_by(Role.name)
            )
        ).all()
        return {"items": [{"id": str(r.id), "name": r.name} for r in rows]}
    members = (
        await db.execute(
            select(Membership.id, User.email)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == ctx.tenant_id,
                Membership.status == "active",
                User.status == "active",
            )
            .order_by(User.email)
            .limit(100)
        )
    ).all()
    return {"items": [{"id": str(mid), "email": email} for mid, email in members]}


@router.post("/team")
async def assign(eid: uuid.UUID, data: Grant, db: DB, ctx: Actor, request: Request):
    await s.engagement(db, ctx, eid, "engagement.assign", True)
    member = await db.scalar(
        select(Membership).where(
            Membership.id == data.membership_id,
            Membership.tenant_id == ctx.tenant_id,
            Membership.status == "active",
        )
    )
    role = await db.get(Role, data.role_id)
    if not member or not role or role.name.startswith(("Platform", "Client")):
        raise HTTPException(422, "Active firm member and audit role required")
    if role.name == "Quality Reviewer":
        existing = await db.scalar(
            select(AuditAccess.id)
            .join(Role, Role.id == AuditAccess.role_id)
            .where(
                AuditAccess.engagement_id == eid,
                AuditAccess.tenant_id == ctx.tenant_id,
                AuditAccess.membership_id == member.id,
                Role.name != "Quality Reviewer",
            )
        )
        prepared = await db.scalar(
            select(AuditRevision.id)
            .join(AuditRecord, AuditRecord.id == AuditRevision.record_id)
            .where(
                AuditRecord.engagement_id == eid,
                AuditRevision.snapshot["prepared_by"].astext == str(member.user_id),
            )
        )
        if existing or prepared:
            raise HTTPException(409, "Quality reviewer cannot be part of the delivery team")
    else:
        qr = await db.scalar(
            select(AuditAccess.id)
            .join(Role, Role.id == AuditAccess.role_id)
            .where(
                AuditAccess.engagement_id == eid,
                AuditAccess.membership_id == member.id,
                AuditAccess.active.is_(True),
                Role.name == "Quality Reviewer",
            )
        )
        if qr:
            raise HTTPException(409, "Independent quality reviewer cannot join delivery team")
    obj = await db.scalar(
        select(AuditAccess).where(
            AuditAccess.engagement_id == eid,
            AuditAccess.membership_id == member.id,
            AuditAccess.role_id == role.id,
        )
    )
    if obj:
        obj.active, obj.expires_at = data.active, data.expires_at
    else:
        obj = AuditAccess(
            tenant_id=ctx.tenant_id, created_by=ctx.user_id, engagement_id=eid, **data.model_dump()
        )
        db.add(obj)
    await db.flush()
    await db.refresh(obj)
    record(
        db,
        ctx,
        "audit.team.assigned",
        obj.id,
        request.state.request_id,
        {"engagement_id": str(eid), "active": obj.active},
    )
    return s.serialize(obj)


@router.post("/policy")
async def configure(eid: uuid.UUID, data: PolicyInput, db: DB, ctx: Actor, request: Request):
    eng = await s.engagement(db, ctx, eid, "engagement.assign", True)
    if eng.status.upper() not in {"DRAFT", "ACCEPTANCE_PENDING"}:
        raise HTTPException(409, "Configure review policy before acceptance")
    valid = set((await db.scalars(select(Role.name))).all())
    if not set(data.review_chain) <= valid or any(
        x.startswith(("Client", "Platform")) for x in data.review_chain
    ):
        raise HTTPException(422, "Unknown review role")
    if "quality_review_decision" in data.methodology:
        raise HTTPException(422, "Quality review decisions use the controlled endpoint")
    p = await s.policy(db, ctx, eid)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    record(db, ctx, "audit.policy.updated", p.id, request.state.request_id)
    await db.flush()
    await db.refresh(p)
    return s.serialize(p)


@router.post("/quality-review")
async def quality(eid: uuid.UUID, data: Action, db: DB, ctx: Actor, request: Request):
    eng = await s.engagement(db, ctx, eid, "engagement.quality_review", True)
    _, roles = await engagement_permissions(db, ctx, eid, "engagement.quality_review")
    if "Quality Reviewer" not in roles or eng.status.upper() != "QUALITY_REVIEW":
        raise HTTPException(
            403, "Assigned independent quality reviewer required during quality review"
        )
    if eng.version != data.version or data.action != "approve":
        raise HTTPException(409, "Quality review version or action invalid")
    rows = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.engagement_id == eid, AuditRecord.tenant_id == ctx.tenant_id
            )
        )
    ).all()
    if any(r.prepared_by == ctx.user_id and r.kind != "independence" for r in rows):
        raise HTTPException(403, "Quality reviewer independence restriction")
    declaration = any(
        r.kind == "independence"
        and r.prepared_by == ctx.user_id
        and r.status in {"APPROVED", "LOCKED"}
        for r in rows
    )
    if not declaration:
        raise HTTPException(409, "Approved independence declaration required")
    from app.modules.audit_execution.completion_sources import reviewed_source_control

    if not (await reviewed_source_control(db, ctx, rows))["passed"]:
        raise HTTPException(409, "Current reviewed sources are required before quality approval")
    p = await s.policy(db, ctx, eid)
    from datetime import UTC, datetime

    if p.methodology.get("quality_review_decision"):
        raise HTTPException(409, "Current engagement version already has a quality review decision")

    p.methodology = {
        **p.methodology,
        "quality_review_decision": {
            "user_id": str(ctx.user_id),
            "at": datetime.now(UTC).isoformat(),
            "comments": data.comments,
            "engagement_version": eng.version,
        },
    }
    record(
        db,
        ctx,
        "audit.quality.approved",
        eid,
        request.state.request_id,
        p.methodology["quality_review_decision"],
    )
    return {"status": "APPROVED"}


@router.post("/transition")
async def transition(eid: uuid.UUID, data: Action, db: DB, ctx: Actor, request: Request):
    return await s.transition(db, ctx, eid, data, request.state.request_id)


@router.get("/completion-checks")
async def completion(eid: uuid.UUID, db: DB, ctx: Actor):
    return await s.completion(db, ctx, eid)


@router.post("/select-sample", status_code=201)
async def select_sample(eid: uuid.UUID, data: SamplingRequest, db: DB, ctx: Actor):
    from app.modules.audit_analytics.service import sampling
    from app.modules.audit_execution.schemas import Source

    eng = await s.engagement(db, ctx, eid, "audit.testing.execute", True)
    await s.source_record(db, ctx, eng, Source(kind="snapshot", id=data.snapshot_id))
    return await sampling(db, ctx, data, engagement_id=eid)


@router.get("/review-queue")
async def review_queue(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await s.engagement(db, ctx, eid, "workingpaper.review")
    conditions = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.status.in_(["REVIEW_REQUIRED", "REVIEW_NOTES", "REVISED"]),
    ]
    rows = (
        await db.scalars(
            select(AuditRecord)
            .where(*conditions)
            .order_by(AuditRecord.updated_at, AuditRecord.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [s.serialize(r) for r in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.get("/records/{rid}/history")
async def history(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await s.get_record(db, ctx, eid, rid)
    return {
        "versions": [
            s.serialize(r)
            for r in (
                await db.scalars(
                    select(AuditRevision)
                    .where(AuditRevision.tenant_id == ctx.tenant_id, AuditRevision.record_id == rid)
                    .order_by(AuditRevision.version)
                )
            ).all()
        ],
        "decisions": [
            s.serialize(r)
            for r in (
                await db.scalars(
                    select(ReviewDecision)
                    .where(
                        ReviewDecision.tenant_id == ctx.tenant_id, ReviewDecision.record_id == rid
                    )
                    .order_by(ReviewDecision.created_at)
                )
            ).all()
        ],
    }


@router.patch("/records/{rid}")
async def update(
    eid: uuid.UUID, rid: uuid.UUID, data: RecordPatch, db: DB, ctx: Actor, request: Request
):
    return await s.update(db, ctx, eid, rid, data, request.state.request_id)


@router.post("/records/{rid}/actions")
async def action(
    eid: uuid.UUID, rid: uuid.UUID, data: Action, db: DB, ctx: Actor, request: Request
):
    return await s.action(db, ctx, eid, rid, data, request.state.request_id)


@router.get("/{kind}")
async def listing(
    eid: uuid.UUID,
    kind: str,
    db: DB,
    ctx: Actor,
    search: str = Query("", max_length=200),
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await s.engagement(db, ctx, eid)
    if kind.startswith("ifrs-"):
        await engagement_permissions(db, ctx, eid, "ifrs.read")
    if kind.startswith("tax-"):
        await engagement_permissions(db, ctx, eid, "tax.profile.read")
    if kind.startswith("vat-"):
        await engagement_permissions(db, ctx, eid, "vat.read")
    if kind.startswith("tp-"):
        await engagement_permissions(db, ctx, eid, "tp.read")
    if kind.startswith("grc-"):
        raise HTTPException(403, "Use the owner-scoped GRC register endpoint")
    if kind.startswith("dmtt-"):
        await engagement_permissions(db, ctx, eid, "dmtt.read")
    if kind not in BODIES:
        raise HTTPException(404, "Unknown audit area")
    conditions = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == kind,
    ]
    if search:
        conditions.append(
            or_(
                AuditRecord.title.icontains(search, autoescape=True),
                AuditRecord.reference.icontains(search, autoescape=True),
            )
        )
    if status:
        conditions.append(AuditRecord.status == status)
    else:
        conditions.append(AuditRecord.status != "ARCHIVED")
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
        "items": [s.serialize(r) for r in rows],
        "total": await db.scalar(select(func.count()).select_from(AuditRecord).where(*conditions)),
        "offset": offset,
        "limit": limit,
    }


@router.post("/{kind}", status_code=201)
async def create(
    eid: uuid.UUID, kind: str, data: RecordInput, db: DB, ctx: Actor, request: Request
):
    return await s.create(db, ctx, eid, kind, data, request.state.request_id)

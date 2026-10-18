import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select, text

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB, Context, require
from app.db.models.platform import AuditEvent
from app.modules.audit_execution import service as s
from app.modules.audit_execution.catalogue import AREAS, ASSERTIONS
from app.modules.audit_execution.models import MethodologyVersion
from app.modules.audit_execution.schemas import RecordInput, Strict
from app.modules.audit_log.service import record

router = APIRouter(tags=["Versioned audit methodology"])
Admin = Annotated[Context, Depends(require("methodology.manage"))]


class TemplateProcedure(Strict):
    code: str = Field(min_length=1, max_length=100)
    area: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=4000)
    assertions: list[str] = Field(max_length=9)
    instructions: str = Field(min_length=1, max_length=4000)
    required_evidence: str = Field(min_length=1, max_length=4000)


class Profile(Strict):
    reporting_period_start: str
    reporting_period_end: str
    standards_edition: str = Field(min_length=1, max_length=300)
    applicability_rationale: str = Field(min_length=1, max_length=4000)
    professional_validation: str = Field(min_length=1, max_length=4000)
    procedures: list[TemplateProcedure] = Field(min_length=1, max_length=300)
    working_paper_templates: list[dict] = Field(default_factory=list, max_length=30)
    independence_questions: list[str] = Field(default_factory=list, max_length=50)
    materiality_benchmarks: list[str] = Field(default_factory=list, max_length=20)


class VersionInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    previous_version: int = Field(ge=0)
    effective_from: datetime
    profile: Profile


@router.get("/admin/methodology/starter")
async def starter(ctx: Admin):
    return {
        "name": "Original statutory audit starter",
        "previous_version": 0,
        "effective_from": "2026-01-01T00:00:00Z",
        "profile": {
            "reporting_period_start": "2026-01-01",
            "reporting_period_end": "2026-12-31",
            "standards_edition": "IAASB handbook: validate applicable editions for period and UAE adoption",
            "applicability_rationale": "Draft profile; requires firm technical validation",
            "professional_validation": "Not yet validated: replace with human technical review",
            "independence_questions": [
                "Disclose financial interests",
                "Disclose family and business relationships",
                "Disclose other services and threats",
                "Document safeguards and expiry",
            ],
            "materiality_benchmarks": [
                "profit_before_tax",
                "revenue",
                "assets",
                "equity",
                "expenses",
                "other",
            ],
            "working_paper_templates": [
                {
                    "folder": "Planning",
                    "sections": [
                        {"heading": "Objective", "text": ""},
                        {"heading": "Work performed", "text": ""},
                        {"heading": "Results and professional conclusion", "text": ""},
                    ],
                }
            ],
            "procedures": [
                {
                    "code": f"AREA-{i:02}",
                    "area": area,
                    "objective": f"Evaluate supported assertions for {area.lower()} in the engagement scope",
                    "assertions": ["completeness", "presentation"],
                    "instructions": f"Identify relevant risks for {area.lower()}; document the tailored response, select appropriate source records, inspect original supporting evidence and investigate exceptions. Record work performed and the limitations of the evidence obtained.",
                    "required_evidence": f"Source population, reconciliation and original documentation relevant to {area.lower()}; tailor before execution",
                }
                for i, area in enumerate(AREAS, 1)
            ],
        },
    }


@router.get("/admin/methodology")
async def versions(db: DB, ctx: Admin):
    rows = (
        await db.scalars(
            select(MethodologyVersion)
            .where(MethodologyVersion.tenant_id == ctx.tenant_id)
            .order_by(MethodologyVersion.created_at.desc())
            .limit(100)
        )
    ).all()
    return {"items": [s.serialize(r) for r in rows]}


@router.post("/admin/methodology", status_code=201)
async def create(data: VersionInput, db: DB, ctx: Admin, request: Request):
    if any(not set(p.assertions) <= set(ASSERTIONS) for p in data.profile.procedures):
        raise HTTPException(422, "Unknown assertion")
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": str(ctx.tenant_id) + data.name},
    )
    current = (
        await db.scalar(
            select(func.max(MethodologyVersion.version)).where(
                MethodologyVersion.tenant_id == ctx.tenant_id, MethodologyVersion.name == data.name
            )
        )
        or 0
    )
    if current != data.previous_version:
        raise HTTPException(409, "Methodology version conflict")
    obj = MethodologyVersion(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        name=data.name,
        version=current + 1,
        effective_from=data.effective_from,
        profile=data.profile.model_dump(mode="json"),
    )
    db.add(obj)
    await db.flush()
    record(db, ctx, "methodology.version.created", obj.id, request.state.request_id)
    return s.serialize(obj)


class Approval(Strict):
    rationale: str = Field(min_length=1, max_length=4000)


@router.post("/admin/methodology/{mid}/approve")
async def approve(mid: uuid.UUID, data: Approval, db: DB, ctx: Admin, request: Request):
    obj = await db.scalar(
        select(MethodologyVersion).where(
            MethodologyVersion.id == mid, MethodologyVersion.tenant_id == ctx.tenant_id
        )
    )
    if not obj:
        raise HTTPException(404, "Methodology not found")
    if obj.created_by == ctx.user_id:
        raise HTTPException(403, "Independent methodology approval required")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": str(mid)})
    if await db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.resource_id == mid,
            AuditEvent.tenant_id == ctx.tenant_id,
            AuditEvent.action == "methodology.approved",
        )
    ):
        raise HTTPException(409, "Methodology version already approved")
    record(
        db,
        ctx,
        "methodology.approved",
        mid,
        request.state.request_id,
        {"version": obj.version, "rationale": data.rationale},
    )
    return {"status": "APPROVED"}


@router.post("/engagements/{eid}/audit/methodology/{mid}/instantiate", status_code=201)
async def instantiate(eid: uuid.UUID, mid: uuid.UUID, db: DB, ctx: Actor, request: Request):
    await s.engagement(db, ctx, eid, "audit.program.prepare", True)
    obj = await db.scalar(
        select(MethodologyVersion).where(
            MethodologyVersion.id == mid, MethodologyVersion.tenant_id == ctx.tenant_id
        )
    )
    approved = await db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.resource_id == mid,
            AuditEvent.tenant_id == ctx.tenant_id,
            AuditEvent.action == "methodology.approved",
        )
    )
    if not obj or not approved:
        raise HTTPException(409, "Approved methodology version required")
    from app.db.models.platform import Engagement, FinancialPeriod

    eng = await db.get(Engagement, eid)
    period = await db.get(FinancialPeriod, eng.period_id) if eng and eng.period_id else None
    if (
        not period
        or str(period.start_date) != obj.profile["reporting_period_start"]
        or str(period.end_date) != obj.profile["reporting_period_end"]
    ):
        raise HTTPException(
            409,
            "Methodology reporting-period applicability differs; create an appropriate validated version",
        )
    result = []
    for p in obj.profile["procedures"]:
        result.append(
            await s.create(
                db,
                ctx,
                eid,
                "procedures",
                RecordInput(
                    reference=p["code"],
                    title=p["area"] + " — " + p["objective"][:180],
                    body={
                        "area": p["area"],
                        "methodology_version": str(obj.id),
                        "objective": p["objective"],
                        "assertions": p["assertions"],
                        "instructions": p["instructions"],
                        "required_evidence": p["required_evidence"],
                    },
                ),
                request.state.request_id,
            )
        )
    return {"items": result, "methodology_version": str(obj.id)}

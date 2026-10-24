import uuid
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import func, or_, select

from app.core.dependencies import DB, Context, require
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import BODIES as AUDIT_BODIES
from app.modules.audit_execution.schemas import RecordInput, Strict
from app.modules.ifrs import service
from app.modules.ifrs.catalogue import AI_TASKS, KINDS
from app.modules.ifrs.models import CalculationRun, StandardVersion
from app.modules.ifrs.schemas import BODIES

for name, schema in BODIES.items():
    AUDIT_BODIES["ifrs-" + name] = schema
for name, (prepare, approve) in KINDS.items():
    PREPARE["ifrs-" + name] = prepare
    APPROVE["ifrs-" + name] = approve

router = APIRouter(prefix="/ifrs", tags=["IFRS reporting"])
Actor = Annotated[Context, Depends(require(""))]


class JournalProposal(Strict):
    profile_id: uuid.UUID
    reference: str = Field(min_length=1, max_length=100)
    debit_account: str = Field(min_length=1, max_length=100)
    credit_account: str = Field(min_length=1, max_length=100)
    adjustment_date: date
    rationale: str = Field(min_length=1, max_length=4000)
    existing_allowance: Decimal = Field(default=Decimal(0), ge=0, max_digits=28, decimal_places=8)
    component: str = Field(default="primary", pattern=r"^(primary|oci|current_tax)$")


@router.post("/engagements/{eid}/runs/{rid}/propose-journal", status_code=201)
async def propose(
    eid: uuid.UUID, rid: uuid.UUID, data: JournalProposal, db: DB, ctx: Actor, request: Request
):
    await audit.engagement(db, ctx, eid, "ifrs.adjustment.prepare", True)
    calc = await service.run(db, ctx, eid, rid)
    if not await service.current_dependencies(db, ctx, eid, calc):
        raise HTTPException(409, "Calculation inputs changed; regenerate")
    profile = await service.record(db, ctx, eid, data.profile_id, "profile", True)
    if calc.inputs.get("profile_id") and calc.inputs["profile_id"] != str(profile.id):
        raise HTTPException(422, "Journal profile differs from approved calculation profile")
    if any(issue.get("blocking") for issue in calc.results.get("issues", [])):
        raise HTTPException(
            409, "Resolve supporting schedule issues before proposing an adjustment"
        )
    if data.component != "primary" and not (
        calc.kind == "deferred-tax" or calc.kind == "employee-benefits" and data.component == "oci"
    ):
        raise HTTPException(422, "This schedule does not support the selected journal component")
    if calc.kind == "lease":
        if calc.inputs.get("previous_run_id"):
            raise HTTPException(
                409,
                "Lease modifications require reviewed modification journals; initial-recognition proposal would duplicate the liability",
            )
        value = Decimal(calc.results["initial_liability"])
        standard = "IFRS 16"
    elif calc.kind == "ecl":
        value = Decimal(calc.results["total_ecl"]) - data.existing_allowance
        standard = "IFRS 9"
    elif calc.kind == "fixed-assets":
        value, standard = Decimal(calc.results["total_depreciation"]), "IAS 16"
    elif calc.kind == "inventory":
        value, standard = Decimal(calc.results["write_down_movement"]), "IAS 2"
    elif calc.kind == "impairment":
        value = Decimal(calc.results["impairment_loss"]) - Decimal(
            calc.results["permitted_reversal_excluding_goodwill"]
        )
        standard = "IAS 36"
    elif calc.kind == "employee-benefits":
        value = Decimal(
            calc.results["oci_movement" if data.component == "oci" else "profit_loss_movement"]
        )
        standard = "IAS 19"
    elif calc.kind == "deferred-tax":
        if data.component == "current_tax":
            if not calc.results.get("current_tax_bridge"):
                raise HTTPException(409, "Current-tax proposal requires an approved E05 bridge")
            value = Decimal(calc.results["current_tax_bridge"]["amount"])
        else:
            value = Decimal(
                calc.results["movements"].get(
                    "oci" if data.component == "oci" else "profit_loss", "0"
                )
            )
        standard = "IAS 12"
    else:
        raise HTTPException(422, "No supported journal movement for this calculation kind")
    from app.modules.ifrs.contracts import currency_receipt

    policy = await currency_receipt(db, ctx, profile.body["presentation_currency"])
    value = value.quantize(Decimal(1).scaleb(-policy["precision"]), rounding=policy["rounding"])
    existing = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "ifrs-adjustment",
            or_(
                AuditRecord.reference == data.reference,
                AuditRecord.body["calculation_run_id"].astext.in_(
                    service.equivalent_runs(ctx, eid, calc)
                )
                & (AuditRecord.body["calculation_component"].astext == data.component),
            ),
        )
    )
    if existing:
        raise HTTPException(
            409,
            "Journal reference or calculation/component already exists; review the retained proposal instead of duplicating it",
        )
    if not value or data.debit_account == data.credit_account:
        raise HTTPException(422, "Nonzero movement and distinct human-selected accounts required")
    debit, credit = (
        (data.debit_account, data.credit_account)
        if value > 0
        else (data.credit_account, data.debit_account)
    )
    return await audit.create(
        db,
        ctx,
        eid,
        "ifrs-adjustment",
        RecordInput(
            reference=data.reference,
            title="Proposed " + standard + " calculation journal",
            body={
                "profile_id": str(profile.id),
                "adjustment_date": str(data.adjustment_date),
                "currency": profile.body["presentation_currency"],
                "standard": standard,
                "narration": data.rationale + "; source run " + str(rid),
                "calculation_run_id": str(rid),
                "calculation_component": data.component,
                "legs": [
                    {"account_code": debit, "debit": str(abs(value))},
                    {"account_code": credit, "credit": str(abs(value))},
                ],
            },
        ),
        request.state.request_id,
    )


@router.get("/standards")
async def standards(db: DB, ctx: Annotated[Context, Depends(require("ifrs.read"))]):
    rows = (
        await db.scalars(
            select(StandardVersion).order_by(
                StandardVersion.code, StandardVersion.rule_version.desc()
            )
        )
    ).all()
    return {"items": [audit.serialize(r) for r in rows], "full_ifrs_text_licensed": False}


@router.get("/engagements/{eid}/workspace")
async def workspace(eid: uuid.UUID, db: DB, ctx: Actor):
    eng = await audit.engagement(db, ctx, eid, "ifrs.read")
    from app.modules.audit_execution.access import engagement_permissions

    permissions, roles = await engagement_permissions(db, ctx, eid, "ifrs.read")
    return {
        "engagement": audit.serialize(eng),
        "permissions": sorted(permissions),
        "roles": sorted(roles),
        "schemas": {k: v.model_json_schema() for k, v in BODIES.items()},
        "kinds": list(BODIES),
        "ai_tasks": AI_TASKS,
        "methodology_version": "auditos-accounting/3.1",
        "accounting_contract_version": "accounting/1",
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
    await audit.engagement(db, ctx, eid, "ifrs.read")
    if kind not in KINDS:
        raise HTTPException(404, "Unknown IFRS workbench")
    conditions = [
        AuditRecord.tenant_id == ctx.tenant_id,
        AuditRecord.engagement_id == eid,
        AuditRecord.kind == "ifrs-" + kind,
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
        raise HTTPException(422, "Unknown editable IFRS kind")
    return await audit.create(db, ctx, eid, "ifrs-" + kind, data, request.state.request_id)


@router.post("/engagements/{eid}/calculate/{rid}", status_code=201)
async def calculate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    return await service.calculate_record(db, ctx, eid, rid)


@router.get("/engagements/{eid}/runs")
async def runs(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    kind: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await audit.engagement(db, ctx, eid, "ifrs.read")
    conditions = [CalculationRun.tenant_id == ctx.tenant_id, CalculationRun.engagement_id == eid]
    if kind:
        conditions.append(CalculationRun.kind == kind)
    rows = (
        await db.scalars(
            select(CalculationRun)
            .where(*conditions)
            .order_by(CalculationRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "created_at": r.created_at,
                "sha256": r.sha256,
                "record_id": str(r.record_id) if r.record_id else None,
            }
            for r in rows
        ],
        "total": await db.scalar(
            select(func.count()).select_from(CalculationRun).where(*conditions)
        ),
        "offset": offset,
        "limit": limit,
    }


@router.get("/engagements/{eid}/runs/{rid}")
async def result(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    calc = await service.run(db, ctx, eid, rid)
    return {
        **audit.serialize(calc),
        "dependencies_current": await service.current_dependencies(db, ctx, eid, calc),
    }


@router.post("/engagements/{eid}/financial-statements/{profile_id}", status_code=201)
async def financials(eid: uuid.UUID, profile_id: uuid.UUID, db: DB, ctx: Actor):
    with localcontext() as precision:
        precision.prec = 48
        return await service.financials(db, ctx, eid, profile_id)


@router.get("/engagements/{eid}/adjusted-trial-balance/{profile_id}")
async def adjusted(eid: uuid.UUID, profile_id: uuid.UUID, db: DB, ctx: Actor):
    with localcontext() as precision:
        precision.prec = 48
        profile, tb, rows, deps = await service.adjusted_balance(db, ctx, eid, profile_id)
    from app.modules.ifrs.calculations import serial

    return serial(
        {
            "profile_id": str(profile.id),
            "snapshot_id": tb["snapshot_id"],
            "currency": tb["functional_currency"],
            "lines": rows,
            "dependencies": deps,
        }
    )


@router.post("/engagements/{eid}/consolidation/{rid}", status_code=201)
async def consolidate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    with localcontext() as precision:
        precision.prec = 48
        return await service.consolidate(db, ctx, eid, rid)


@router.get("/engagements/{eid}/runs/{rid}/validate")
async def validate(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    calc = await service.run(db, ctx, eid, rid)
    return {
        "validation": calc.results.get("validation"),
        "dependencies_current": await service.current_dependencies(db, ctx, eid, calc),
        "sha256": calc.sha256,
    }


@router.get("/engagements/{eid}/runs/{rid}/review")
async def review(
    eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor, comparison_run_id: uuid.UUID | None = None
):
    from app.modules.ifrs.review import review_statements

    calc = await service.run(db, ctx, eid, rid)
    if calc.kind != "financials":
        raise HTTPException(422, "Structured single-entity financial statements required")
    previous = None
    if comparison_run_id:
        previous = await service.run(db, ctx, eid, comparison_run_id)
        if previous.kind != "financials" or any(
            previous.results.get(k) != calc.results.get(k)
            for k in ("entity_id", "currency", "period_start", "period_end")
        ):
            raise HTTPException(
                422, "Draft comparison requires the same entity, currency and reporting period"
            )
        if previous.id == calc.id or previous.created_at > calc.created_at:
            raise HTTPException(422, "Select a distinct earlier financial statement version")
    current = await service.current_dependencies(db, ctx, eid, calc)
    result = review_statements(calc.results, previous.results if previous else None)
    return {
        **result,
        "ready": result["ready"] and current,
        "dependencies_current": current,
        "run_id": str(calc.id),
        "sha256": calc.sha256,
        "comparison_run_id": str(previous.id) if previous else None,
    }


@router.get("/engagements/{eid}/runs/{rid}/export/{format}")
async def export(eid: uuid.UUID, rid: uuid.UUID, format: str, db: DB, ctx: Actor, request: Request):
    from app.modules.audit_log.service import record as log
    from app.modules.ifrs.exports import render

    await audit.engagement(db, ctx, eid, "ifrs.report.export")
    if format not in {"json", "pdf", "docx", "xlsx"}:
        raise HTTPException(422, "Supported formats: json, pdf, docx, xlsx")
    calc = await service.run(db, ctx, eid, rid)
    current = await service.current_dependencies(db, ctx, eid, calc)
    approval = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "ifrs-financials",
            AuditRecord.status.in_(service.APPROVED),
            AuditRecord.body["run_id"].astext == str(rid),
        )
    )
    released = bool(approval and current and calc.results.get("validation", {}).get("ready"))
    if released and calc.kind == "financials":
        from app.modules.ifrs.review import review_statements

        released = review_statements(calc.results)["ready"]
    content, mime = render(
        calc, format, released, approval.body.get("review_approvers", []) if approval else []
    )
    log(
        db,
        ctx,
        "ifrs.export",
        rid,
        request.state.request_id,
        {"format": format, "released": released, "sha256": calc.sha256},
    )
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="AuditOS-{rid}-{"reviewed" if released else "draft"}.{format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

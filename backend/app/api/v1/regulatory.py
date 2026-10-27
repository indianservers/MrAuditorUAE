import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import or_, select
from starlette.concurrency import run_in_threadpool

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.modules.audit_execution import service as audit
from app.modules.intelligence import service as intelligence
from app.modules.regulatory import schemas as s
from app.modules.regulatory import service, source_documents
from app.modules.regulatory.conversion import ConversionInput
from app.modules.regulatory.exposure_rollup import ExposureRollupInput
from app.modules.regulatory.models import RuleSourceDocument, RuleVersion
from app.modules.regulatory.validation_schemas import ValidationInput

router = APIRouter(prefix="/regulatory", tags=["Regulatory rule library"])


@router.post("/sources", status_code=201)
async def retain_source(
    db: DB,
    ctx: Actor,
    request: Request,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form(max_length=10000)],
):
    await service.authorize(db, ctx, "tax.rules.manage")
    try:
        selected = s.SourceDocumentMetadata.model_validate_json(metadata)
    except ValidationError:
        raise HTTPException(422, "Invalid regulatory source metadata") from None
    return source_documents.info(
        await source_documents.upload(db, ctx, file, selected, request.state.request_id)
    )


@router.get("/sources")
async def source_library(
    db: DB,
    ctx: Actor,
    country: str | None = Query(None, pattern="^[A-Z]{2}$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await service.authorize_read(db, ctx)
    query = select(RuleSourceDocument).where(RuleSourceDocument.tenant_id == ctx.tenant_id)
    if country:
        query = query.where(RuleSourceDocument.country.in_([country, "GLOBAL"]))
    documents = (
        await db.scalars(
            query.order_by(RuleSourceDocument.created_at.desc(), RuleSourceDocument.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [source_documents.info(document) for document in documents],
        "offset": offset,
        "limit": limit,
    }


@router.get("/sources/{identifier}/download")
async def download_source(identifier: uuid.UUID, db: DB, ctx: Actor, request: Request):
    from urllib.parse import quote

    await service.authorize_read(db, ctx)
    document = await source_documents.get(db, ctx, identifier)
    try:
        content = await run_in_threadpool(source_documents.read, document, download=True)
    except (ValueError, OSError):
        raise HTTPException(
            409, "Retained regulatory source failed original-file integrity"
        ) from None
    record_metadata = {"sha256": document.sha256}
    from app.modules.audit_log.service import record

    record(
        db,
        ctx,
        "regulatory.source_downloaded",
        document.id,
        request.state.request_id,
        record_metadata,
    )
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(document.filename),
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    decision = await service.state(db, ctx, obj)
    receipt = decision.body.get("fixture_validation") if decision else None
    fixture_status = "NOT_RECORDED"
    if decision and decision.state == "WITHDRAWN":
        fixture_status = "WITHDRAWN"
    elif receipt:
        from app.modules.regulatory.validation import require_current

        try:
            require_current(s.Rule.model_validate(obj.body), obj.sha256, receipt)
            fixture_status = "CURRENT"
        except HTTPException as error:
            if error.status_code != 409:
                raise
            fixture_status = "STALE"
    return {
        **audit.serialize(obj),
        "current_sequence": await service.sequence(db, ctx, obj.rule_key),
        "state": audit.serialize(decision),
        "fixture_validation": {
            "status": fixture_status,
            "case_count": receipt.get("case_count", 0) if receipt else 0,
            "receipt_sha256": receipt.get("receipt_sha256") if receipt else None,
        },
        "validation_blockers": service.validation_blockers(s.Rule.model_validate(obj.body)),
    }


@router.post("/rules/{identifier}/decisions", status_code=201)
async def decide(identifier: uuid.UUID, data: s.Decision, db: DB, ctx: Actor, request: Request):
    return audit.serialize(
        await service.decide(
            db, ctx, await service.get(db, ctx, identifier), data, request.state.request_id
        )
    )


@router.post("/rules/{identifier}/validate")
async def validate_fixtures(
    identifier: uuid.UUID, data: ValidationInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.audit_log.service import record
    from app.modules.regulatory import validation

    await service.authorize_read(db, ctx)
    obj = await service.get(db, ctx, identifier)
    try:
        receipt = await run_in_threadpool(
            validation.run, s.Rule.model_validate(obj.body), obj.sha256, data.cases
        )
    except validation.FixtureMismatch as error:
        from app.modules.jurisdictions.packages import fingerprint

        payload = {
            "contract": validation.CONTRACT,
            "rule_sha256": obj.sha256,
            "method": obj.body["method"],
            "passed": False,
            "case_count": len(data.cases),
            "message": str(error),
            "outcomes": error.outcomes,
            "scope": "SUPPLIED_FIXTURES_ONLY_NOT_LEGAL_QUALIFICATION",
        }
        receipt = {**payload, "receipt_sha256": fingerprint(payload)}
    except (ValueError, ArithmeticError) as error:
        raise HTTPException(
            409,
            {
                "code": "fixture_validation_failed",
                "message": str(error),
                "outcomes": getattr(error, "outcomes", []),
            },
        ) from None
    record(
        db,
        ctx,
        "regulatory.fixtures_checked",
        obj.id,
        request.state.request_id,
        {"receipt_sha256": receipt["receipt_sha256"], "case_count": receipt["case_count"]},
    )
    return receipt


@router.get("/rules/{identifier}/validation-contract")
async def validation_contract(identifier: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.regulatory.validation_schemas import RuleFixture

    await service.authorize_read(db, ctx)
    obj = await service.get(db, ctx, identifier)
    rule = s.Rule.model_validate(obj.body)
    template: dict[str, object] = {"id": "CASE-1", "kind": rule.method, "expected_reference": ""}
    if rule.method in {"checklist", "flat_rate"}:
        template.update(
            period_start=rule.effective_from.isoformat(),
            period_end=(rule.effective_to or rule.effective_from).isoformat(),
            facts={},
            expected_applicability=None,
        )
        if rule.period_basis == "transaction_date":
            template["transaction_date"] = rule.effective_from.isoformat()
    else:
        template.update(as_of=None, expected_state=None)
        template[
            "employee"
            if rule.method == "benefit_profile"
            else "pension_basis"
            if rule.method == "pension_profile"
            else "basis"
        ] = None
        if rule.method in {"payroll_profile", "pension_profile"}:
            template["reported_amount"] = None
    if rule.method != "checklist":
        template["expected_amount"] = None
    return {
        "schema": RuleFixture.model_json_schema(),
        "template": [template],
        "maximum_cases": 20,
        "policy": "Supply independently determined expected outcomes; only anonymized fixture inputs belong in the firm rule library",
    }


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


@router.post("/engagements/{eid}/tax-close-rollups", status_code=201)
async def tax_close_rollup(
    eid: uuid.UUID, data: ExposureRollupInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.regulatory.exposure_rollup import prepare

    eng = await audit.engagement(db, ctx, eid, "workingpaper.create", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))

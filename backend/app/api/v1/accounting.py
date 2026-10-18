import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from pydantic import Field, ValidationError
from sqlalchemy import func, select, text

from app.core.dependencies import DB, Context, require
from app.modules.accounting import models as m
from app.modules.accounting import service
from app.modules.accounting.schemas import (
    AccountAssignment,
    ImportOptions,
    ImportOut,
    Input,
    MappingCreate,
    ReconcileRequest,
    ResourcePage,
    RunOut,
    SamplingRequest,
    SnapshotRequest,
)
from app.modules.audit_analytics import service as analytics_service
from app.modules.audit_analytics.engine import RULES, VERSION
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.audit_log.service import record
from app.modules.financial_ai.schemas import FinancialRequest
from app.modules.financial_ai.service import suggest
from app.modules.reconciliation import service as reconciliation

router = APIRouter(tags=["Accounting and audit intelligence"])
Read = Annotated[Context, Depends(require("accounting.read"))]
Write = Annotated[Context, Depends(require("accounting.import"))]
Map = Annotated[Context, Depends(require("accounting.map"))]
Analyze = Annotated[Context, Depends(require("analytics.run"))]
AnalyzeRead = Annotated[Context, Depends(require("analytics.read"))]
Sample = Annotated[Context, Depends(require("sampling.run"))]
FinancialAI = Annotated[Context, Depends(require("financial_ai.execute"))]


def serialize(obj: Any) -> dict:
    return jsonable_encoder(
        {
            column.name: getattr(obj, column.name)
            for column in obj.__table__.columns
            if column.name != "encrypted_credentials"
        },
        custom_encoder={Decimal: str},
    )


async def page(
    db,
    ctx,
    model,
    offset,
    limit,
    client_id=None,
    entity_id=None,
    period_id=None,
    account_id=None,
    date_from=None,
    date_to=None,
    sort="created_at",
    run_id=None,
    snapshot_id=None,
):
    conditions = [model.tenant_id == ctx.tenant_id]
    if model in {m.JournalLine, m.Journal} and snapshot_id is None:
        conditions.append(
            model.batch_id.in_(
                select(m.ImportBatch.id).where(
                    m.ImportBatch.tenant_id == ctx.tenant_id, m.ImportBatch.status == "active"
                )
            )
        )
    for field, value in [
        ("client_id", client_id),
        ("entity_id", entity_id),
        ("period_id", period_id),
        ("account_id", account_id),
        ("run_id", run_id),
        ("snapshot_id", snapshot_id),
    ]:
        if value is not None:
            if not hasattr(model, field):
                raise HTTPException(422, "Filter unsupported for resource")
            conditions.append(getattr(model, field) == value)
    if date_from or date_to:
        if not hasattr(model, "posting_date"):
            raise HTTPException(422, "Date filters require ledger resource")
        if date_from:
            conditions.append(model.posting_date >= date_from)
        if date_to:
            conditions.append(model.posting_date <= date_to)
    field = sort.lstrip("-")
    if field not in {"created_at", "posting_date", "code", "score", "row_number"} or not hasattr(
        model, field
    ):
        raise HTTPException(422, "Unsupported sort field")
    column = getattr(model, field)
    query = (
        select(model)
        .where(*conditions)
        .order_by(column.desc() if sort.startswith("-") else column.asc(), model.id)
        .offset(offset)
        .limit(limit)
    )
    items = (await db.scalars(query)).all()
    total = await db.scalar(select(func.count()).select_from(model).where(*conditions))
    return {
        "items": [serialize(obj) for obj in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/accounting/imports", response_model=ImportOut, status_code=201)
async def upload(
    db: DB,
    ctx: Write,
    request: Request,
    options: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    try:
        data = ImportOptions.model_validate_json(options)
    except ValidationError:
        raise HTTPException(422, "Invalid import options") from None
    return await service.upload(
        db, ctx, data, file.filename or "", file.file, request.state.request_id
    )


@router.get("/accounting/imports/{identifier}", response_model=dict)
async def get_import(identifier: uuid.UUID, db: DB, ctx: Read):
    batch = await service.scoped(db, ctx, m.ImportBatch, identifier)
    snapshot = await db.scalar(
        select(m.ImportSnapshot).where(
            m.ImportSnapshot.batch_id == batch.id, m.ImportSnapshot.tenant_id == ctx.tenant_id
        )
    )
    if snapshot is None:
        raise HTTPException(409, "Source snapshot missing")
    return {**serialize(batch), "snapshot_id": str(snapshot.id)}


@router.get("/accounting/imports/{identifier}/preview", response_model=dict)
async def preview(identifier: uuid.UUID, db: DB, ctx: Read):
    return await service.preview(db, ctx, identifier)


@router.post("/accounting/imports/{identifier}/validate", response_model=dict)
async def validate(
    identifier: uuid.UUID, db: DB, ctx: Write, request: Request, background: bool = False
):
    await service.scoped(db, ctx, m.ImportBatch, identifier)
    if background:
        from app.workers.accounting import submit

        return await submit(
            db, ctx, "import.validate", {"batch_id": str(identifier)}, request.state.request_id
        )
    return serialize(await service.validate(db, ctx, identifier, request.state.request_id))


@router.post("/accounting/imports/{identifier}/commit", response_model=ImportOut)
async def commit(identifier: uuid.UUID, db: DB, ctx: Write, request: Request):
    return await service.commit(db, ctx, identifier, request.state.request_id)


@router.get("/accounting/imports/{identifier}/validations", response_model=ResourcePage)
async def validations(
    identifier: uuid.UUID,
    db: DB,
    ctx: Read,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    await service.scoped(db, ctx, m.ImportBatch, identifier)
    query = select(m.ValidationResult).where(
        m.ValidationResult.tenant_id == ctx.tenant_id, m.ValidationResult.batch_id == identifier
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(m.ValidationResult.created_at, m.ValidationResult.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {"items": [serialize(r) for r in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/accounting/trial-balance", response_model=dict)
async def balance(
    snapshot_id: uuid.UUID,
    db: DB,
    ctx: Read,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    result = await reconciliation.balance(db, ctx, snapshot_id)
    lines = result.pop("lines")
    return {
        **result,
        "items": lines[offset : offset + limit],
        "total": len(lines),
        "offset": offset,
        "limit": limit,
    }


@router.post("/accounting/trial-balance", response_model=RunOut)
async def balance_snapshot(data: SnapshotRequest, db: DB, ctx: Write):
    return await reconciliation.persist_balance(db, ctx, data.snapshot_id)


@router.post("/accounting/mappings", response_model=dict, status_code=201)
async def mapping(data: MappingCreate, db: DB, ctx: Map, request: Request):
    await service.check_scope(db, ctx, data)
    if data.approved:
        try:
            for key in ["accounts", "groups"]:
                validated = {
                    selector: AccountAssignment.model_validate(value).model_dump(exclude_unset=True)
                    for selector, value in data.mapping.get(key, {}).items()
                }
                data.mapping[key] = validated
        except (ValidationError, AttributeError, TypeError):
            raise HTTPException(422, "Invalid approved mapping definition") from None
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(ctx.tenant_id) + str(data.entity_id) + data.name},
    )
    version = (
        await db.scalar(
            select(func.max(m.MappingProfile.version)).where(
                m.MappingProfile.tenant_id == ctx.tenant_id,
                m.MappingProfile.entity_id == data.entity_id,
                m.MappingProfile.name == data.name,
            )
        )
        or 0
    ) + 1
    profile = m.MappingProfile(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        client_id=data.client_id,
        entity_id=data.entity_id,
        period_id=data.period_id,
        name=data.name,
        version=version,
        mapping=data.mapping,
        approved=data.approved,
    )
    db.add(profile)
    if data.approved:
        assignments = dict(data.mapping.get("accounts", {}))
        for source_group, classification in data.mapping.get("groups", {}).items():
            codes = (
                await db.scalars(
                    select(m.Account.code).where(
                        m.Account.tenant_id == ctx.tenant_id,
                        m.Account.entity_id == data.entity_id,
                        m.Account.source_group == source_group,
                    )
                )
            ).all()
            for code in codes:
                assignments.setdefault(code, classification)
        for code, classification in assignments.items():
            if classification.get("classification") not in {
                "Assets",
                "Liabilities",
                "Equity",
                "Income",
                "Expenses",
            }:
                raise HTTPException(422, "Invalid account classification")
            account = await db.scalar(
                select(m.Account)
                .where(
                    m.Account.tenant_id == ctx.tenant_id,
                    m.Account.entity_id == data.entity_id,
                    m.Account.code == code,
                )
                .with_for_update()
            )
            if account is None:
                raise HTTPException(422, "Account does not exist in this entity")
            for field in [
                "classification",
                "statement_group",
                "contra",
                "parent_code",
                "source_group",
            ]:
                if field in classification:
                    setattr(account, field, classification[field])
            account.mapping_version = version
            account.mapping_profile_id = profile.id
    await db.flush()
    record(db, ctx, "mapping.version_created", profile.id, request.state.request_id)
    return serialize(profile)


@router.get("/accounting/mappings/{identifier}", response_model=dict)
async def get_mapping(identifier: uuid.UUID, db: DB, ctx: Read):
    return serialize(await service.scoped(db, ctx, m.MappingProfile, identifier))


@router.post("/analytics/runs", response_model=dict, status_code=201)
async def analytics(
    data: AnalyticsRequest, db: DB, ctx: Analyze, request: Request, background: bool = False
):
    await service.scoped(db, ctx, m.ImportSnapshot, data.snapshot_id)
    if background:
        from app.workers.accounting import submit

        return await submit(
            db, ctx, "analytics", data.model_dump(mode="json"), request.state.request_id
        )
    return await analytics_service.analytics(db, ctx, data)


@router.get("/analytics/runs/{identifier}", response_model=dict)
async def get_analytics(identifier: uuid.UUID, db: DB, ctx: AnalyzeRead):
    run = await service.scoped(db, ctx, m.AnalyticsRun, identifier)
    results = (
        await db.scalars(
            select(m.RuleResult).where(
                m.RuleResult.tenant_id == ctx.tenant_id, m.RuleResult.run_id == run.id
            )
        )
    ).all()
    from app.modules.lineage.freshness import analytics_current, state

    return {
        **serialize(run),
        "rules": [r.result for r in results],
        "freshness": state(await analytics_current(db, ctx, run)),
    }


@router.get("/analytics/rules", response_model=list[dict])
async def rules(ctx: AnalyzeRead):
    return [
        {
            "rule_id": code,
            "test_name": name,
            "version": VERSION,
            "requires": requires,
            "limitation": "Indicators require professional investigation; missing prerequisites are not testable",
        }
        for code, name, requires in RULES
    ]


@router.post("/reconciliation/runs", response_model=RunOut, status_code=201)
async def reconcile(
    data: ReconcileRequest, db: DB, ctx: Analyze, request: Request, background: bool = False
):
    await service.scoped(db, ctx, m.ImportSnapshot, data.snapshot_id)
    if background:
        from app.workers.accounting import submit

        return await submit(
            db, ctx, "reconciliation", data.model_dump(mode="json"), request.state.request_id
        )
    return await reconciliation.run_reconciliation(
        db, ctx, data.snapshot_id, data.comparison_snapshot_id, data.tolerance
    )


@router.post("/sampling/runs", response_model=RunOut, status_code=201)
async def sampling(
    data: SamplingRequest, db: DB, ctx: Sample, request: Request, background: bool = False
):
    await service.scoped(db, ctx, m.ImportSnapshot, data.snapshot_id)
    if background:
        from app.workers.accounting import submit

        return await submit(
            db, ctx, "sampling", data.model_dump(mode="json"), request.state.request_id
        )
    return await analytics_service.sampling(db, ctx, data)


@router.get("/sampling/runs/{identifier}", response_model=dict)
async def get_sampling(
    identifier: uuid.UUID,
    db: DB,
    ctx: AnalyzeRead,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    run = await service.scoped(db, ctx, m.SamplingRun, identifier)
    items = await page(db, ctx, m.SamplingItem, offset, limit, run_id=run.id)
    return {**serialize(run), "selection": items}


@router.get("/accounting/lineage/{identifier}", response_model=dict)
async def lineage(identifier: uuid.UUID, db: DB, ctx: Read):
    line = await service.scoped(db, ctx, m.JournalLine, identifier)
    source = await service.scoped(db, ctx, m.SourceRecord, line.source_record_id)
    snapshot = await service.scoped(db, ctx, m.ImportSnapshot, line.snapshot_id)
    connector_source = None
    sync_id = snapshot.manifest.get("options", {}).get("source_sync_run_id")
    if sync_id:
        sync = await service.scoped(db, ctx, m.SyncRun, uuid.UUID(sync_id))
        if sync.entity_id != snapshot.entity_id:
            raise HTTPException(409, "Invalid connector lineage scope")
        connector_source = serialize(sync)
    return {
        "journal_line": serialize(line),
        "source_record": serialize(source),
        "snapshot": serialize(snapshot),
        "connector_source": connector_source,
    }


def list_route(model, permission):
    async def endpoint(
        db: DB,
        ctx: Annotated[Context, Depends(require(permission))],
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        client_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        period_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort: str = "created_at",
        run_id: uuid.UUID | None = None,
        snapshot_id: uuid.UUID | None = None,
    ):
        return await page(
            db,
            ctx,
            model,
            offset,
            limit,
            client_id,
            entity_id,
            period_id,
            account_id,
            date_from,
            date_to,
            sort,
            run_id,
            snapshot_id,
        )

    return endpoint


for path, model, permission in [
    ("accounting/imports", m.ImportBatch, "accounting.read"),
    ("accounting/accounts", m.Account, "accounting.read"),
    ("accounting/journals", m.Journal, "accounting.read"),
    ("accounting/ledger", m.JournalLine, "accounting.read"),
    ("accounting/mappings", m.MappingProfile, "accounting.read"),
    ("analytics/runs", m.AnalyticsRun, "analytics.read"),
    ("analytics/findings", m.Finding, "analytics.read"),
    ("analytics/risk-scores", m.RiskScore, "analytics.read"),
    ("reconciliation/runs", m.ReconciliationRun, "analytics.read"),
    ("reconciliation/exceptions", m.ReconciliationException, "analytics.read"),
    ("sampling/runs", m.SamplingRun, "analytics.read"),
]:
    router.add_api_route(
        "/" + path,
        list_route(model, permission),
        methods=["GET"],
        response_model=ResourcePage,
        name="list_" + model.__tablename__,
    )


def financial_route(task):
    async def endpoint(
        data: FinancialRequest, db: DB, ctx: FinancialAI, request: Request, background: bool = False
    ):
        if background:
            await service.scoped(db, ctx, m.ImportSnapshot, data.snapshot_id)
            from app.workers.accounting import submit

            return await submit(
                db,
                ctx,
                "financial_ai",
                {"task": task, "request": data.model_dump(mode="json")},
                request.state.request_id,
            )
        return await suggest(db, ctx, task, data, request.state.request_id)

    return endpoint


for slug, task in [
    ("account-classification", "account_classification"),
    ("anomaly-explanation", "anomaly_explanation"),
    ("audit-procedures", "audit_procedures"),
    ("financial-commentary", "financial_commentary"),
]:
    router.add_api_route(
        "/ai/" + slug, financial_route(task), methods=["POST"], response_model=dict, name=task
    )


class ReviewDecision(Input):
    decision: str = Field(pattern="^(approved|rejected)$")


@router.post("/ai/suggestions/{identifier}/review", response_model=dict)
async def review_suggestion(
    identifier: uuid.UUID,
    data: ReviewDecision,
    db: DB,
    ctx: Annotated[Context, Depends(require("financial_ai.approve"))],
    request: Request,
):
    suggestion = await service.scoped(db, ctx, m.FinancialSuggestion, identifier, True)
    if suggestion.review_status != "pending_review":
        raise HTTPException(409, "Suggestion already reviewed")
    suggestion.review_status = data.decision
    suggestion.reviewed_by = ctx.user_id
    record(db, ctx, "financial_ai." + data.decision, suggestion.id, request.state.request_id)
    await db.flush()
    await db.refresh(suggestion)
    return {
        "id": str(suggestion.id),
        "review_status": suggestion.review_status,
        "ledger_modified": False,
    }


class CurrencyPolicy(Input):
    code: str = Field(pattern=r"^[A-Z]{3}$")
    precision: int = Field(ge=0, le=8)
    rounding: str = Field(pattern="^(ROUND_HALF_EVEN|ROUND_HALF_UP)$")


@router.post("/accounting/currencies", response_model=dict)
async def currency_policy(data: CurrencyPolicy, db: DB, ctx: Map):
    import pycountry

    if pycountry.currencies.get(alpha_3=data.code) is None:
        raise HTTPException(422, "Unknown ISO currency")
    policy = await db.scalar(
        select(m.Currency)
        .where(m.Currency.tenant_id == ctx.tenant_id, m.Currency.code == data.code)
        .with_for_update()
    )
    if policy is None:
        policy = m.Currency(tenant_id=ctx.tenant_id, created_by=ctx.user_id, **data.model_dump())
        db.add(policy)
    else:
        policy.precision = data.precision
        policy.rounding = data.rounding
    await db.flush()
    await db.refresh(policy)
    return serialize(policy)

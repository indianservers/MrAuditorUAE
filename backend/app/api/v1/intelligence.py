"""Connected accounting/document workflows using immutable source and result versions."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy import and_, or_, select

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import RecordInput, RecordPatch, Source
from app.modules.audit_log.service import record
from app.modules.country_workflows.bank_carryforward import CarryforwardInput
from app.modules.country_workflows.bank_outstanding_source import BankOutstandingSourceInput
from app.modules.country_workflows.benefit_settlement_source import BenefitSettlementInput
from app.modules.country_workflows.benefit_source import BenefitSourceInput
from app.modules.country_workflows.contribution_source import ContributionSourceInput
from app.modules.country_workflows.import_vat_source import ImportVATSourceInput
from app.modules.country_workflows.india_company_scope import IndiaCompanyScopeInput
from app.modules.country_workflows.inventory_performance import InventoryPerformanceInput
from app.modules.country_workflows.payroll_proration_source import ProratedBasisInput
from app.modules.country_workflows.payroll_source import PayrollSourceInput, PensionSourceInput
from app.modules.country_workflows.salary_annual_comparison import SalaryAnnualComparisonInput
from app.modules.country_workflows.savings_reported_source import SavingsReportedInput
from app.modules.country_workflows.turnover_composition import TurnoverCompositionInput
from app.modules.country_workflows.turnover_ledger import TurnoverLedgerInput
from app.modules.country_workflows.uae_company_accounts import CompanyAccountsInput
from app.modules.country_workflows.uae_ct_audit_duty import CTAuditDutyInput
from app.modules.country_workflows.uae_tax_group_workpaper import TaxGroupWorkpaperInput
from app.modules.country_workflows.vat_composition import VATCompositionInput
from app.modules.country_workflows.withholding_obligations import WithholdingObligationInput
from app.modules.intelligence import jobs, service
from app.modules.intelligence import schemas as s
from app.modules.intelligence.foundations import PeriodAction
from app.modules.intelligence.models import IntelligenceEvent, IntelligenceJob

router = APIRouter(prefix="/intelligence", tags=["Accounting intelligence"])


@router.get("/engagements/{eid}/events/{identifier}/bank-cash-status")
async def bank_cash_status(eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.country_workflows.bank_consumption import WORKFLOWS, status

    obj = await service.event(db, ctx, eid, identifier, False)
    if obj.kind != "country-workflow" or obj.body.get("workflow") not in WORKFLOWS:
        raise HTTPException(422, "Select an obligation or merchant bank allocation review")
    return await status(db, ctx, obj)


@router.post("/engagements/{eid}/events/{identifier}/withdraw-bank-cash", status_code=201)
async def withdraw_bank_cash(
    eid: uuid.UUID, identifier: uuid.UUID, data: s.Review, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.bank_consumption import (
        WITHDRAWN,
        WORKFLOWS,
        current_decision,
        entity_scope,
        is_active,
    )

    eng = await service.scope(db, ctx, eid, mutable=True)
    await engagement_permissions(db, ctx, eid, "workingpaper.approve")
    obj = await service.event(db, ctx, eid, identifier, False)
    if (
        obj.kind != "country-workflow"
        or obj.body.get("workflow") not in WORKFLOWS
        or data.action != "reject"
    ):
        raise HTTPException(
            422, "Explicit rejection of an obligation or merchant cash review is required"
        )
    if obj.version != data.expected_version or await service.head(db, ctx, obj) != obj.version:
        raise HTTPException(409, "Result version conflict")
    if str(ctx.user_id) in obj.body.get("contributors", [str(obj.created_by)]):
        raise HTTPException(403, "Independent reviewer required")
    if len(data.comments.strip()) < 10:
        raise HTTPException(422, "Document why the approved bank cash claim is being withdrawn")
    await entity_scope(db, ctx, eid, lock=True)
    prior_decision = await current_decision(db, ctx, eid, obj.root_id)
    if prior_decision is None or not is_active(prior_decision.body):
        raise HTTPException(409, "No active approved bank cash claim to withdraw")
    body = dict(obj.body)
    body.update(
        review_status="REJECTED",
        reviewer=str(ctx.user_id),
        reviewed_at=datetime.now(UTC).isoformat(),
        review_comments=data.comments.strip(),
        bank_consumption_review={
            "status": WITHDRAWN,
            "withdrawn_at": datetime.now(UTC).isoformat(),
            "withdrawn_by": str(ctx.user_id),
            "reason": data.comments.strip(),
            "historical_cash_values_not_revalidated": True,
        },
    )
    return audit.serialize(
        await service.append(
            db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
        )
    )


@router.post(
    "/engagements/{eid}/events/{identifier}/withholding-obligation-source", status_code=201
)
async def withholding_obligation_source(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: WithholdingObligationInput,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.country_workflows.withholding_obligations import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    parent = await service.event(db, ctx, eid, identifier, True)
    return audit.serialize(await prepare(db, ctx, eng, parent, data, request.state.request_id))


@router.post("/engagements/{eid}/turnover-ledger-source", status_code=201)
async def turnover_ledger_source(
    eid: uuid.UUID, data: TurnoverLedgerInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.turnover_ledger import prepare

    eng = await service.scope(db, ctx, eid, "workflow-ledger", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/inventory-performance", status_code=201)
async def inventory_performance(
    eid: uuid.UUID, data: InventoryPerformanceInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.inventory_performance import prepare

    eng = await service.scope(db, ctx, eid, "workflow-ledger", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.get("/engagements/{eid}/inventory-performance-options")
async def inventory_performance_options(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.db.models.platform import FinancialPeriod, LegalEntity
    from app.modules.accounting.models import ImportBatch, ImportSnapshot

    eng = await service.scope(db, ctx, eid)
    await engagement_permissions(db, ctx, eid, "accounting.read")
    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    if not entity or not period:
        raise HTTPException(422, "Retained entity and financial period required")
    result: dict = {"currency": entity.functional_currency, "limit": 100, "truncated": {}}
    for side in ("current", "prior"):
        rows = (
            await db.execute(
                select(ImportSnapshot, FinancialPeriod, ImportBatch.kind)
                .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
                .join(FinancialPeriod, FinancialPeriod.id == ImportSnapshot.period_id)
                .where(
                    ImportSnapshot.tenant_id == ctx.tenant_id,
                    ImportSnapshot.entity_id == eng.entity_id,
                    FinancialPeriod.entity_id == eng.entity_id,
                    ImportBatch.status == "active",
                    ImportBatch.kind.in_(["gl", "journals", "tb"]),
                    ImportSnapshot.period_id == eng.period_id
                    if side == "current"
                    else FinancialPeriod.end_date < period.start_date,
                )
                .order_by(FinancialPeriod.end_date.desc(), ImportSnapshot.created_at.desc())
                .limit(101)
            )
        ).all()
        result[side] = [
            {
                "id": str(snapshot.id),
                "label": f"{source_kind} {window.start_date} – {window.end_date} · {snapshot.id}",
                "start": window.start_date.isoformat(),
                "end": window.end_date.isoformat(),
            }
            for snapshot, window, source_kind in rows[:100]
        ]
        result["truncated"][side] = len(rows) > 100
    return result


@router.post("/engagements/{eid}/turnover-books-composition", status_code=201)
async def turnover_books_composition(
    eid: uuid.UUID, data: TurnoverCompositionInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.turnover_composition import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/vat201-composition-source", status_code=201)
async def vat201_composition_source(
    eid: uuid.UUID, data: VATCompositionInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.vat_composition import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/salary-annual-comparison", status_code=201)
async def salary_annual_comparison(
    eid: uuid.UUID, data: SalaryAnnualComparisonInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.salary_annual_comparison import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/uae-ct-audit-duty", status_code=201)
async def uae_ct_audit_duty(
    eid: uuid.UUID, data: CTAuditDutyInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.uae_ct_audit_duty import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/uae-tax-group-statements", status_code=201)
async def uae_tax_group_statements(
    eid: uuid.UUID, data: TaxGroupWorkpaperInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.uae_tax_group_workpaper import COLLECTIONS, prepare, preview

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    obj = await prepare(db, ctx, eng, data, request.state.request_id)
    return {
        **audit.serialize(obj),
        "body": {**preview(obj.body), "rows": obj.body["rows"][:100]},
        "collection_totals": {key: len(obj.body.get(key, [])) for key in COLLECTIONS.values()},
    }


@router.get("/engagements/{eid}/events/{identifier}/tax-group-collections")
async def tax_group_collections(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    collection_name: Literal[
        "statements",
        "sources",
        "members",
        "adjustments",
        "checks",
        "notes",
        "issues",
        "losses",
        "documents",
    ] = Query(...),
    period: Literal["all", "current", "comparative"] = "all",
    statement: Literal["all", "position", "profit_loss", "oci", "changes_equity"] = "all",
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    from app.modules.country_workflows.uae_tax_group_workpaper import collection

    obj = await service.event(db, ctx, eid, identifier)
    if obj.body.get("workflow") != "uae-tax-group-statements":
        raise HTTPException(422, "Select a retained Tax Group statement workpaper")
    values = collection(obj.body, collection_name, period, statement)
    return {
        "items": values[offset : offset + limit],
        "total": len(values),
        "offset": offset,
        "limit": limit,
    }


@router.get("/engagements/{eid}/tax-group-mapping-schema")
async def tax_group_mapping_schema(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.country_workflows.uae_tax_group_workpaper import mapping_schema

    await service.scope(db, ctx, eid)
    return mapping_schema()


@router.get("/engagements/{eid}/evidence-choices")
async def evidence_choices(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    sha256: str | None = Query(None, pattern=r"^[a-f0-9]{64}$"),
    search: str = Query("", max_length=100),
):
    from sqlalchemy import func

    from app.modules.audit_execution.models import EvidenceVersion

    await service.scope(db, ctx, eid)
    latest = (
        select(EvidenceVersion.record_id, func.max(EvidenceVersion.number).label("number"))
        .join(AuditRecord, AuditRecord.id == EvidenceVersion.record_id)
        .where(
            EvidenceVersion.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.kind == "evidence",
            AuditRecord.status != "ARCHIVED",
        )
        .group_by(EvidenceVersion.record_id)
        .subquery()
    )
    query = (
        select(EvidenceVersion)
        .join(
            latest,
            and_(
                EvidenceVersion.record_id == latest.c.record_id,
                EvidenceVersion.number == latest.c.number,
            ),
        )
        .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.scan_status == "CLEAN")
    )
    if sha256:
        query = query.where(EvidenceVersion.sha256 == sha256)
    if search:
        query = query.where(EvidenceVersion.filename.icontains(search, autoescape=True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    versions = (
        await db.scalars(
            query.order_by(EvidenceVersion.created_at.desc(), EvidenceVersion.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(v.id),
                "record_id": str(v.record_id),
                "label": v.filename,
                "sha256": v.sha256,
                "version": v.number,
                "scan_status": v.scan_status,
            }
            for v in versions
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/engagements/{eid}/uae-company-accounts-duty", status_code=201)
async def uae_company_accounts_duty(
    eid: uuid.UUID, data: CompanyAccountsInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.uae_company_accounts import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/india-company-reporting-scope", status_code=201)
async def india_company_reporting_scope(
    eid: uuid.UUID, data: IndiaCompanyScopeInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.india_company_scope import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/contribution-obligation-source", status_code=201)
async def contribution_obligation_source(
    eid: uuid.UUID, data: ContributionSourceInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.contribution_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/savings-reported-obligation-source", status_code=201)
async def savings_reported_obligation_source(
    eid: uuid.UUID, data: SavingsReportedInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.savings_reported_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/prorated-payroll-basis-source", status_code=201)
async def prorated_payroll_basis_source(
    eid: uuid.UUID, data: ProratedBasisInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.payroll_proration_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/benefit-settlement-source", status_code=201)
async def benefit_settlement_source(
    eid: uuid.UUID, data: BenefitSettlementInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.benefit_settlement_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/payroll-rule-source", status_code=201)
async def payroll_rule_source(
    eid: uuid.UUID, data: PayrollSourceInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.payroll_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/pension-rule-source", status_code=201)
async def pension_rule_source(
    eid: uuid.UUID, data: PensionSourceInput, db: DB, ctx: Actor, request: Request
):
    from app.modules.country_workflows.payroll_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(
        await prepare(db, ctx, eng, data, request.state.request_id, profile_kind="pension")
    )


@router.post("/engagements/{eid}/benefit-rule-source", status_code=201)
async def benefit_rule_source(
    eid: uuid.UUID,
    data: BenefitSourceInput,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.country_workflows.benefit_source import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    return audit.serialize(await prepare(db, ctx, eng, data, request.state.request_id))


@router.post("/engagements/{eid}/events/{identifier}/bank-carryforward-source", status_code=201)
async def bank_carryforward_source(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: CarryforwardInput,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.country_workflows.bank_carryforward import prepare

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    parent = await service.event(db, ctx, eid, identifier, True)
    return audit.serialize(await prepare(db, ctx, eng, parent, data, request.state.request_id))


@router.post("/engagements/{eid}/events/{identifier}/bank-outstanding-source", status_code=201)
async def bank_outstanding_source(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: BankOutstandingSourceInput,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.country_workflows.bank_outstanding_source import source_rows

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    parent = await service.event(db, ctx, eid, identifier, True)
    if parent.kind != "country-workflow" or parent.body.get("workflow") != "bank-brs":
        raise HTTPException(422, "Select a bank reconciliation")
    if parent.body.get("review_status") != "REVIEWED" or parent.body.get("blocked"):
        raise HTTPException(
            409, "Independently review and resolve the BRS before preparing outstanding items"
        )
    source_ids = parent.body.get("parameters", {}).get("source_ids", {})
    if set(source_ids) != {"books", "statement"}:
        raise HTTPException(409, "BRS source roles are incomplete")
    sources = {}
    for role, source_id in source_ids.items():
        original = await service.event(db, ctx, eid, uuid.UUID(source_id), True)
        if (
            original.kind != "workflow-source"
            or original.body.get("table_type") != "transactions"
            or original.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(409, "Independently review every retained BRS source")
        sources[role] = original
    try:
        rows, totals = source_rows(parent.body, sources["books"].body, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    created = await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "bank-outstanding",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": "brs-outstanding-bridge/1",
            "source_identity": "brs-outstanding:" + str(parent.root_id),
            "source_sha256": parent.sha256,
            "contributors": sorted(
                {*parent.body.get("contributors", [str(parent.created_by)]), str(ctx.user_id)}
            ),
            "population_completeness": "SELECTED_REVIEWED_BRS_BOOK_EXCEPTIONS_ONLY",
            "native_metadata": {
                "source_brs_id": str(parent.id),
                "source_books_id": str(sources["books"].id),
                "selected_exception_ids": data.exception_ids,
                "scope_assessment": data.assessment,
                "expected_rows": data.expected_rows,
                "signed_total": str(data.signed_total),
                "clearance_status": "NOT_DETERMINED_BY_BRS_EXCEPTION",
            },
            "limitations": [
                "Selected book exceptions only; statement-side unbooked entries are excluded",
                "BRS candidate causes and documented dispositions do not establish later clearance",
                "Independently review this derived population before subsequent clearance assessment",
            ],
        },
        [service.event_receipt(parent)],
        request.state.request_id,
    )
    return audit.serialize(created)


@router.post("/engagements/{eid}/events/{identifier}/import-vat-box-source", status_code=201)
async def import_vat_box_source(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: ImportVATSourceInput,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.country_workflows.import_vat_source import source_rows
    from app.modules.jurisdictions.workspace import resolved

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    package, _ = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "Import VAT box sources require a UAE engagement")
    parent = await service.event(db, ctx, eid, identifier, True)
    if parent.kind != "country-workflow" or parent.body.get("workflow") != "uae-import-vat":
        raise HTTPException(422, "Select an import VAT detail comparison")
    if parent.body.get("review_status") != "REVIEWED" or parent.body.get("blocked"):
        raise HTTPException(
            409, "Independently review and resolve the import comparison before bridging"
        )
    source_ids = parent.body.get("parameters", {}).get("source_ids", {})
    if set(source_ids) != {"customs", "portal", "books"}:
        raise HTTPException(409, "Import comparison source roles are incomplete")
    for source_id in source_ids.values():
        original = await service.event(db, ctx, eid, uuid.UUID(source_id), True)
        if (
            original.kind != "workflow-source"
            or original.body.get("table_type") != "import-vat-lines"
            or original.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(409, "Independently review every retained import-detail source")
    try:
        rows, totals = source_rows(parent.body, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    created = await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        {
            "table_type": "return-boxes",
            "rows": rows,
            "row_count": len(rows),
            "control_totals": totals,
            "title": data.label,
            "review_status": "UNVERIFIED",
            "parser_version": "import-vat-box-bridge/1",
            "source_identity": "import-vat:" + str(parent.root_id),
            "source_sha256": parent.sha256,
            "contributors": sorted(
                {*parent.body.get("contributors", [str(parent.created_by)]), str(ctx.user_id)}
            ),
            "population_completeness": "SELECTED_REVIEWED_IMPORT_BOX_POPULATIONS_ONLY",
            "statutory_calculation_qualified": False,
            "native_metadata": {
                "source_import_comparison_id": str(parent.id),
                "source_role": data.source_role,
                "selected_box_controls": data.model_dump(mode="json")["boxes"],
                "scope_assessment": data.assessment,
                "upstream_exception_count": parent.body.get("exception_count"),
                "return_role": "BOOKS_ONLY_NOT_FILED_RETURN",
                "tax_field_basis": "FINAL_ASSESSED_SELECTED_IMPORT_TAX_WITH_ZERO_SEPARATE_TAX_ADJUSTMENT",
            },
            "limitations": [
                "Selected import detail only; independently retained filed VAT201 evidence is still required",
                "This bridge does not prepare a whole VAT201, infer absent boxes, approve recovery or execute filing",
                "Documented upstream exceptions remain part of the parent comparison and are not resolved by aggregation",
            ],
        },
        [service.event_receipt(parent)],
        request.state.request_id,
    )
    return audit.serialize(created)


@router.post("/engagements/{eid}/events/{identifier}/remaining-open-items", status_code=201)
async def remaining_open_items(
    eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor, request: Request
):
    from collections import defaultdict
    from decimal import Decimal

    eng = await service.scope(db, ctx, eid, "country-workflow", True)
    source = await service.event(db, ctx, eid, identifier, True)
    if source.kind != "country-workflow" or source.body.get("workflow") not in {
        "open-item-allocations",
        "credit-note-applications",
    }:
        raise HTTPException(422, "Select a cash allocation or credit application assessment")
    if source.body.get("review_status") != "REVIEWED" or source.body.get("blocked"):
        raise HTTPException(409, "Independently reviewed reconciled allocations required")
    # The existing ECL/count/source consumers use this same canonical source type.
    rows = source.body["remaining_open_items"]
    credit_application = source.body.get("workflow") == "credit-note-applications"
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        totals[row["currency"]] += Decimal(row["amount"])
    body = {
        "table_type": "audit-open-items",
        "rows": rows,
        "row_count": len(rows),
        "control_totals": {c: str(v) for c, v in totals.items()},
        "population_completeness": "DERIVED_FROM_REVIEWED_EXPLICIT_CREDIT_APPLICATIONS"
        if credit_application
        else "DERIVED_FROM_REVIEWED_EXPLICIT_ALLOCATIONS",
        "review_status": "UNVERIFIED",
        "title": "Remaining open items after reviewed credit applications"
        if credit_application
        else "Remaining open items after reviewed cash allocations",
        "parser_version": "credit-application-open-items/1"
        if credit_application
        else "allocation-open-items/1",
        "contributors": sorted({*source.body.get("contributors", []), str(ctx.user_id)}),
        "source_identity": "allocation:" + str(source.root_id),
        "source_sha256": source.sha256,
    }
    created = await service.append(
        db,
        ctx,
        eng,
        "workflow-source",
        body,
        [service.event_receipt(source)],
        request.state.request_id,
    )
    return audit.serialize(created)


@router.get("/engagements/{eid}/foundation-status")
async def foundation_status(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.intelligence.foundations import diagnostics

    eng = await audit.engagement(db, ctx, eid, "accounting.read", lock=False)
    return await diagnostics(db, ctx, eng)


@router.post("/engagements/{eid}/period-actions")
async def period_action(eid: uuid.UUID, data: PeriodAction, db: DB, ctx: Actor, request: Request):
    from app.db.models.platform import FinancialPeriod

    action = data
    eng = await audit.engagement(db, ctx, eid, "workingpaper.approve", True)
    period = await db.scalar(
        select(FinancialPeriod)
        .where(FinancialPeriod.tenant_id == ctx.tenant_id, FinancialPeriod.id == eng.period_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not period or period.lock_version != action.expected_version:
        raise HTTPException(409, "Period lock version conflict")
    target = "LOCKED" if action.action == "lock" else "OPEN"
    if period.lock_state == target:
        raise HTTPException(409, "Period is already in the requested state")
    previous = period.lock_state
    period.lock_state = target
    period.lock_version += 1
    record(
        db,
        ctx,
        "accounting.period." + action.action,
        period.id,
        request.state.request_id,
        {
            "entity_id": str(eng.entity_id),
            "engagement_id": str(eid),
            "before": previous,
            "after": target,
            "version": period.lock_version,
            "reason": action.reason,
        },
    )
    return {"id": str(period.id), "state": target, "version": period.lock_version}


@router.get("/capabilities")
async def capabilities(ctx: Actor):
    from app.core.config import settings
    from app.modules.country_workflows.catalogue import catalogue, scenarios

    return {
        "country_workflows": catalogue(),
        "real_world_scenario_count": len(scenarios()),
        "engine_version": "accounting-intelligence-1",
        "operations": list(s.OPERATIONS),
        "lead_sections": s.SECTIONS,
        "ocr": {
            "providers": ["pdfium-text", "rapidocr-local"],
            "external_document_transfer": False,
            "max_pages": settings().document_max_pages,
            "max_bytes": settings().document_max_bytes,
            "requires_clean_evidence": True,
            "scores_calibrated": False,
        },
        "limits": {
            "vouching_items": 2000,
            "documents_per_run": 200,
            "matching_rows_per_side": 20000,
            "graph_journals": 10000,
        },
        "statutory_qualification": False,
    }


@router.get("/engagements/{eid}/country-workflows")
async def country_workflows(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.db.models.platform import LegalEntity
    from app.modules.country_workflows.catalogue import catalogue, check_templates, scenarios
    from app.modules.country_workflows.schemas import ROW_TYPES
    from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS
    from app.modules.jurisdictions.workspace import resolved

    eng = await service.scope(db, ctx, eid)
    await engagement_permissions(db, ctx, eid, "accounting.read")
    package, _ = await resolved(db, ctx, eng)
    from app.modules.country_workflows.native_sources import formats

    entity = await db.get(LegalEntity, eng.entity_id)
    if entity is None or entity.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "Entity not found")
    return {
        "default_currency": entity.functional_currency,
        "default_currency_basis": "ENTITY_FUNCTIONAL_CURRENCY",
        "source_formats": formats(package.country),
        "vat201_layouts": LAYOUTS if package.country == "AE" else {},
        "vat201_emirates": EMIRATES if package.country == "AE" else {},
        "check_templates": check_templates(package.country),
        "scenarios": scenarios(),
        "country": package.country,
        "items": catalogue(package.country),
        "source_contracts": {
            name: {
                field: {"required": info.is_required(), "type": str(info.annotation)}
                for field, info in model.model_fields.items()
            }
            for name, model in ROW_TYPES.items()
            if name != "gst-summary-metrics" or package.country == "IN"
            if not name.startswith("msme-") or package.country == "IN"
        },
        "max_rows_per_source": 5000,
        "statutory_calculation_qualified": False,
    }


@router.post("/engagements/{eid}/jobs", status_code=202)
async def submit(
    eid: uuid.UUID,
    data: s.JobInput,
    db: DB,
    ctx: Actor,
    request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
):
    return audit.serialize(
        await jobs.submit(db, ctx, eid, data, idempotency_key, request.state.request_id)
    )


@router.get("/engagements/{eid}/vat-sources")
async def vat_sources(eid: uuid.UUID, db: DB, ctx: Actor):
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.vat.models import VATRun
    from app.modules.vat.service import current

    eng = await service.scope(db, ctx, eid)
    await engagement_permissions(db, ctx, eid, "accounting.read")
    await engagement_permissions(db, ctx, eid, "vat.read")
    package, _ = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "UAE VAT sources are unavailable for this engagement country")
    rows = (
        await db.scalars(
            select(VATRun)
            .where(
                VATRun.tenant_id == ctx.tenant_id,
                VATRun.engagement_id == eid,
                VATRun.kind == "vat201",
            )
            .order_by(VATRun.created_at.desc(), VATRun.id)
            .limit(51)
        )
    ).all()
    items = []
    for row in rows[:50]:
        if (
            row.results.get("validation", {}).get("ready") is True
            and not row.results.get("exceptions")
            and await current(db, ctx, eid, row)
        ):
            items.append(
                {
                    "id": str(row.id),
                    "label": f"VAT201 {row.period_start} – {row.period_end}",
                    "sha256": row.sha256,
                    "mapping_version": row.results.get("mapping_version"),
                }
            )
    return {"items": items, "limit": 50, "truncated": len(rows) > 50}


@router.get("/engagements/{eid}/jobs")
async def job_list(eid: uuid.UUID, db: DB, ctx: Actor, limit: int = Query(50, ge=1, le=100)):
    await service.scope(db, ctx, eid)
    rows = (
        await db.scalars(
            select(IntelligenceJob)
            .where(IntelligenceJob.tenant_id == ctx.tenant_id, IntelligenceJob.engagement_id == eid)
            .order_by(IntelligenceJob.created_at.desc(), IntelligenceJob.id)
            .limit(limit)
        )
    ).all()
    visible = []
    for row in rows:
        try:
            await service.restricted_permission(db, ctx, eid, row.payload)
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        visible.append(audit.serialize(row))
    return {"items": visible, "limit": limit}


@router.get("/engagements/{eid}/jobs/{jid}")
async def job_details(eid: uuid.UUID, jid: uuid.UUID, db: DB, ctx: Actor):
    await service.scope(db, ctx, eid)
    obj = await db.scalar(
        select(IntelligenceJob).where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.engagement_id == eid,
            IntelligenceJob.id == jid,
        )
    )
    if not obj:
        raise HTTPException(404, "Job not found")
    await service.restricted_permission(db, ctx, eid, obj.payload)
    return audit.serialize(obj)


class JobAction(s.Strict):
    version: int = Field(ge=1)
    action: Literal["cancel", "retry"]


@router.post("/engagements/{eid}/jobs/{jid}/actions")
async def job_action(
    eid: uuid.UUID, jid: uuid.UUID, data: JobAction, db: DB, ctx: Actor, request: Request
):
    await service.scope(db, ctx, eid)
    obj = await db.scalar(
        select(IntelligenceJob)
        .where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.engagement_id == eid,
            IntelligenceJob.id == jid,
        )
        .with_for_update()
    )
    if not obj:
        raise HTTPException(404, "Job not found")
    if obj.created_by != ctx.user_id:
        raise HTTPException(403, "Only the submitting user may control this job")
    await service.restricted_permission(db, ctx, eid, obj.payload)
    await service.scope(db, ctx, eid, obj.operation)
    if obj.version != data.version:
        raise HTTPException(409, "Job version conflict")
    if data.action == "cancel":
        if obj.status not in {"pending", "running"}:
            raise HTTPException(409, "Only active jobs can be canceled")
        obj.status = "canceled"
    elif data.action == "retry":
        if obj.status not in {"failed", "canceled"} or obj.attempts >= 3:
            raise HTTPException(
                409,
                "Retry requires a failed/canceled job with fewer than three attempts; otherwise submit a corrected new job",
            )
        obj.status = "pending"
        obj.progress = 0
        obj.error_category = None
        obj.error_details = None
    else:
        raise HTTPException(422, "Unknown job action")
    await db.flush()
    await db.refresh(obj)
    record(
        db,
        ctx,
        "intelligence.job." + data.action,
        obj.id,
        request.state.request_id,
        {"engagement_id": str(eid)},
    )
    await db.commit()
    if data.action == "retry":
        from app.workers.intelligence import run

        try:
            run.apply_async(args=[str(obj.id), str(ctx.tenant_id)], queue="intelligence")
        except Exception:
            raise HTTPException(503, "Broker unavailable; retry remains pending") from None
    return audit.serialize(obj)


@router.get("/engagements/{eid}/events")
async def events(
    eid: uuid.UUID,
    db: DB,
    ctx: Actor,
    kind: str | None = None,
    after: uuid.UUID | None = None,
    before: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    newest: bool = False,
):
    await service.scope(db, ctx, eid)
    query = select(IntelligenceEvent).where(
        IntelligenceEvent.tenant_id == ctx.tenant_id, IntelligenceEvent.engagement_id == eid
    )
    if kind:
        query = query.where(IntelligenceEvent.kind == kind)
    if before:
        if not newest or after:
            raise HTTPException(
                422, "An older-result cursor requires newest ordering without after"
            )
        anchor = await db.scalar(query.where(IntelligenceEvent.id == before))
        if anchor is None:
            raise HTTPException(404, "Result cursor not found in this engagement and filter")
        query = query.where(
            or_(
                IntelligenceEvent.created_at < anchor.created_at,
                and_(
                    IntelligenceEvent.created_at == anchor.created_at,
                    IntelligenceEvent.id < anchor.id,
                ),
            )
        )
    if after:
        if newest:
            raise HTTPException(422, "Newest result selection does not support an ID cursor")
        query = query.where(IntelligenceEvent.id > after)
    ordering = (
        [IntelligenceEvent.created_at.desc(), IntelligenceEvent.id.desc()]
        if newest
        else [IntelligenceEvent.id]
    )
    rows = (await db.scalars(query.order_by(*ordering).limit(limit + 1))).all()
    from app.core.read_projection import read_projection

    with read_projection(db, ctx):
        items = []
        for row in rows[:limit]:
            try:
                await service.event(db, ctx, eid, row.id)
            except HTTPException as exc:
                if exc.status_code == 403:
                    continue
                raise
            items.append(
                {
                    "id": str(row.id),
                    "root_id": str(row.root_id),
                    "kind": row.kind,
                    "area": row.body.get("area"),
                    "table_type": row.body.get("table_type"),
                    "workflow": row.body.get("workflow"),
                    "blocked": bool(row.body.get("blocked")),
                    "as_of": row.body.get("as_of"),
                    "bank_account_scope": {
                        key: row.body["bank_account_scope"].get(key)
                        for key in ("account", "currency")
                    }
                    if row.body.get("workflow") == "bank-account-evidence"
                    else None,
                    "native_format": row.body.get("native_format"),
                    "parser_version": row.body.get("parser_version"),
                    "allowed_source_roles": row.body.get("allowed_source_roles"),
                    "allowed_workflows": row.body.get("allowed_workflows"),
                    "invoice_direction": row.body.get("native_metadata", {}).get("direction")
                    if row.body.get("native_format") == "india-inv01-json"
                    else None,
                    "inventory_controls_verified": row.body.get("inventory_controls_verified")
                    is True,
                    "purchase_controls_verified": row.body.get("purchase_controls_verified")
                    is True,
                    "obligation_populations": sorted(
                        {item.get("population", "unspecified") for item in row.body.get("rows", [])}
                    )
                    if row.body.get("table_type") == "obligations"
                    else None,
                    "evidence_version_id": row.body.get("evidence_version_id"),
                    "table_kind": row.body.get("table_kind"),
                    "version": row.version,
                    "sha256": row.sha256,
                    "created_at": row.created_at.isoformat(),
                    "created_by": str(row.created_by),
                    "review_status": row.body.get("review_status", "UNVERIFIED"),
                    "label": (row.body.get("title") if row.kind == "workflow-source" else None)
                    or row.body.get("source_filename")
                    or row.body.get("section")
                    or row.body.get("title")
                    or row.kind,
                    "freshness": "CURRENT" if await service.current(db, ctx, row) else "STALE",
                }
            )
    return {
        "items": items,
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit and not newest else None,
        "next_before": str(rows[limit - 1].id) if len(rows) > limit and newest else None,
        "truncated": len(rows) > limit,
        "limit": limit,
    }


@router.get("/engagements/{eid}/events/{identifier}")
async def event_details(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    turnover_offset: int = Query(0, ge=0),
    turnover_limit: int = Query(100, ge=1, le=500),
    excluded_offset: int = Query(0, ge=0),
    excluded_limit: int = Query(100, ge=1, le=500),
    fifo_offset: int = Query(0, ge=0),
    fifo_limit: int = Query(20, ge=1, le=100),
    inventory_performance_offset: int = Query(0, ge=0),
    inventory_performance_limit: int = Query(20, ge=1, le=100),
    inventory_offset: int = Query(0, ge=0),
    inventory_limit: int = Query(100, ge=1, le=500),
    bridge_offset: int = Query(0, ge=0),
    bridge_limit: int = Query(100, ge=1, le=500),
    posting_offset: int = Query(0, ge=0),
    posting_limit: int = Query(100, ge=1, le=500),
    date_offset: int = Query(0, ge=0),
    date_limit: int = Query(100, ge=1, le=500),
    payroll_view: Literal["all", "accounts", "postings"] = "all",
    employment_view: Literal["all", "assessment", "history"] = "all",
    inventory_view: Literal["all", "valuations", "gl-controls"] = "all",
    confirmation_view: Literal["all", "parties", "gl-controls"] = "all",
    confirmation_link_offset: int = Query(0, ge=0),
    confirmation_link_limit: int = Query(100, ge=1, le=500),
    custody_control_offset: int = Query(0, ge=0),
    custody_control_limit: int = Query(100, ge=1, le=500),
    ownership_path_offset: int = Query(0, ge=0),
    ownership_path_limit: int = Query(100, ge=1, le=500),
    ownership_step_offset: int = Query(0, ge=0),
    ownership_step_limit: int = Query(100, ge=1, le=500),
    cutoff_control_offset: int = Query(0, ge=0),
    cutoff_control_limit: int = Query(100, ge=1, le=500),
    cutoff_posting_offset: int = Query(0, ge=0),
    cutoff_posting_limit: int = Query(100, ge=1, le=500),
    purchase_offset: int = Query(0, ge=0),
    purchase_limit: int = Query(100, ge=1, le=500),
    ambiguity_offset: int = Query(0, ge=0),
    ambiguity_limit: int = Query(100, ge=1, le=500),
    tax_invoice_offset: int = Query(0, ge=0),
    tax_invoice_limit: int = Query(100, ge=1, le=500),
    salary_link_offset: int = Query(0, ge=0),
    salary_link_limit: int = Query(100, ge=1, le=500),
):
    obj = await service.event(db, ctx, eid, identifier)
    body = dict(obj.body)
    if obj.kind == "reconciliation":
        from app.modules.intelligence.matching_review import review_summary

        body["review_decision_summary"] = review_summary(obj.body)
    if body.get("workflow") == "payroll-ledger-rollforward" and payroll_view != "all":
        selected_kind = (
            "account-rollforward" if payroll_view == "accounts" else "posting-comparison"
        )
        body["rows"] = [row for row in body["rows"] if row["kind"] == selected_kind]
    if body.get("workflow") == "employment-payroll-review" and employment_view != "all":
        selected_kinds = (
            {"revision-history"}
            if employment_view == "history"
            else {"entry-comparison", "population-coverage"}
        )
        body["rows"] = [row for row in body["rows"] if row["kind"] in selected_kinds]
    if body.get("workflow") == "inventory-valuation-control" and inventory_view != "all":
        selected_kind = "valuation-test" if inventory_view == "valuations" else "gl-control"
        body["rows"] = [row for row in body["rows"] if row["kind"] == selected_kind]
    if body.get("workflow") == "party-balance-confirmations" and confirmation_view != "all":
        selected_kind = "party-confirmation" if confirmation_view == "parties" else "control"
        body["rows"] = [row for row in body["rows"] if row["kind"] == selected_kind]
    totals = {}
    if body.get("workflow") == "uae-tax-group-statements":
        from app.modules.country_workflows.uae_tax_group_workpaper import COLLECTIONS, preview

        totals.update(
            {key: len(body.get(key, [])) for key in COLLECTIONS.values() if key != "rows"}
        )
        body = preview(body)
    for key in [
        "rows",
        "items",
        "suggestions",
        "source_rows",
        "destination_rows",
        "unmatched_left",
        "unmatched_right",
        "matches",
        "edges",
    ]:
        if isinstance(body.get(key), list):
            totals[key] = len(body[key])
            body[key] = body[key][offset : offset + limit]
    if isinstance(body.get("excluded_box_rows"), list):
        totals["excluded_box_rows"] = len(body["excluded_box_rows"])
        body["excluded_box_rows"] = body["excluded_box_rows"][
            excluded_offset : excluded_offset + excluded_limit
        ]
    for key, start, size in [
        ("salary_quarterly_links", salary_link_offset, salary_link_limit),
        ("unassigned_quarterly_parties", salary_link_offset, salary_link_limit),
        ("turnover_adjustment_rows", turnover_offset, turnover_limit),
        ("custody_quantity_controls", custody_control_offset, custody_control_limit),
        ("ownership_paths", ownership_path_offset, ownership_path_limit),
        ("ownership_path_steps", ownership_step_offset, ownership_step_limit),
        ("cutoff_document_controls", cutoff_control_offset, cutoff_control_limit),
        ("cutoff_posting_links", cutoff_posting_offset, cutoff_posting_limit),
        ("confirmation_coverage_links", confirmation_link_offset, confirmation_link_limit),
        ("purchase_quantity_controls", purchase_offset, purchase_limit),
        ("fifo_allocations", fifo_offset, fifo_limit),
        ("inventory_performance_links", inventory_performance_offset, inventory_performance_limit),
        ("fifo_event_costs", fifo_offset, fifo_limit),
        ("fifo_closing_layers", fifo_offset, fifo_limit),
        ("inventory_fifo_controls", fifo_offset, fifo_limit),
        ("inventory_quantity_controls", inventory_offset, inventory_limit),
        ("count_bridges", bridge_offset, bridge_limit),
        ("payroll_posting_links", posting_offset, posting_limit),
        ("transaction_dates", date_offset, date_limit),
        ("invoice_tax_details", tax_invoice_offset, tax_invoice_limit),
    ]:
        if isinstance(body.get(key), list):
            totals[key] = len(body[key])
            body[key] = body[key][start : start + size]
    if isinstance(body.get("ambiguous"), list):
        totals["ambiguous"] = len(body["ambiguous"])
        body["ambiguous"] = [
            {
                **row,
                "candidate_ids": row.get("candidate_ids", [])[:50],
                "candidate_preview_truncated": row.get("candidate_preview_truncated", False)
                or len(row.get("candidate_ids", [])) > 50,
            }
            for row in body["ambiguous"][ambiguity_offset : ambiguity_offset + ambiguity_limit]
        ]
    return {
        **audit.serialize(obj),
        "body": body,
        "collection_totals": totals,
        "offset": offset,
        "limit": limit,
        "freshness": "CURRENT" if await service.current(db, ctx, obj) else "STALE",
        "latest_version": await service.head(db, ctx, obj),
        "provenance_status": "receipts_retained"
        if any(d.get("type") != "context" for d in obj.dependencies)
        else "legacy provenance incomplete",
    }


@router.get("/engagements/{eid}/events/{identifier}/bank-candidates")
async def bank_candidates(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    left_id: str = Query(..., min_length=1, max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    from app.modules.intelligence.matching_review import candidate_page

    obj = await service.event(db, ctx, eid, identifier)
    return await candidate_page(db, ctx, eid, obj, left_id, offset, limit)


@router.get("/engagements/{eid}/events/{identifier}/bank-matched-proposal")
async def bank_matched_proposal(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    index: int = Query(..., ge=0),
):
    from app.modules.intelligence.bank_matches import detail

    obj = await service.event(db, ctx, eid, identifier)
    return await detail(db, ctx, eid, obj, index)


@router.post("/engagements/{eid}/events/{identifier}/corrections", status_code=201)
async def correct(
    eid: uuid.UUID, identifier: uuid.UUID, data: s.Correction, db: DB, ctx: Actor, request: Request
):
    eng = await service.scope(db, ctx, eid, "ocr", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.kind != "ocr":
        raise HTTPException(422, "Only OCR fields use this correction workflow")
    if obj.version != data.expected_version:
        raise HTTPException(409, "Extraction version conflict")
    from app.modules.intelligence.documents import FIELDS, MONEY, money

    if not set(data.fields) <= {*FIELDS, "gstin", "trn", "cgst", "sgst", "igst"}:
        raise HTTPException(422, "Unknown extracted field")
    fields = dict(obj.body["fields"])
    locations = dict(obj.body.get("field_locations", {}))
    for key, value in data.fields.items():
        if value is not None:
            if len(value) > 1000:
                raise HTTPException(422, "Corrected field exceeds limit")
            if key in MONEY:
                try:
                    value = money(value)
                except ValueError:
                    raise HTTPException(422, "Invalid corrected amount") from None
            if key.endswith("date"):
                try:
                    value = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    raise HTTPException(422, "Corrected date must use YYYY-MM-DD") from None
            if key == "currency":
                import pycountry

                value = value.upper()
                if pycountry.currencies.get(alpha_3=value) is None:
                    raise HTTPException(422, "ISO currency required")
        fields[key] = value
        locations[key] = {
            "origin": "HUMAN_CORRECTION",
            "actor": str(ctx.user_id),
            "prior_event_id": str(obj.id),
            "reason": data.reason,
        }
    messages = [
        message
        for message in obj.body.get("validation_messages", [])
        if message != "Net plus tax does not equal gross"
        and not any(
            message.startswith(key + ":") and value is not None
            for key, value in data.fields.items()
        )
    ]
    if all(fields.get(key) is not None for key in ["gross_amount", "net_amount", "tax_amount"]):
        from decimal import Decimal

        if Decimal(fields["net_amount"]) + Decimal(fields["tax_amount"]) != Decimal(
            fields["gross_amount"]
        ):
            messages.append("Net plus tax does not equal gross")
    body = {
        **obj.body,
        "fields": fields,
        "validation_messages": messages,
        "field_locations": locations,
        "correction_reason": data.reason,
        "review_status": "UNVERIFIED",
        "contributors": sorted({*obj.body.get("contributors", []), str(ctx.user_id)}),
    }
    result = await service.append(
        db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
    )
    return audit.serialize(result)


@router.get("/engagements/{eid}/inputs")
async def inputs(eid: uuid.UUID, db: DB, ctx: Actor):
    """Bounded authorized source choices; large accounting lists remain in the existing workbenches."""
    from app.modules.accounting.models import ImportBatch, ImportSnapshot, SamplingRun
    from app.modules.audit_execution.models import AuditRecord, EvidenceVersion

    eng = await service.scope(db, ctx, eid)
    await engagement_permissions(db, ctx, eid, "accounting.read")
    snapshots = (
        await db.scalars(
            select(ImportSnapshot)
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .where(
                ImportSnapshot.tenant_id == ctx.tenant_id,
                ImportSnapshot.entity_id == eng.entity_id,
                ImportSnapshot.period_id == eng.period_id,
                ImportBatch.status == "active",
            )
            .order_by(ImportSnapshot.created_at.desc())
            .limit(100)
        )
    ).all()
    samples = (
        await db.scalars(
            select(SamplingRun)
            .where(
                SamplingRun.tenant_id == ctx.tenant_id,
                SamplingRun.entity_id == eng.entity_id,
                SamplingRun.period_id == eng.period_id,
                SamplingRun.status == "completed",
            )
            .order_by(SamplingRun.created_at.desc())
            .limit(100)
        )
    ).all()
    evidence = (
        await db.scalars(
            select(EvidenceVersion)
            .join(AuditRecord, AuditRecord.id == EvidenceVersion.record_id)
            .where(
                EvidenceVersion.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.status != "ARCHIVED",
            )
            .order_by(EvidenceVersion.created_at.desc())
            .limit(100)
        )
    ).all()
    return {
        "snapshots": [
            dict(id=str(r.id), label=f"Snapshot {r.id}", sha256=r.sha256) for r in snapshots
        ],
        "samples": [dict(id=str(r.id), label=f"{r.method} • seed {r.seed}") for r in samples],
        "evidence": [
            dict(
                id=str(r.id),
                record_id=str(r.record_id),
                label=r.filename,
                scan_status=r.scan_status,
                sha256=r.sha256,
                version=r.number,
            )
            for r in evidence
        ],
        "limit": 100,
    }


@router.get("/engagements/{eid}/accounts")
async def account_choices(
    eid: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: DB,
    ctx: Actor,
    search: str = Query("", max_length=100),
    comparative: bool = False,
):
    from sqlalchemy import or_

    from app.modules.accounting.models import Account, SourceRecord

    eng = await service.scope(db, ctx, eid)
    snap, _ = await service.snapshot(db, ctx, eng, snapshot_id, comparative)
    query = select(Account).where(
        Account.tenant_id == ctx.tenant_id,
        Account.entity_id == eng.entity_id,
        Account.code.in_(
            select(SourceRecord.canonical["account_code"].astext).where(
                SourceRecord.tenant_id == ctx.tenant_id, SourceRecord.batch_id == snap.batch_id
            )
        ),
    )
    if search:
        query = query.where(
            or_(
                Account.code.contains(search, autoescape=True),
                Account.name.icontains(search, autoescape=True),
            )
        )
    rows = (await db.scalars(query.order_by(Account.code).limit(1001))).all()
    return {
        "items": [{"id": str(r.id), "code": r.code, "name": r.name} for r in rows[:1000]],
        "truncated": len(rows) > 1000,
    }


@router.post("/engagements/{eid}/events/{identifier}/review", status_code=201)
async def review(
    eid: uuid.UUID, identifier: uuid.UUID, data: s.Review, db: DB, ctx: Actor, request: Request
):
    eng = await service.scope(db, ctx, eid, mutable=True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.version != data.expected_version:
        raise HTTPException(409, "Result version conflict")
    reviewer = data.action in {"approve", "reject"}
    needed = (
        "tax.computation.approve"
        if obj.kind == "tax-connected-assessment" and reviewer
        else (
            "audit.evidence.review"
            if obj.kind in {"ocr", "source-table", "workflow-source"} and reviewer
            else "workingpaper.approve"
            if reviewer
            else {
                "submit": "workingpaper.create",
                "finding": "audit.finding.create",
                "note": "workingpaper.review",
                "request-evidence": "audit.evidence.upload",
            }.get(data.action, "audit.testing.execute")
        )
    )
    await engagement_permissions(db, ctx, eid, needed)
    if obj.kind == "tax-connected-assessment" and reviewer:
        await engagement_permissions(db, ctx, eid, "tax.computation.approve")
    if reviewer and str(ctx.user_id) in obj.body.get("contributors", [str(obj.created_by)]):
        raise HTTPException(403, "Independent reviewer required")
    body = dict(obj.body)
    if data.action == "submit":
        if obj.kind != "foundation-validation" or body.get("review_status") not in {
            "UNVERIFIED",
            "REJECTED",
        }:
            raise HTTPException(409, "Only an unsubmitted foundation validation may be submitted")
        body.update(
            review_status="PREPARED",
            submission_reason=data.comments,
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        return audit.serialize(
            await service.append(
                db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
            )
        )
    if data.action == "accept" and obj.kind == "country-workflow":
        rows = [dict(row) for row in body["rows"]]
        selected_row = next((row for row in rows if row["id"] == data.item_id), None)
        if selected_row is None:
            raise HTTPException(422, "Select a workflow exception row")
        selected_row.update(
            auditor_status="EXCEPTION_DOCUMENTED",
            auditor_comments=data.comments,
            auditor=str(ctx.user_id),
            auditor_at=datetime.now(UTC).isoformat(),
        )
        if body.get("workflow") == "sanctions-name-review":
            selected_row["reviewer_disposition"] = "OBSERVATIONS_DOCUMENTED"
        body.update(
            rows=rows,
            review_status="PREPARED",
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        return audit.serialize(
            await service.append(
                db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
            )
        )
    if data.action == "accept" and obj.kind == "reconciliation":
        matches = [dict(i) for i in body["matches"]]
        selected_match = next((i for i in matches if data.item_id in i["left_ids"]), None)
        if not selected_match:
            raise HTTPException(
                422, "Select a proposed match using its original source transaction"
            )
        selected_match.update(
            auditor_status="ACCEPTED",
            auditor=str(ctx.user_id),
            auditor_comments=data.comments,
            auditor_at=datetime.now(UTC).isoformat(),
        )
        body.update(
            matches=matches,
            review_status="PREPARED",
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        return audit.serialize(
            await service.append(
                db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
            )
        )
    if data.action in {"finding", "note", "request-evidence"}:
        if obj.kind not in {"vouching", "reconciliation"} or not data.item_id:
            raise HTTPException(422, "Select a vouching or reconciliation source item")
        collection = (
            obj.body["items"]
            if obj.kind == "vouching"
            else [*obj.body["source_rows"], *obj.body["destination_rows"]]
        )
        item = next((i for i in collection if i["id"] == data.item_id), None)
        if not item:
            raise HTTPException(404, "Vouching item not found")
        from app.db.models.platform import LegalEntity

        entity = await db.get(LegalEntity, eng.entity_id)
        if not entity:
            raise HTTPException(404, "Entity not found")
        source = [{"kind": "intelligence", "id": str(obj.id)}]
        if obj.kind == "vouching" or any(i["id"] == data.item_id for i in obj.body["source_rows"]):
            source.append({"kind": "journal", "id": data.item_id})
        if data.action == "request-evidence":
            kind = "requests"
            content: dict = {
                "client_id": str(entity.client_id),
                "question": data.comments,
                "sources": source,
            }
        elif data.action == "note":
            if not data.target_record_id:
                raise HTTPException(
                    422, "Select the actual working paper or audit record for the review note"
                )
            kind = "review-notes"
            content = {
                "target_id": str(data.target_record_id),
                "assigned_reviewer": str(data.assigned_reviewer or ctx.user_id),
                "narrative": data.comments,
                "sources": source,
            }
        else:
            kind = "findings"
            content = {
                "finding_type": "missing_evidence" if obj.kind == "vouching" else "reconciliation",
                "severity": "medium",
                "narrative": data.comments,
                "financial_impact": None,
                "sources": source,
            }
        from app.modules.intelligence.matching_review import exception_reference

        reference = exception_reference(obj.dependencies, data.item_id, kind)
        existing = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == kind,
                AuditRecord.reference == reference,
            )
        )
        created = (
            audit.serialize(existing)
            if existing
            else await audit.create(
                db,
                ctx,
                eid,
                kind,
                RecordInput(
                    reference=reference,
                    title="Documentary support: " + data.item_id[:8],
                    body=content,
                ),
                request.state.request_id,
            )
        )
        if obj.kind == "reconciliation":
            body.update(
                exceptions=[
                    *body.get("exceptions", []),
                    {
                        "item_id": data.item_id,
                        "record_id": created["id"],
                        "kind": kind,
                        "reason": data.comments,
                        "actor": str(ctx.user_id),
                    },
                ],
                review_status="PREPARED",
                contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
            )
            return audit.serialize(
                await service.append(
                    db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
                )
            )
        items = [dict(i) for i in body["items"]]
        selected_item = next(i for i in items if i["id"] == data.item_id)
        selected_item["linked_records"] = [
            *selected_item.get("linked_records", []),
            {"id": created["id"], "kind": kind, "reason": data.comments},
        ]
        if data.action == "finding":
            selected_item.update(
                auditor_status="EXCEPTION_RECORDED",
                auditor=str(ctx.user_id),
                auditor_comments=data.comments,
            )
        body.update(
            items=items,
            review_status="PREPARED",
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
        )
        result = await service.append(
            db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
        )
        return audit.serialize(result)
    if data.action == "accept":
        if obj.kind != "vouching" or not data.item_id or not data.candidate_id:
            raise HTTPException(422, "Select a vouching item and candidate extraction")
        items = [dict(i) for i in body["items"]]
        item = next((i for i in items if i["id"] == data.item_id), None)
        if not item or not any(
            c["extraction_id"] == str(data.candidate_id) for c in item["candidates"]
        ):
            raise HTTPException(422, "Candidate is not part of this scoped result")
        item.update(
            auditor_status="ACCEPTED",
            accepted_extraction_id=str(data.candidate_id),
            auditor=str(ctx.user_id),
            auditor_comments=data.comments,
            auditor_at=datetime.now(UTC).isoformat(),
        )
        body.update(
            items=items,
            contributors=sorted({*body.get("contributors", []), str(ctx.user_id)}),
            review_status="PREPARED",
        )
    else:
        if data.action == "approve":
            if obj.kind == "report-template":
                from app.modules.regulatory.report_requirements import parse_template, require_ready

                body["requirements_coverage"] = await require_ready(
                    db, ctx, eng, parse_template(obj.body)
                )
            if obj.kind == "reconciliation":
                from app.modules.intelligence.matching_review import verify_review

                await verify_review(db, ctx, eid, obj)
            if obj.kind == "tax-close-rollup" and obj.body.get("blocked"):
                raise HTTPException(
                    409,
                    "Resolve the tax-close finding scope, quantification and review issues before approval",
                )
            if obj.kind == "tax-connected-assessment" and obj.body.get("issues"):
                raise HTTPException(
                    409, "Resolve connected tax issues and regenerate before approval"
                )
            if obj.kind == "foundation-validation" and (
                obj.body.get("review_status") != "PREPARED"
                or obj.body.get("completeness") != "complete"
                or any(
                    i.get("blocking", True) and i.get("disposition", "open") == "open"
                    for i in obj.body.get("issues", [])
                )
            ):
                raise HTTPException(
                    409, "Resolve foundation blockers and regenerate before approval"
                )
            if obj.kind == "regulatory-assessment" and any(
                r.get("applicability") == "PENDING" for r in obj.body["rows"]
            ):
                raise HTTPException(
                    409,
                    "Resolve required applicability facts and numeric source provenance before approval",
                )
            if obj.kind == "country-workflow":
                from app.modules.country_workflows.review import approval_error

                error = approval_error(obj.body)
                if error:
                    raise HTTPException(409, error)
            if obj.kind == "statutory-checklist" and any(
                i["state"] not in {"PREPARED", "NOT_APPLICABLE", "EXCEPTION_IDENTIFIED"}
                for i in obj.body["items"]
            ):
                raise HTTPException(
                    409,
                    "Resolve pending applicability and evidence requirements before approving the specialist checklist",
                )
            for dependency in obj.dependencies:
                if dependency["type"] == "event":
                    supporting = await service.event(
                        db, ctx, eid, uuid.UUID(dependency["id"]), True
                    )
                    if (
                        supporting.kind in {"source-table", "workflow-source"}
                        and supporting.body.get("review_status") != "REVIEWED"
                    ):
                        raise HTTPException(
                            409,
                            "Supporting table needs independent review before approving derived results",
                        )
        if obj.kind == "vouching" and data.action == "approve":
            if not body.get("items") or any(
                i.get("auditor_status") not in {"ACCEPTED", "EXCEPTION_RECORDED"}
                for i in body["items"]
            ):
                raise HTTPException(
                    409,
                    "Every item needs a documented auditor decision or a separate exception workflow",
                )
            for item in body["items"]:
                if item.get("auditor_status") == "EXCEPTION_RECORDED":
                    if not item.get("linked_records"):
                        raise HTTPException(409, "Documented exception record required")
                    for linked in item["linked_records"]:
                        await audit.get_record(db, ctx, eid, uuid.UUID(linked["id"]), lock=False)
                    continue
                extraction = await service.event(
                    db, ctx, eid, uuid.UUID(item["accepted_extraction_id"]), True
                )
                if extraction.body.get("review_status") != "REVIEWED":
                    raise HTTPException(
                        409, "Accepted supporting extraction needs independent field review"
                    )
        if obj.kind == "country-workflow" and obj.body.get("workflow") in {
            "obligation-bank-allocations",
            "merchant-settlement-bridge",
        }:
            from app.modules.country_workflows.bank_consumption import (
                WITHDRAWN,
                approve,
                entity_scope,
            )

            if data.action == "approve":
                cash_manifest, cash_review = await approve(db, ctx, obj)
                body.update(
                    bank_consumption_manifest=cash_manifest, bank_consumption_review=cash_review
                )
            else:
                await entity_scope(db, ctx, eid, lock=True)
                body["bank_consumption_review"] = {
                    "status": WITHDRAWN,
                    "withdrawn_at": datetime.now(UTC).isoformat(),
                    "withdrawn_by": str(ctx.user_id),
                    "reason": data.comments,
                }
        body.update(
            review_status="REVIEWED" if data.action == "approve" else "REJECTED",
            reviewer=str(ctx.user_id),
            reviewed_at=datetime.now(UTC).isoformat(),
            review_comments=data.comments,
        )
    result = await service.append(
        db, ctx, eng, obj.kind, body, obj.dependencies, request.state.request_id, obj
    )
    return audit.serialize(result)


@router.post("/engagements/{eid}/events/{identifier}/working-paper", status_code=201)
async def generate_paper(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: s.GeneratePaper,
    db: DB,
    ctx: Actor,
    request: Request,
):
    eng = await audit.engagement(db, ctx, eid, "workingpaper.create", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    from app.modules.country_workflows.diligence_schemas import (
        DILIGENCE_ROW_TYPES,
        DILIGENCE_WORKFLOWS,
    )

    if (
        obj.body.get("table_type") in DILIGENCE_ROW_TYPES
        or obj.body.get("workflow") in DILIGENCE_WORKFLOWS
    ):
        raise HTTPException(
            409,
            "Diligence results require restricted workpaper handling; generic paper generation is unavailable",
        )
    if obj.body.get("review_status") != "REVIEWED":
        raise HTTPException(
            409, "Independently reviewed source result required before working-paper generation"
        )
    if (
        obj.body.get("workflow") == "stock-audit"
        and obj.body.get("quantity_coverage_contract") != "stock-declared-count-coverage/1"
    ):
        raise HTTPException(
            409,
            "Regenerate stock count coverage with current quantity and sign controls before paper generation",
        )
    from app.modules.country_workflows.withholding_provisions import saved_withdrawn_expectation

    if saved_withdrawn_expectation(obj.body):
        raise HTTPException(
            409,
            "Correct the positive 206C(1H) expectation for the withdrawn period and regenerate before paper generation",
        )
    summary = {
        key: value
        for key, value in obj.body.items()
        if key
        in {
            "section",
            "totals",
            "totals_by_currency",
            "control_comparison",
            "source_totals",
            "destination_totals",
            "sampling_method",
            "seed",
            "review_status",
            "as_of",
            "rationale",
            "withholding_role",
            "comparison_basis",
            "selected_current_totals",
            "assessment_contract_version",
            "withholding_pan_contract",
            "withholding_pan_counts",
            "withholding_provision_scope",
            "turnover_contract",
            "turnover_basis",
            "turnover_difference_totals",
            "inventory_performance_contract",
            "inventory_performance_binding",
            "inventory_performance_scope",
            "inventory_performance_controls",
            "gp_arithmetic_observation",
            "inventory_fifo_contract",
            "inventory_fifo_scope",
            "inventory_fifo_document_binding",
            "coverage",
            "quantity_coverage_basis",
            "quantity_coverage_contract",
            "population_completeness",
            "statutory_calculation_qualified",
            "box_comparison_scope",
            "excluded_box_controls",
            "included_box_controls",
            "limitations",
        }
    }
    tables = [
        {
            "title": "System-generated source calculations",
            "values": summary,
            "source_event_id": str(obj.id),
            "source_sha256": obj.sha256,
            "input_version": obj.version,
        }
    ]
    if isinstance(obj.body.get("rows"), list):
        tables.append(
            {
                "title": "Source schedule",
                "rows": obj.body["rows"][:1000],
                "total_rows": len(obj.body["rows"]),
                "bounded": len(obj.body["rows"]) > 1000,
            }
        )
    if obj.body.get("excluded_box_rows"):
        tables.append(
            {
                "title": "Rows excluded from selected VAT box scope",
                "rows": obj.body["excluded_box_rows"][:1000],
                "total_rows": len(obj.body["excluded_box_rows"]),
                "bounded": len(obj.body["excluded_box_rows"]) > 1000,
            }
        )
    paper = RecordInput(
        reference=data.reference,
        title=data.title,
        body={
            "folder": obj.kind.title(),
            "assertions": data.assertions,
            "sources": [{"kind": "intelligence", "id": str(obj.id)}],
            "sections": [
                {"heading": "Objective — auditor authored", "text": data.objective},
                *(
                    [
                        {
                            "heading": "Selected VAT201 comparison coverage",
                            "text": "Machine comparison covers only VAT201 boxes "
                            + ", ".join(obj.body["box_comparison_scope"]["required_boxes"])
                            + ". Whole-return completeness is not determined. "
                            + str(len(obj.body.get("excluded_box_rows", [])))
                            + " retained source rows were excluded from this comparison; their full detail remains in the source result and XLSX export.",
                        }
                    ]
                    if obj.body.get("box_comparison_scope", {}).get("mode")
                    == "SELECTED_REQUIRED_BOXES"
                    else []
                ),
                {
                    "heading": "System-generated source information",
                    "text": f"Derived from immutable {obj.kind} result {obj.id}, version {obj.version}, SHA-256 {obj.sha256}. Machine output is not a performed audit procedure or reviewed conclusion.",
                },
                {
                    "heading": "Procedures performed — auditor to complete",
                    "text": "No procedures are represented as performed by generation. Record actual testing and evidence assessment.",
                },
            ],
            "financial_tables": tables,
            "conclusion": "Draft only. Auditor must document actual work, exceptions, evidence sufficiency and conclusion before independent review.",
        },
    )
    return await audit.create(db, ctx, eng.id, "working-papers", paper, request.state.request_id)


@router.post("/engagements/{eid}/events/{identifier}/mapping-decisions", status_code=201)
async def mapping_decisions(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    data: s.MappingDecision,
    db: DB,
    ctx: Actor,
    request: Request,
):
    from app.modules.accounting.schemas import AccountAssignment

    eng = await service.scope(db, ctx, eid, "mapping", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if obj.kind != "mapping" or obj.version != data.expected_version:
        raise HTTPException(409, "Mapping proposal version conflict")
    allowed = {r["account_code"] for r in obj.body["suggestions"]}
    if not set(data.assignments) <= allowed:
        raise HTTPException(422, "Assignments must reference accounts in this proposal")
    try:
        assignments = {
            code: AccountAssignment.model_validate(value).model_dump(mode="json")
            for code, value in data.assignments.items()
        }
    except ValidationError:
        raise HTTPException(422, "Invalid human account classification") from None
    return audit.serialize(
        await service.append(
            db,
            ctx,
            eng,
            "mapping",
            {
                **obj.body,
                "human_assignments": assignments,
                "decision_reason": data.reason,
                "contributors": sorted({*obj.body.get("contributors", []), str(ctx.user_id)}),
                "review_status": "PREPARED",
            },
            obj.dependencies,
            request.state.request_id,
            obj,
        )
    )


@router.post("/engagements/{eid}/events/{identifier}/apply-mapping", status_code=201)
async def apply_mapping(
    eid: uuid.UUID, identifier: uuid.UUID, db: DB, ctx: Actor, request: Request
):
    from app.api.v1.accounting import mapping
    from app.db.models.platform import LegalEntity
    from app.modules.accounting.schemas import MappingCreate

    eng = await service.scope(db, ctx, eid, "mapping", True)
    obj = await service.event(db, ctx, eid, identifier, True)
    if (
        obj.kind != "mapping"
        or obj.body.get("review_status") != "REVIEWED"
        or not obj.body.get("human_assignments")
    ):
        raise HTTPException(409, "Documented human assignments and independent approval required")
    entity = await db.get(LegalEntity, eng.entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    profile = await mapping(
        MappingCreate(
            client_id=entity.client_id,
            entity_id=entity.id,
            period_id=eng.period_id,
            name="Reviewed intelligence mapping",
            mapping={"accounts": obj.body["human_assignments"]},
            approved=True,
        ),
        db,
        ctx,
        request,
    )
    record(
        db,
        ctx,
        "intelligence.mapping.applied",
        obj.id,
        request.state.request_id,
        {"proposal_id": str(obj.id), "proposal_sha256": obj.sha256, "profile_id": profile["id"]},
    )
    return profile


@router.post("/engagements/{eid}/ticks", status_code=201)
async def tick(eid: uuid.UUID, data: s.Tick, db: DB, ctx: Actor, request: Request):
    eng = await service.scope(db, ctx, eid, "lead", True)
    paper = await audit.get_record(db, ctx, eid, data.record_id, mutable=True)
    if paper.kind != "working-papers" or paper.version != data.expected_version:
        raise HTTPException(409, "Working-paper version conflict")
    for source in data.supporting_sources:
        await audit.source_record(db, ctx, eng, Source.model_validate(source))
    marker = {
        "mark": data.mark,
        "actor": str(ctx.user_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "supporting_sources": data.supporting_sources,
        "rationale": data.rationale,
        "applied_to_version": paper.version,
        "evidence_sufficiency_determined": False,
    }
    tables = list(paper.body.get("financial_tables", []))
    existing = next((t for t in tables if t.get("title") == "Auditor tick marks"), None)
    if existing:
        tables = [
            {**t, "marks": [*t["marks"], marker]} if t.get("title") == "Auditor tick marks" else t
            for t in tables
        ]
    else:
        tables.append({"title": "Auditor tick marks", "marks": [marker]})
    return await audit.update(
        db,
        ctx,
        eid,
        paper.id,
        RecordPatch(
            version=paper.version,
            reference=paper.reference,
            title=paper.title,
            body={**paper.body, "financial_tables": tables},
        ),
        request.state.request_id,
    )


@router.get("/engagements/{eid}/events/{identifier}/export")
async def export_result(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    format: str = Query("xlsx", pattern="^(xlsx|pdf|docx)$"),
):
    obj = await service.event(db, ctx, eid, identifier)
    await engagement_permissions(db, ctx, eid, "audit.export")
    from starlette.concurrency import run_in_threadpool

    from app.db.models.platform import Tenant
    from app.modules.intelligence.exports import render

    tenant = await db.get(Tenant, ctx.tenant_id)
    freshness = "CURRENT" if await service.current(db, ctx, obj) else "STALE"
    from app.core.pdf_text import PDFTextError
    from app.modules.intelligence.xlsx_values import XlsxValueLimitError

    try:
        content, media = await run_in_threadpool(
            render,
            {
                **audit.serialize(obj),
                "firm_name": tenant.name if tenant else "",
                "freshness": freshness,
                "exported_at": datetime.now(UTC).isoformat(),
            },
            format,
        )
    except (XlsxValueLimitError, PDFTextError) as error:
        raise HTTPException(422, str(error)) from error
    content_sha256 = hashlib.sha256(content).hexdigest()
    record(
        db,
        ctx,
        "intelligence.exported",
        obj.id,
        request.state.request_id,
        {
            "format": format,
            "sha256": obj.sha256,
            "freshness": freshness,
            "content_sha256": content_sha256,
            "content_bytes": len(content),
        },
    )
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{obj.kind}-{str(obj.id)[:8]}.{format}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Export-SHA256": content_sha256,
        },
    )


@router.get("/engagements/{eid}/evidence/{identifier}/preview")
async def preview(
    eid: uuid.UUID,
    identifier: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    page: int = Query(1, ge=1, le=20),
    member: str | None = Query(None, max_length=500),
):
    from starlette.concurrency import run_in_threadpool

    from app.modules.intelligence.documents import preview_page
    from app.modules.lineage.storage import ObjectStore, hash_file

    eng = await service.scope(db, ctx, eid)
    version, _ = await service.evidence(db, ctx, eng, identifier)

    def render_page():
        with ObjectStore().local(version.object_key, version.object_version) as path:
            if hash_file(path) != version.sha256:
                raise ValueError("Evidence integrity verification failed")
            return preview_page(path, version.media_type, page, member)

    try:
        content = await run_in_threadpool(render_page)
    except (ValueError, OSError, KeyError, EOFError):
        raise HTTPException(422, "Preview unavailable for this document and page") from None
    record(
        db,
        ctx,
        "intelligence.evidence.previewed",
        version.id,
        request.state.request_id,
        {"page": page},
    )
    return Response(
        content,
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

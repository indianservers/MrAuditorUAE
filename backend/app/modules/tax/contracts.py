"""Additive tax execution receipts. Filing, cash and authority states are never inferred."""

import uuid
from datetime import date
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from app.core.engine_contracts import Contract
from app.db.models.platform import Engagement, FinancialPeriod
from app.modules.accounting.models import ImportBatch, ImportSnapshot
from app.modules.lineage.freshness import mapping_receipt


class TaxExecution(Contract):
    schema_version: Literal["tax/1"] = "tax/1"
    execution_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    entity_id: uuid.UUID
    engagement_id: uuid.UUID
    period_id: uuid.UUID
    period_start: date
    period_end: date
    tax_type: Literal["VAT", "CT", "QFZP", "TP", "DMTT"]
    calculation_version: str
    execution_mode: Literal["deterministic"] = "deterministic"
    input_completeness: Literal["complete_for_supported_case", "partial", "unknown"]
    professional_review: Literal["DRAFT_REQUIRES_REVIEW"] = "DRAFT_REQUIRES_REVIEW"
    filing_status: Literal["NOT_SUBMITTED"] = "NOT_SUBMITTED"
    authority_assessment: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    payment_status: Literal["NOT_RECONCILED"] = "NOT_RECONCILED"
    source_snapshots: list[dict]
    account_mapping_receipt: list[dict]
    rule_versions: dict = Field(default_factory=dict)
    registrations_and_elections: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    rounding: str
    accounting_amount: str | None = None
    calculated_liability: str | None = None
    evidence_references: list[dict] = Field(default_factory=list)


async def snapshots(db, tenant, entity, period):
    rows = (await db.scalars(select(ImportSnapshot).join(
        ImportBatch, ImportBatch.id == ImportSnapshot.batch_id
    ).where(ImportSnapshot.tenant_id == tenant, ImportSnapshot.entity_id == entity,
            ImportSnapshot.period_id == period, ImportBatch.status == "active",
            ImportBatch.kind.in_(["gl", "journals"]))
        .order_by(ImportSnapshot.id))).all()
    return [{"id": str(row.id), "sha256": row.sha256} for row in rows]


async def attach(db, ctx, eid, tax_type, result, inputs, dependencies, profile=None):
    eng = await db.get(Engagement, eid)
    period = await db.get(FinancialPeriod, eng.period_id)
    questions = [str(x) for x in result.get("issues", [])]
    questions += [x.get("message", str(x)) for x in result.get("exceptions", [])]
    questions += [str(x) for x in result.get("unresolved", [])]
    if result.get("assessment") in {"INSUFFICIENT_DATA", "REVIEW_REQUIRED"}:
        questions.append("Legal eligibility remains unresolved")
    if result.get("status") in {"INCOMPLETE_SCOPE", "UNSUPPORTED_CASE", "LOSS_OR_NEGATIVE_TAX_TECHNICAL_REVIEW"}:
        questions.append(result["status"])
    receipts = await snapshots(db, ctx.tenant_id, eng.entity_id, eng.period_id)
    if not receipts:
        questions.append("No active journal snapshot; source coverage requires review")
    # Never imply all tax cases are covered merely because arithmetic succeeded.
    liability = result.get("current_tax", result.get("net_vat", result.get("uae_dmtt")))
    contract = TaxExecution(
        tenant_id=ctx.tenant_id, entity_id=eng.entity_id, engagement_id=eid, period_id=eng.period_id,
        period_start=getattr(profile, "tax_start", getattr(profile, "period_start", period.start_date)),
        period_end=getattr(profile, "tax_end", getattr(profile, "period_end", period.end_date)),
        tax_type=tax_type, calculation_version=f"connected-{tax_type.lower()}/1",
        input_completeness="partial" if questions else "complete_for_supported_case",
        source_snapshots=receipts,
        account_mapping_receipt=await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
        rule_versions=inputs.get("rules", result.get("rules", {})),
        registrations_and_elections={"profile_id": inputs.get("profile_id"),
            "elections": result.get("safe_harbours", []), "sbr": result.get("sbr"),
            "registration": getattr(profile, "trn", None)},
        assumptions=["Approved human classifications remain legal inputs; no AI eligibility determination"],
        unresolved_questions=questions, evidence_references=dependencies,
        rounding="VAT/DMTT: explicit nearest 0.01 HALF_UP; CT/TP internal schedules: 0.00000001 HALF_UP; filing rounding requires reviewed return mapping",
        accounting_amount=str(result["accounting_profit"]) if "accounting_profit" in result else None,
        calculated_liability=str(liability) if liability is not None else None,
    )
    return {**result, "tax_execution": contract.model_dump(mode="json")}


async def current(db, ctx, eid, result):
    receipt = result.get("tax_execution")
    if receipt is None:
        return True  # Existing legacy adapters retain their prior checks; no invented receipts.
    eng = await db.get(Engagement, eid)
    return bool(receipt.get("schema_version") == "tax/1"
        and receipt.get("tenant_id") == str(ctx.tenant_id)
        and receipt.get("engagement_id") == str(eid)
        and receipt.get("entity_id") == str(eng.entity_id)
        and receipt.get("source_snapshots") == await snapshots(db, ctx.tenant_id, eng.entity_id, eng.period_id)
        and receipt.get("account_mapping_receipt") == await mapping_receipt(db, ctx.tenant_id, eng.entity_id))

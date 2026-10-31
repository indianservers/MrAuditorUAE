"""Accounting execution receipts within the existing immutable CalculationRun."""

import hashlib
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from app.db.models.platform import Engagement, FinancialPeriod, LegalEntity
from app.modules.accounting.models import Currency, ImportBatch, ImportSnapshot
from app.modules.audit_execution.models import AuditRecord
from app.modules.audit_execution.schemas import Strict


class AccountingExecution(Strict):
    contract_version: Literal["accounting/1"] = "accounting/1"
    tenant_id: str
    entity_id: str
    entity_version: int
    engagement_id: str
    period_id: str | None
    period_start: str | None
    period_end: str | None
    framework: str
    functional_currency: str
    presentation_currency: str
    calculation_version: str = "auditos-accounting/3.1"
    implementation_sha256: str
    execution_mode: Literal["deterministic_python_decimal"] = "deterministic_python_decimal"
    rounding: str = "Decimal precision 48; schedule HALF_UP to 8 decimal places; journals use currency minor units"
    policy_versions: list[dict] = Field(default_factory=list)
    approved_assumptions: list[dict] = Field(default_factory=list)
    source_snapshots: list[dict] = Field(default_factory=list)
    chart_snapshots: list[dict] = Field(default_factory=list)
    currency_policy: dict = Field(default_factory=dict)
    evidence: list[dict] = Field(default_factory=list)
    source_completeness: Literal["complete_for_declared_scope", "partial", "unknown"]
    source_balance: str = "Retained ledger snapshot; original balances are never overwritten"
    calculated_adjustment: str = "Calculation output; recognition and accounts require review"
    proposed_journals: list[dict] = Field(default_factory=list)
    journal_state: Literal["NOT_POSTED"] = "NOT_POSTED"
    review_status: Literal["DRAFT_REQUIRES_REVIEW"] = "DRAFT_REQUIRES_REVIEW"
    unresolved_issues: list[dict] = Field(default_factory=list)
    supporting_runs: list[dict] = Field(default_factory=list)
    current_tax_runs: list[dict] = Field(default_factory=list)


def implementation_hash():
    folder = Path(__file__).parent
    names = [
        "calculations.py",
        "schemas.py",
        "inventory.py",
        "employee_benefits.py",
        "intercompany.py",
        "group_comparatives.py",
        "service.py",
        "contracts.py",
    ]
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode())
        digest.update((folder / name).read_bytes())
    return digest.hexdigest()


async def chart_receipts(db, ctx, eid):
    eng = await db.get(Engagement, eid)
    rows = (
        await db.scalars(
            select(ImportSnapshot)
            .join(ImportBatch, ImportBatch.id == ImportSnapshot.batch_id)
            .where(
                ImportSnapshot.tenant_id == ctx.tenant_id,
                ImportSnapshot.entity_id == eng.entity_id,
                ImportSnapshot.period_id == eng.period_id,
                ImportBatch.kind == "coa",
                ImportBatch.status == "active",
            )
        )
    ).all()
    return sorted(
        [{"id": str(row.id), "sha256": row.sha256} for row in rows], key=lambda r: r["id"]
    )


async def currency_receipt(db, ctx, code):
    from babel.numbers import get_currency_precision

    policy = await db.scalar(
        select(Currency).where(Currency.tenant_id == ctx.tenant_id, Currency.code == code)
    )
    return {
        "code": code,
        "precision": policy.precision if policy else get_currency_precision(code),
        "rounding": policy.rounding if policy else "ROUND_HALF_EVEN",
    }


async def attach(db, ctx, eid, inputs, deps, results):
    eng = await db.scalar(
        select(Engagement).where(Engagement.id == eid, Engagement.tenant_id == ctx.tenant_id)
    )
    entity = await db.get(LegalEntity, eng.entity_id)
    period = await db.get(FinancialPeriod, eng.period_id) if eng.period_id else None
    policies, assumptions, evidence, snapshots, supporting, tax_runs = [], [], [], [], set(), set()
    issues = list(results.get("issues", []))
    for dep in deps:
        obj = await db.scalar(
            select(AuditRecord).where(
                AuditRecord.id == uuid.UUID(dep["id"]), AuditRecord.tenant_id == ctx.tenant_id
            )
        )
        if not obj:
            continue
        receipt = {
            "id": str(obj.id),
            "version": obj.version,
            "kind": obj.kind,
            "status": obj.status,
        }
        assumptions.append(receipt)
        evidence += obj.body.get("sources", [])
        if obj.kind == "ifrs-profile":
            policies.append(
                {
                    **receipt,
                    "framework": obj.body["framework"],
                    "technical_validation": obj.body["technical_validation"],
                }
            )
            for key in ("snapshot_id", "comparative_snapshot_id"):
                if not obj.body.get(key):
                    continue
                snap = await db.get(ImportSnapshot, uuid.UUID(obj.body[key]))
                batch = await db.get(ImportBatch, snap.batch_id) if snap else None
                snapshots.append(
                    {
                        "id": obj.body[key],
                        "sha256": snap.sha256 if snap else None,
                        "source_complete": bool(
                            batch and batch.options.get("source_complete") is True
                        ),
                    }
                )
                evidence.append({"kind": "snapshot", "id": obj.body[key]})
        for key in ("calculation_run_id", "previous_run_id"):
            if obj.body.get(key):
                supporting.add((str(obj.engagement_id), obj.body[key]))
        if obj.kind == "ifrs-financials":
            supporting.add((str(obj.engagement_id), obj.body["run_id"]))
        supporting.update(
            (str(obj.engagement_id), rid) for rid in obj.body.get("schedule_run_ids", [])
        )
        if obj.body.get("current_tax_run_id"):
            tax_runs.add((str(obj.engagement_id), obj.body["current_tax_run_id"]))
    if inputs.get("profile_id") and not policies:
        issues.append(
            {
                "code": "APPROVED_POLICY_MISSING",
                "blocking": True,
                "remediation": "Attach an approved full-IFRS reporting profile",
            }
        )
    if inputs.get("comparative_source"):
        source = inputs["comparative_source"]
        supporting.add((str(source["engagement_id"]), str(source["run_id"])))
    complete = bool(snapshots) and all(s["source_complete"] for s in snapshots)
    if not complete:
        issues.append(
            {
                "code": "SOURCE_SCOPE_UNCONFIRMED",
                "blocking": True,
                "remediation": "Review the declared ledger population; schedule output does not establish full-ledger completeness",
            }
        )
    if not evidence:
        issues.append(
            {
                "code": "EVIDENCE_LINKS_MISSING",
                "blocking": True,
                "remediation": "Retain source evidence links on approved inputs",
            }
        )
    execution_receipt = AccountingExecution(
        tenant_id=str(ctx.tenant_id),
        entity_id=str(eng.entity_id),
        entity_version=entity.version,
        engagement_id=str(eid),
        period_id=str(eng.period_id) if eng.period_id else None,
        period_start=str(period.start_date) if period else None,
        period_end=str(period.end_date) if period else None,
        framework=policies[0]["framework"] if policies else "NOT_ESTABLISHED",
        functional_currency=entity.functional_currency,
        presentation_currency=results.get("currency", entity.functional_currency),
        implementation_sha256=implementation_hash(),
        policy_versions=policies,
        approved_assumptions=assumptions,
        source_snapshots=snapshots,
        chart_snapshots=await chart_receipts(db, ctx, eid),
        currency_policy=await currency_receipt(db, ctx, entity.functional_currency),
        evidence=evidence,
        source_completeness="complete_for_declared_scope"
        if complete
        else "partial"
        if snapshots
        else "unknown",
        proposed_journals=results.get("journal_proposals", []),
        unresolved_issues=issues,
        supporting_runs=[{"engagement_id": en, "id": rid} for en, rid in sorted(supporting)],
        current_tax_runs=[{"engagement_id": en, "id": rid} for en, rid in sorted(tax_runs)],
    )
    results["execution"] = execution_receipt.model_dump(mode="json")


def receipt_current(ctx, eid, calculation):
    receipt = calculation.results.get("execution")
    return bool(
        receipt
        and receipt.get("contract_version") == "accounting/1"
        and receipt.get("tenant_id") == str(ctx.tenant_id)
        and receipt.get("engagement_id") == str(eid)
        and receipt.get("implementation_sha256") == implementation_hash()
    )

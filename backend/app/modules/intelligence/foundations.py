"""E01/E02/E03/E20 coordinator over existing, versioned engine outputs."""

import uuid

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import func, select

from app.core.engine_contracts import EngineIssue, EngineResult
from app.db.models.platform import FinancialPeriod
from app.modules.accounting.models import Account, ImportBatch, JournalLine, ValidationResult
from app.modules.jurisdictions.profiles import Strict
from app.modules.jurisdictions.workspace import resolved
from app.modules.lineage.freshness import mapping_receipt


class DocumentLink(Strict):
    extraction_id: uuid.UUID
    journal_line_id: uuid.UUID
    fields: list[str] = Field(default_factory=lambda: ["gross_amount"], min_length=1, max_length=30)


class ValidationInput(Strict):
    snapshot_id: uuid.UUID
    extraction_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    assessment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    document_links: list[DocumentLink] = Field(default_factory=list, max_length=200)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    rationale: str = Field(min_length=10, max_length=4000)


class PeriodAction(Strict):
    expected_version: int = Field(ge=1)
    action: str = Field(pattern="^(lock|reopen)$")
    reason: str = Field(min_length=10, max_length=4000)


async def validate(db, ctx, eng, data):
    from app.modules.intelligence import service

    package, context = await resolved(db, ctx, eng)
    source, receipt = await service.snapshot(db, ctx, eng, data.snapshot_id)
    if source.period_id != eng.period_id:
        raise HTTPException(422, "Foundation snapshot must match the engagement period")
    batch = await db.get(ImportBatch, source.batch_id)
    issues = []
    deps = [
        receipt,
        {
            "type": "mapping",
            "entity_id": str(eng.entity_id),
            "receipt": await mapping_receipt(db, ctx.tenant_id, eng.entity_id),
        },
    ]

    def issue(code, reason, remediation, affected=(), url=None):
        issues.append(
            EngineIssue(
                code=code,
                reason=reason,
                remediation=remediation,
                affected_records=list(affected),
                owner=str(ctx.user_id),
                url=url,
            )
        )

    if package.country != "AE":
        issue(
            "unsupported_jurisdiction",
            "Phase 1 foundation validation is qualified for UAE engagements only",
            "Select an approved UAE reporting context",
        )
    if context["version"] == 0 or context["framework"].startswith("UNCONFIGURED"):
        issue(
            "unverified_rule",
            "An explicitly reviewed reporting context is required",
            "Review the engagement reporting context",
            url=f"/engagements/{eng.id}/lifecycle",
        )
    if batch.kind not in {"gl", "journals"}:
        issue("incompatible_schema", "Journal/GL source is required", "Import a journal population")
    options = batch.options
    if not options.get("source_complete"):
        issue(
            "missing_evidence",
            "Source is a partial or unconfirmed extract; imbalance is not an accounting conclusion",
            "Obtain and reconcile a complete source extract",
            [str(batch.id)],
        )
    controls = (
        await db.scalars(
            select(ValidationResult).where(
                ValidationResult.tenant_id == ctx.tenant_id,
                ValidationResult.batch_id == batch.id,
                ValidationResult.rule.in_(
                    ["source_count", "source_total_debit", "source_total_credit", "journal_balance"]
                ),
            )
        )
    ).all()
    by_rule = {row.rule: row for row in controls}
    for name in ["source_count", "source_total_debit", "source_total_credit", "journal_balance"]:
        if name not in by_rule or by_rule[name].status != "passed":
            issue(
                "missing_evidence",
                f"Independent import control not satisfied: {name}",
                "Supply source totals/count and validate the import",
                [str(batch.id)],
                "/integrations",
            )
    accounts = (
        await db.scalars(
            select(Account)
            .where(
                Account.tenant_id == ctx.tenant_id,
                Account.id.in_(
                    select(JournalLine.account_id).where(
                        JournalLine.tenant_id == ctx.tenant_id, JournalLine.snapshot_id == source.id
                    )
                ),
            )
            .order_by(Account.code)
        )
    ).all()
    if not accounts:
        issue(
            "missing_evidence",
            "No committed journal accounts",
            "Activate a validated journal import",
        )
    unmapped = [str(a.id) for a in accounts if not a.classification or not a.mapping_profile_id]
    if unmapped:
        issue(
            "invalid_input",
            f"{len(unmapped)} accounts lack an approved mapping",
            "Review account mappings; tax classifications are separate",
            unmapped,
            f"/intelligence/{eng.id}/mapping",
        )
    links = []
    for link in data.document_links:
        if link.extraction_id not in data.extraction_ids:
            raise HTTPException(422, "Document links must use selected extractions")
        line = await db.scalar(
            select(JournalLine).where(
                JournalLine.tenant_id == ctx.tenant_id,
                JournalLine.snapshot_id == source.id,
                JournalLine.id == link.journal_line_id,
            )
        )
        if not line:
            raise HTTPException(
                422, "Linked journal line must belong to the selected source snapshot"
            )
        extraction = await service.event(db, ctx, eng.id, link.extraction_id, True)
        if any(extraction.body.get("fields", {}).get(field) is None for field in link.fields):
            raise HTTPException(422, "Linked extraction fields must have reviewed values")
        links.append(
            {
                **link.model_dump(mode="json"),
                "source_record_id": str(line.source_record_id),
                "snapshot_id": str(source.id),
                "extraction_sha256": extraction.sha256,
                "rationale": data.rationale,
                "relation": "human_selected_support; not automatic monetary reconciliation",
            }
        )
    for identifier in data.extraction_ids:
        if not any(link.extraction_id == identifier for link in data.document_links):
            issue(
                "missing_evidence",
                "Document extraction is not linked to a normalized transaction",
                "Select a supporting journal line and document the relationship",
                [str(identifier)],
            )
    for ids, kind, label in [
        (data.extraction_ids, "ocr", "document extraction"),
        (data.assessment_ids, "regulatory-assessment", "verified rule assessment"),
    ]:
        if not ids:
            issue(
                "missing_evidence" if kind == "ocr" else "unverified_rule",
                f"Missing reviewed {label}",
                f"Create and independently review a {label}",
            )
        for identifier in dict.fromkeys(ids):
            obj = await service.event(db, ctx, eng.id, identifier, True)
            if obj.kind != kind:
                raise HTTPException(422, f"Expected {label}")
            deps.append(service.event_receipt(obj))
            if obj.body.get("review_status") != "REVIEWED":
                issue(
                    "missing_evidence",
                    f"Independent review required: {label}",
                    "Submit to an independent reviewer",
                    [str(identifier)],
                    f"/intelligence/{eng.id}/{kind}?event={identifier}",
                )
            if kind == "ocr" and not any(d.get("type") == "evidence" for d in obj.dependencies):
                issue(
                    "missing_evidence",
                    "Legacy provenance incomplete: extraction has no original evidence receipt",
                    "Reprocess from retained, clean original evidence",
                    [str(identifier)],
                )
            if kind == "ocr" and any(
                "parsing failed" in message
                or "conflicting values" in message
                or message == "Net plus tax does not equal gross"
                for message in obj.body.get("validation_messages", [])
            ):
                issue(
                    "invalid_input",
                    "Extraction has unresolved parsing or arithmetic issues",
                    "Correct the extracted values and independently review the new version",
                    [str(identifier)],
                )
            if kind == "ocr" and not any(
                v is not None for v in obj.body.get("fields", {}).values()
            ):
                issue(
                    "missing_evidence",
                    "Extraction has no resolved fields",
                    "Review or correct the source fields",
                    [str(identifier)],
                )
            if kind == "regulatory-assessment" and (
                not obj.body.get("rows")
                or any(
                    r.get("applicability") not in {"APPLICABLE", "NOT_APPLICABLE"}
                    for r in obj.body["rows"]
                )
            ):
                issue(
                    "unverified_rule",
                    "Rule applicability remains unresolved",
                    "Resolve verified rule applicability",
                    [str(identifier)],
                )
    result = EngineResult(
        tenant_id=ctx.tenant_id,
        entity_id=eng.entity_id,
        engagement_id=eng.id,
        period_id=eng.period_id,
        jurisdiction=package.country,
        framework=context["framework"],
        calculation_version="foundation-validation/1",
        completeness="partial" if issues else "complete",
        issues=issues,
        assumptions=data.assumptions,
        evidence_references=deps,
        results={
            "snapshot_id": str(source.id),
            "account_count": len(accounts),
            "document_links": links,
            "source_controls": {
                r.rule: {"status": r.status, "evidence": r.evidence} for r in controls
            },
            "scope": "Foundation technical controls; not a legal opinion or audit conclusion",
        },
    )
    return {
        **result.model_dump(mode="json"),
        "title": "Foundation validation workpaper",
        "rationale": data.rationale,
    }, deps


async def diagnostics(db, ctx, eng):
    from app.core.config import settings
    from app.modules.intelligence.models import IntelligenceEvent, IntelligenceJob

    jobs = (
        await db.execute(
            select(IntelligenceJob.status, func.count())
            .where(
                IntelligenceJob.tenant_id == ctx.tenant_id, IntelligenceJob.engagement_id == eng.id
            )
            .group_by(IntelligenceJob.status)
        )
    ).all()
    period = await db.get(FinancialPeriod, eng.period_id)
    if not period:
        raise HTTPException(409, {"code": "invalid_input", "message": "Select an engagement reporting period before foundation diagnostics"})
    last = await db.scalar(
        select(IntelligenceJob)
        .where(
            IntelligenceJob.tenant_id == ctx.tenant_id,
            IntelligenceJob.engagement_id == eng.id,
            IntelligenceJob.status == "completed",
        )
        .order_by(IntelligenceJob.updated_at.desc(), IntelligenceJob.id)
        .limit(1)
    )
    result = await db.get(IntelligenceEvent, last.result_id) if last and last.result_id else None
    return {
        "runtime": "available",
        "professional_correctness": "not_assessed",
        "period": {
            "id": str(period.id),
            "state": period.lock_state,
            "version": period.lock_version,
        },
        "job_counts": dict(jobs),
        "queue_observation": "Persisted outbox counts; not broker availability",
        "last_successful_execution": {
            "job_id": str(last.id),
            "at": last.updated_at.isoformat(),
            "processing_duration_seconds": result.body.get("processing_duration_seconds")
            if result
            else None,
        }
        if last
        else None,
        "dependencies": {
            "database": "reachable",
            "scanner": "configured_unprobed" if settings().evidence_clamav_host else "unconfigured",
            "broker": "not_probed",
            "language_model": "not_required",
        },
        "malware_scanning": "Requires an operational configured ClamAV service",
    }

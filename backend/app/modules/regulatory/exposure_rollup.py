"""Exact finding-identity roll-up across reviewed workpapers; no tax liability inference."""

import hashlib
import uuid
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select

from app.modules.audit_execution.schemas import Strict

CONTRACT = "tax-close-finding-rollup/1"
REVIEWED_FINDINGS = {"RESOLVED", "ACCEPTED_UNRESOLVED", "CLOSED"}


class ExposureRollupInput(Strict):
    workpaper_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def explicit_population(self):
        if (
            len(set(self.workpaper_ids)) != len(self.workpaper_ids)
            or len(self.rationale.strip()) < 10
        ):
            raise ValueError("Select distinct workpapers and document the tax-close population")
        return self


def implementation_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def summarize(papers, findings):
    linked = defaultdict(set)
    for paper in papers:
        for source in paper["body"].get("sources", []):
            if source["kind"] == "record" and source["id"] in findings:
                linked[source["id"]].add(paper["id"])
    rows, issues = [], []
    for paper in papers:
        for source in paper["body"].get("sources", []):
            if source["kind"] == "finding":
                issues.append(
                    {
                        "source_id": source["id"],
                        "workpaper_id": paper["id"],
                        "code": "ANALYTICS_FINDING_REQUIRES_AUDIT_FINDING_ASSESSMENT",
                    }
                )
    totals: dict[str, dict[str, Any]] = {}
    for paper in papers:
        if not any(paper["id"] in refs for refs in linked.values()):
            issues.append({"source_id": paper["id"], "code": "NO_LINKED_AUDIT_FINDING"})
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        for identifier, references in sorted(linked.items()):
            finding = findings[identifier]
            amount = finding["body"].get("financial_impact")
            currency = finding["body"].get("financial_impact_currency")
            missing = []
            if finding["status"] not in REVIEWED_FINDINGS:
                missing.append("FINDING_REVIEW_REQUIRED")
            if amount is None:
                missing.append("IMPACT_UNQUANTIFIED")
            if currency is None:
                missing.append("IMPACT_CURRENCY_UNASSESSED")
            for code in missing:
                issues.append({"source_id": identifier, "code": code})
            if not missing:
                number = Decimal(str(amount))
                group = totals.setdefault(
                    currency,
                    {
                        "positive_impact": Decimal(0),
                        "negative_impact": Decimal(0),
                        "finding_count": 0,
                    },
                )
                group["positive_impact" if number >= 0 else "negative_impact"] += number
                group["finding_count"] += 1
            rows.append(
                {
                    "id": identifier,
                    "reference": finding["reference"],
                    "status": finding["status"],
                    "area": finding["body"].get("area"),
                    "financial_impact": amount,
                    "currency": currency,
                    "correction_status": finding["body"].get("correction_status", "not_applicable"),
                    "workpaper_ids": sorted(references),
                    "reference_count": len(references),
                    "aggregation": "PENDING" if missing else "COUNTED_ONCE",
                    "issues": missing,
                }
            )
    occurrence_count = sum(len(refs) for refs in linked.values())
    return {
        "rows": rows,
        "totals_by_currency": {
            currency: {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in values.items()
            }
            for currency, values in sorted(totals.items())
        },
        "issues": issues,
        "blocked": bool(issues),
        "unique_findings": len(rows),
        "workpaper_reference_count": occurrence_count,
        "reference_count_basis": "DISTINCT_WORKPAPER_AUDIT_FINDING_PAIRS",
        "duplicate_references_eliminated": occurrence_count - len(rows),
        "limitations": [
            "Only the explicitly selected workpapers and linked audit finding identities are covered",
            "Different finding IDs are not assumed to be the same underlying transaction or risk",
            "Currencies and positive/negative impacts are separate; no net tax liability or recoverability is inferred",
            "Correction status is retained without automatically reducing the reported gross impacts",
            "Unknown amounts, currencies and unreviewed findings remain unresolved, never zero",
        ],
    }


async def prepare(db, ctx, eng, data, request_id):
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.models import AuditRecord
    from app.modules.intelligence import service as intelligence
    from app.modules.lineage.working_papers import require_current

    papers, findings, dependencies, contributors = [], {}, [], {str(ctx.user_id)}
    records = {}
    referenced: set[uuid.UUID] = set()
    for identifier in data.workpaper_ids:
        paper = await audit.get_record(db, ctx, eng.id, identifier, lock=False)
        if paper.kind != "working-papers" or paper.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(409, "Select current independently reviewed working papers")
        await require_current(db, ctx, paper)
        papers.append(audit.serialize(paper))
        records[str(paper.id)] = paper
        referenced.update(
            uuid.UUID(str(source["id"]))
            for source in paper.body.get("sources", [])
            if source["kind"] == "record"
        )
    candidates = (
        await db.scalars(
            select(AuditRecord.id)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.kind == "findings",
                AuditRecord.id.in_(referenced),
            )
            .order_by(AuditRecord.id)
            .limit(101)
        )
    ).all()
    if len(candidates) > 100:
        raise HTTPException(422, "Tax-close roll-up is bounded to 100 distinct linked findings")
    for identifier in candidates:
        finding = await audit.get_record(db, ctx, eng.id, identifier, lock=False)
        await require_current(db, ctx, finding)
        records[str(identifier)] = finding
        findings[str(identifier)] = audit.serialize(finding)
    for identifier, record in sorted(records.items()):
        dependencies.append({"type": "record", "id": identifier, "version": record.version})
        contributors.update([str(record.created_by), *record.body.get("contributors", [])])
    result = summarize(papers, findings)
    return await intelligence.append(
        db,
        ctx,
        eng,
        "tax-close-rollup",
        {
            **result,
            "title": data.title,
            "rationale": data.rationale,
            "contract": CONTRACT,
            "implementation_sha256": implementation_hash(),
            "review_status": "UNVERIFIED",
            "contributors": sorted(contributors),
            "professional_conclusion": "NOT_DETERMINED",
        },
        dependencies,
        request_id,
    )

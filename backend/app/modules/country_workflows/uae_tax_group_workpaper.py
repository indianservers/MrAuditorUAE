"""Retained-source wrapper for the distinct UAE Tax Group statement workpaper."""

import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.modules.grc.deadlines import CalendarDate
from app.modules.ifrs.uae_tax_group_statements import (
    CONTRACT as ENGINE_CONTRACT,
)
from app.modules.ifrs.uae_tax_group_statements import (
    CTP007_SHA256,
    FTA7_SHA256,
    TaxGroupStatements,
    calculate,
)
from app.modules.jurisdictions.packages import fingerprint
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "uae-tax-group-retained-workpaper/1"
BINDING = "ORIGINAL_BYTES_VERIFIED_AND_MAPPING_PARSED"
COLLECTIONS = {
    "statements": "rows",
    "sources": "tax_group_source_lines",
    "members": "tax_group_members",
    "adjustments": "tax_group_adjustments",
    "checks": "tax_group_checks",
    "notes": "tax_group_notes",
    "issues": "tax_group_issues",
    "losses": "tax_group_losses",
    "documents": "tax_group_documents",
}


class TaxGroupWorkpaperInput(Strict):
    profile: Literal["uae-tax-group-retained-workpaper/1"]
    label: str = Field(min_length=1, max_length=200)
    assessed_on: CalendarDate
    adopted_from: CalendarDate
    adopted_through: CalendarDate
    operative_changes: Literal["assessed_none", "unresolved"]
    legal_adoption_assessment: str = Field(min_length=10, max_length=4000)
    rule_evidence_version_id: UUID
    clarification_evidence_version_id: UUID
    adoption_evidence_version_id: UUID
    adoption_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapping_evidence_version_id: UUID
    mapping_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def scope_and_roles(self):
        if not self.label.strip() or len(self.legal_adoption_assessment.strip()) < 10:
            raise ValueError("Retain a meaningful title and operative-source assessment")
        if not date(2025, 7, 16) <= self.assessed_on <= date.today():
            raise ValueError("Assess after FTA7 issuance, not a future date")
        if not self.adopted_from <= self.assessed_on <= self.adopted_through:
            raise ValueError("Retain a source-adoption window covering the assessment")
        if (
            len({row[1] for row in role_sources(self)}) != 4
            or len({row[2] for row in role_sources(self)}) != 4
        ):
            raise ValueError(
                "Retain separate original FTA7, CTP007, legal adoption and mapping documents"
            )
        return self


def role_sources(data):
    return [
        ("fta7", data.rule_evidence_version_id, FTA7_SHA256),
        ("ctp007", data.clarification_evidence_version_id, CTP007_SHA256),
        ("legal_adoption", data.adoption_evidence_version_id, data.adoption_sha256),
        ("independent_mapping", data.mapping_evidence_version_id, data.mapping_sha256),
    ]


def validate_workpaper(data, workpaper):
    if (
        not data.adopted_from
        <= workpaper.current.period_start
        <= workpaper.current.period_end
        <= data.assessed_on
    ):
        raise ValueError("Source adoption and assessment must cover the completed current period")
    if workpaper.comparative and data.adopted_from > workpaper.comparative.period_start:
        raise ValueError("Adopt the comparative framework for its preceding period")
    roles = {row[1] for row in role_sources(data)}
    hashes = {row[2] for row in role_sources(data)}
    for period in (workpaper.current, workpaper.comparative):
        if period:
            for member in period.members:
                if member.source_evidence_version_id in roles or member.source_sha256 in hashes:
                    raise ValueError(
                        "Member statements must be separate from authority, adoption and mapping evidence"
                    )


def parse_mapping(raw: bytes):
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Statement mapping exceeds its 8 MiB limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate statement-mapping JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Use finite exact decimal strings in the statement mapping")

    parsed = json.loads(
        raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid
    )
    pending = [(parsed, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 32:
            raise ValueError("Statement mapping nesting exceeds its limit")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return TaxGroupStatements.model_validate(parsed)


def mapping_schema():
    """Describe the JSON document boundary, including its no-fractional-number rule."""
    schema = TaxGroupStatements.model_json_schema()
    amount_fields = {
        "amount",
        "delta",
        "deductible_loss",
        "previously_reversed",
        "period_income",
        "cost_basis",
        "cumulative_impairment",
    }
    for model in schema.get("$defs", {}).values():
        for name, field in model.get("properties", {}).items():
            if name not in amount_fields:
                continue
            alternatives = field.get("anyOf", [])
            nonnegative = any(option.get("minimum") == 0 for option in alternatives)
            for option in alternatives:
                if option.get("type") == "number":
                    option["type"] = "integer"
                elif option.get("type") == "string":
                    option["pattern"] = (
                        "" if nonnegative else "-?"
                    ) + r"[0-9]{1,28}(?:\.[0-9]{1,8})?"
                    option["pattern"] = "^" + option["pattern"] + "$"
            field["description"] = (
                "Use an exact bounded plain decimal string (at most28 total digits and8 decimal places). Fractional JSON numbers are rejected. Cross-field and total-digit checks run during preparation."
            )
    return schema


def body_for(data: TaxGroupWorkpaperInput, workpaper: TaxGroupStatements):
    calculation = calculate(workpaper)
    issues = list(calculation["issues"])
    if data.operative_changes != "assessed_none":
        issues.append({"code": "OPERATIVE_RULE_CHANGES_UNRESOLVED"})
    body: dict[str, Any] = {
        "workflow": "uae-tax-group-statements",
        "contract": CONTRACT,
        "engine_contract": ENGINE_CONTRACT,
        "title": data.label,
        "parameters": data.model_dump(mode="json"),
        "mapping_fingerprint": fingerprint(workpaper.model_dump(mode="json")),
        "tax_group_totals": [],
        "rows": [],
        **{key: [] for key in COLLECTIONS.values() if key != "rows"},
        "exception_count": len(issues),
        "blocked": bool(issues),
        "review_status": "UNVERIFIED",
        "population_completeness": "DECLARED_MEMBER_PACKAGES_AND_RETAINED_MAPPING_ONLY",
        "statutory_calculation_qualified": False,
        "professional_conclusion": "NOT_DETERMINED",
        "validation": {**calculation["validation"], "ready": False},
        "statutory_issuance": False,
        "source_binding_established": False,
        "limitations": [
            "Draft aggregation workpaper only; an independent workpaper review does not establish a complete statutory reporting pack, audit opinion or filing",
            "Source identities and financial facts are independently declared; byte verification does not authenticate document meaning, Tax Group eligibility or completeness",
            "All retained documents belong to this authorized group engagement; declared member legal-entity identifiers do not authorize access to other engagements",
            "No IFRS10 investment/equity elimination, FX, NCI, acquisition journal or payment is inferred",
            "Prescribed note wording, Arabic/operative-source adoption, leaving-member continuity, clawback treatment, professional audit and submission remain separate requirements",
            "Pre-join loss ceilings remain unresolved review schedules rather than determinations of taxable income",
        ],
    }
    for period_name in ("current", "comparative"):
        period = calculation.get(period_name)
        if period is None:
            continue
        base = {
            "period": period_name,
            "period_start": period["period_start"],
            "period_end": period["period_end"],
        }
        body["tax_group_totals"].append(
            {**base, **period["totals"], "arithmetic_reconciled": period["arithmetic_reconciled"]}
        )
        for statement, lines in period["statements"].items():
            for line in lines:
                row = {
                    **base,
                    "id": f"{period_name}:{statement}:{line['code']}",
                    "statement": statement,
                    **{k: v for k, v in line.items() if k != "source_lines"},
                    "source_line_count": len(line["source_lines"]),
                    "state": "EXCEPTION" if issues else "SUPPORTED",
                    "issues": [],
                }
                body["rows"].append(row)
                body["tax_group_source_lines"] += [
                    {
                        **base,
                        "statement": statement,
                        "code": line["code"],
                        "kind": line["kind"],
                        **source,
                    }
                    for source in line["source_lines"]
                ]
        body["tax_group_members"] += [{**base, **member} for member in period["members"]]
        body["tax_group_adjustments"] += [
            {**base, **adjustment} for adjustment in period["adjustments"]
        ]
        body["tax_group_losses"] += [{**base, **loss} for loss in period["pre_join_loss_schedule"]]
        body["tax_group_notes"] += [
            {**base, "section": key, "text": text} for key, text in period["notes"].items()
        ]
        scoped_checks = [("adjusted_group", None, period["reconciliation_differences"])] + [
            ("source_member", member, checks)
            for member, checks in period["source_member_reconciliation_differences"].items()
        ]
        for scope, member, checks in scoped_checks:
            body["tax_group_checks"] += [
                {
                    **base,
                    "scope": scope,
                    "member": member,
                    "check": check,
                    "difference": difference,
                    "state": "SUPPORTED" if Decimal(difference) == 0 else "EXCEPTION",
                }
                for check, difference in checks.items()
            ]
    body["tax_group_issues"] = issues
    body["row_count"] = len(body["rows"])
    return body


def collection(body, name, period="all", statement="all"):
    values = body.get(COLLECTIONS[name], [])
    return [
        row
        for row in values
        if (period == "all" or row.get("period") == period)
        and (statement == "all" or row.get("statement") == statement)
    ]


def preview(body, *, limit=100):
    """Copy nested collections; never mutate the retained event to make a preview."""
    return {
        **body,
        **{key: body.get(key, [])[:limit] for key in COLLECTIONS.values() if key != "rows"},
    }


async def prepare(db, ctx, eng, data, request_id):
    from sqlalchemy import select

    from app.db.models.platform import FinancialPeriod
    from app.modules.audit_execution.models import AuditRecord
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.lineage.storage import ObjectStore, hash_file

    package, _ = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "Tax Group statements require a UAE engagement")
    for identifier, expected in (
        (data.rule_evidence_version_id, FTA7_SHA256),
        (data.clarification_evidence_version_id, CTP007_SHA256),
    ):
        original, _ = await service.evidence(db, ctx, eng, identifier)
        if original.media_type != "application/pdf" or original.sha256 != expected:
            raise HTTPException(422, "Retain exact original FTA7 and CTP007 PDFs")
    mapping_version, _ = await service.evidence(db, ctx, eng, data.mapping_evidence_version_id)
    if mapping_version.sha256 != data.mapping_sha256:
        raise HTTPException(422, "Retained mapping SHA256 differs from its selected version")

    def verify_and_parse():
        with ObjectStore().local(
            mapping_version.object_key, mapping_version.object_version
        ) as path:
            if path.stat().st_size > 8 * 1024 * 1024 or hash_file(path) != data.mapping_sha256:
                raise ValueError("Retained mapping is unavailable, oversized or changed")
            mapping = parse_mapping(path.read_bytes())
        validate_workpaper(data, mapping)
        return mapping

    try:
        workpaper = await run_in_threadpool(verify_and_parse)
    except (OSError, ValueError, RecursionError, UnicodeError):
        raise HTTPException(
            422,
            "Tax Group retained mapping validation failed; retain valid original bytes and a bounded complete-period statement mapping",
        ) from None
    period = await db.scalar(select(FinancialPeriod).where(FinancialPeriod.id == eng.period_id))
    if not period or (period.start_date, period.end_date) != (
        workpaper.current.period_start,
        workpaper.current.period_end,
    ):
        raise HTTPException(422, "Select the engagement for the exact current Tax Group period")
    documents = role_sources(data)
    for name, source_period in (
        ("current", workpaper.current),
        ("comparative", workpaper.comparative),
    ):
        if source_period:
            documents += [
                (
                    f"{name}:member:{member.member}",
                    member.source_evidence_version_id,
                    member.source_sha256,
                )
                for member in source_period.members
            ]
    contributors = {str(ctx.user_id)}
    try:
        dependencies = await payroll_rule_documents(
            db,
            ctx,
            eng,
            [
                {"source_evidence_version_id": str(identifier), "source_sha256": digest}
                for _, identifier, digest in documents
            ],
            label="Tax Group authority, adoption, mapping and standalone statements",
            contributors=contributors,
            max_documents=204,
        )
        body = await run_in_threadpool(body_for, data, workpaper)
    except (OSError, ValueError):
        raise HTTPException(
            422,
            "Tax Group retained evidence failed original-file integrity or statement mapping controls",
        ) from None
    records = (
        await db.scalars(
            select(AuditRecord).where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eng.id,
                AuditRecord.id.in_({UUID(item["record_id"]) for item in dependencies}),
            )
        )
    ).all()
    dependencies += [
        {"type": "record", "id": str(row.id), "version": row.version} for row in records
    ]
    contributors.update(str(row.created_by) for row in records if row.created_by)
    body["tax_group_document_binding"] = BINDING
    body["source_binding_established"] = True
    body["contributors"] = sorted(contributors)
    body["tax_group_documents"] = [
        {"role": role, "version_id": str(identifier), "sha256": digest}
        for role, identifier, digest in documents
    ]
    return await service.append(db, ctx, eng, "country-workflow", body, dependencies, request_id)

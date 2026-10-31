"""Retained India reporting-scope workpaper, separate from legal qualification."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.country_workflows.india_company_scope_core import (
    CompanyFacts,
    evaluate_company_scope,
)
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "india-company-reporting-scope/1"
SMALL_COMPANY_2022_SHA256 = "bb19f1b28fa3d1fad986a549d2f664ba052de684b7f1539a07f221441ea0fff3"
BINDING = "RETAINED_DOCUMENT_BYTES_VERIFIED"
ROLES = {
    "companies_act",
    "small_company_amendment",
    "caro_order",
    "caro_commencement",
    "ifc_notification",
    "ifc_corrigendum",
    "legal_adoption",
    "company_facts",
}
PINNED = {
    "small_company_amendment": "44faa58ca500e7581e6612dc64baa586474adaf292734a7134c6c857d330a031",
    "caro_commencement": "c057dfd5503ad88049dc0b3ba22818a66721c04237b91550193a159446d8e219",
    "ifc_notification": "0863084c4880e5f418e5ca52e0a608e65523674ff8f8e54f6fb602dff269ea2a",
}


class ScopeDocument(Strict):
    role: Literal[
        "companies_act",
        "small_company_amendment",
        "caro_order",
        "caro_commencement",
        "ifc_notification",
        "ifc_corrigendum",
        "legal_adoption",
        "company_facts",
    ]
    evidence_version_id: UUID
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class IndiaCompanyScopeInput(Strict):
    profile: Literal["india-company-reporting-scope/1"]
    label: str = Field(min_length=1, max_length=200)
    facts: CompanyFacts
    adopted_from: date
    adopted_through: date
    source_chain_status: Literal["unresolved", "independently_assessed"]
    other_operative_changes: Literal["unresolved", "assessed_none"]
    legal_adoption_assessment: str = Field(min_length=10, max_length=4000)
    documents: list[ScopeDocument] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def retained_scope(self):
        if (
            {d.role for d in self.documents} != ROLES
            or len({d.evidence_version_id for d in self.documents}) != 8
            or len({d.sha256 for d in self.documents}) != 8
        ):
            raise ValueError("Retain eight separate originals for every required source role")
        if not (
            self.adopted_from
            <= self.facts.financial_period_start
            <= self.facts.financial_period_end
            <= self.facts.report_date
            <= self.adopted_through
        ):
            raise ValueError(
                "The independently adopted window must cover the period and report date"
            )
        if not self.label.strip() or len(self.legal_adoption_assessment.strip()) < 10:
            raise ValueError("Retain meaningful title and independent source-chain assessment")
        return self


def assess(data: IndiaCompanyScopeInput):
    candidate = evaluate_company_scope(data.facts.model_dump(mode="json"))
    adopted = (
        data.source_chain_status == "independently_assessed"
        and data.other_operative_changes == "assessed_none"
    )
    issues = [f"PENDING_{key.upper()}" for key in candidate["pending_candidates"]]
    if not adopted:
        issues.append("OPERATIVE_LEGAL_ADOPTION_UNRESOLVED")
    row = {
        "id": "IN:company-reporting-scope",
        "entity_reference": data.facts.entity_reference,
        "period_start": data.facts.financial_period_start.isoformat(),
        "period_end": data.facts.financial_period_end.isoformat(),
        "report_date": data.facts.report_date.isoformat(),
        "statement_scope": data.facts.statement_scope,
        **{k: v if adopted else None for k, v in candidate["candidates"].items()},
        "dated_source_candidates": candidate["candidates"],
        "basis": candidate["basis"],
        "issues": issues,
        "exceptions": issues,
        "state": "EXCEPTION" if issues else "SUPPORTED",
    }
    return {
        "workflow": "india-company-reporting-scope",
        "contract": CONTRACT,
        "title": data.label,
        "parameters": data.model_dump(mode="json"),
        "rows": [row],
        "row_count": 1,
        "exception_count": int(bool(issues)),
        "blocked": bool(issues),
        "population_completeness": "ONE_DECLARED_ENTITY_AND_EXACT_ENGAGEMENT_PERIOD",
        "source_authenticity": "THREE_PINNED_ORIGINALS_OTHER_LEGAL_ORIGINALS_INDEPENDENTLY_ASSESSED",
        "statutory_calculation_qualified": False,
        "independent_legal_adoption_verified": False,
        "ready_for_statutory_issue": False,
        "professional_conclusion": "NOT_DETERMINED",
        "review_status": "UNVERIFIED",
        "limitations": [
            "Source-byte integrity and workflow review do not authenticate legal adoption or issue an opinion",
            "Companies Act, CARO order and IFC corrigendum identities require independent assessment; only three Gazette files are pinned",
            "CARO exemption and IFC exemption never establish exemption from the separate Companies Act audit duty",
            "AS/Ind AS, Schedule III, individual CARO clauses, special regimes and authorized issuance remain separate",
            *candidate["reasons"],
        ],
    }


async def prepare(db, ctx, eng, data, request_id):
    from sqlalchemy import select

    from app.db.models.platform import FinancialPeriod
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, _ = await resolved(db, ctx, eng)
    if package.country != "IN":
        raise HTTPException(422, "India company reporting requires an India engagement")
    period = await db.scalar(select(FinancialPeriod).where(FinancialPeriod.id == eng.period_id))
    if not period or (period.start_date, period.end_date) != (
        data.facts.financial_period_start,
        data.facts.financial_period_end,
    ):
        raise HTTPException(422, "Select the engagement for the exact assessed financial period")
    for source in data.documents:
        original, _ = await service.evidence(db, ctx, eng, source.evidence_version_id)
        if source.role not in {"legal_adoption", "company_facts"}:
            if original.media_type != "application/pdf":
                raise HTTPException(422, "Retain legal source originals as PDF documents")
        expected = PINNED.get(source.role)
        if source.role == "small_company_amendment" and date(
            2022, 9, 15
        ) <= data.facts.financial_period_end < date(2025, 12, 1):
            expected = SMALL_COMPANY_2022_SHA256
        if expected and (source.sha256 != expected or original.sha256 != expected):
            raise HTTPException(
                422, "Retain the exact pinned Gazette original for this source role"
            )
    contributors = {str(ctx.user_id)}
    try:
        dependencies = await payroll_rule_documents(
            db,
            ctx,
            eng,
            [
                {
                    "source_evidence_version_id": str(d.evidence_version_id),
                    "source_sha256": d.sha256,
                }
                for d in data.documents
            ],
            label="India company reporting legal originals, adoption and company facts",
            contributors=contributors,
        )
    except (OSError, ValueError):
        raise HTTPException(
            422, "Retained company-scope evidence failed original-byte integrity or is unavailable"
        ) from None
    body = assess(data)
    body["company_scope_document_binding"] = BINDING
    body["contributors"] = sorted(contributors)
    return await service.append(db, ctx, eng, "country-workflow", body, dependencies, request_id)

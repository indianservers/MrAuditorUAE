"""Dated MD84 preparation/maintenance duties over explicitly assessed tax-period facts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.grc.deadlines import CalendarDate
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "uae-ct-audited-statements-md84-2025/2"
CLARIFICATION_SHA256 = "5b8d235dfd5af78789cc8cb96d5f55dbb57fb1df5e2ba5224fc82d6696147dbf"
CLARIFICATION_URL = "https://tax.gov.ae/Datafolder/Files/Pdf/2025/CTP007-Aggregate-Financial-Statements-and-Audit-Requirement-for-Tax-Groups-27-082025-final-for-publishing.pdf"
SOURCE_SHA256 = "1121cdca7e0386dcf93a68a3919ba3f5c42e2521cdaf3c7020c41670dd0afedb"
SOURCE_URL = "https://www.mof.gov.ae/wp-content/uploads/2025/04/Ministerial-Decision-No.-84-of-2025-on-Audited-Financial-Statements.pdf"
Answer = Literal["assessed_yes", "assessed_no", "unassessed"]


class CTAuditDutyInput(Strict):
    profile: Literal["uae-ct-audited-statements-md84-2025/2"]
    label: str = Field(min_length=1, max_length=200)
    registration_reference: str = Field(min_length=1, max_length=120)
    tax_period_start: CalendarDate
    tax_period_end: CalendarDate
    assessed_on: CalendarDate
    adopted_from: CalendarDate
    adopted_through: CalendarDate
    other_rule_changes: Literal["assessed_none", "unresolved"]
    rule_adoption_assessment: str = Field(min_length=10, max_length=2000)
    taxable_person: Answer
    tax_group: Answer
    tax_group_member: Answer
    qualifying_free_zone_person: Answer
    residency: Literal["resident", "non_resident", "unassessed"]
    revenue_basis: Literal["whole_person", "uae_pe_and_nexus", "unassessed"]
    revenue_aed: (
        Annotated[Decimal, Field(ge=0, max_digits=28, decimal_places=2, allow_inf_nan=False)] | None
    )
    currency: Literal["AED"]
    designated_zone_distribution: Answer
    fact_assessment: str = Field(min_length=10, max_length=2000)
    rule_evidence_version_id: UUID
    clarification_evidence_version_id: UUID
    fact_evidence_version_id: UUID
    fact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="before")
    @classmethod
    def decimal_amount(cls, value):
        if isinstance(value, dict) and isinstance(value.get("revenue_aed"), (float, bool)):
            raise ValueError("Use an exact AED revenue string or explicit null, not binary floats")
        return value

    @model_validator(mode="after")
    def period_and_sources(self):
        if (
            not date(2025, 1, 1)
            <= self.tax_period_start
            <= self.tax_period_end
            <= self.assessed_on
            <= date.today()
        ):
            raise ValueError(
                "MD84 requires a completed assessed tax period commencing from 1 January 2025; earlier periods need their separate MD82 source"
            )
        if (
            self.assessed_on < date(2025, 3, 25)
            or not self.adopted_from
            <= self.tax_period_start
            <= self.assessed_on
            <= self.adopted_through
        ):
            raise ValueError(
                "Retain an adopted rule window covering the period and assessment after issuance"
            )
        if len(
            {
                self.rule_evidence_version_id,
                self.clarification_evidence_version_id,
                self.fact_evidence_version_id,
            }
        ) != 3 or self.fact_sha256 in {SOURCE_SHA256, CLARIFICATION_SHA256}:
            raise ValueError("Retain separate MD84, CTP007 and company fact evidence")
        if (
            any(len(v.strip()) < 10 for v in (self.fact_assessment, self.rule_adoption_assessment))
            or not self.registration_reference.strip()
        ):
            raise ValueError("Retain meaningful registration, fact and adopted-source assessments")
        return self


def assess(data):
    def truth(answer):
        return {"assessed_yes": True, "assessed_no": False}.get(answer)

    taxable, group, member, qfzp = map(
        truth,
        (
            data.taxable_person,
            data.tax_group,
            data.tax_group_member,
            data.qualifying_free_zone_person,
        ),
    )
    required = None
    kind = "UNRESOLVED"
    issues = []
    threshold = None
    threshold_basis = "NOT_NEEDED_FOR_SELECTED_BRANCH"
    if member is True and (
        group is True or qfzp is True or taxable is False or data.residency == "non_resident"
    ):
        issues.append("TAX_GROUP_MEMBER_CLASSIFICATION_CONFLICT")
    elif taxable is False and (group is True or qfzp is True):
        issues.append("TAXABLE_PERSON_CLASSIFICATION_CONFLICT")
    elif taxable is False:
        required, kind = False, "OUTSIDE_ASSESSED_TAXABLE_PERSON_SCOPE"
    elif taxable is None:
        issues.append("TAXABLE_PERSON_UNASSESSED")
    elif group is True:
        required, kind = True, "AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS"
        if qfzp is True:
            kind = "TAX_GROUP_AND_QFZP_CLASSIFICATIONS_REQUIRE_REVIEW"
            issues.append("SEPARATE_TAX_GROUP_AND_QFZP_ELIGIBILITY_REVIEW_REQUIRED")
    elif member is True:
        if group is None or qfzp is None or data.residency == "unassessed":
            issues.append("TAX_GROUP_MEMBER_SCOPE_UNASSESSED")
        else:
            required, kind = False, "NO_STANDALONE_CT_AUDIT_DUTY_FOR_ASSESSED_GROUP_MEMBER"
    elif member is None:
        issues.append("TAX_GROUP_MEMBERSHIP_UNASSESSED")
    else:
        if group is None:
            issues.append("TAX_GROUP_STATUS_UNASSESSED")
        if qfzp is True:
            required, kind = True, "AUDITED_FINANCIAL_STATEMENTS"
        else:
            expected = {"resident": "whole_person", "non_resident": "uae_pe_and_nexus"}.get(
                data.residency
            )
            threshold_basis = "UNRESOLVED"
            if expected is None:
                issues.append("RESIDENCY_UNASSESSED_FOR_REVENUE_TEST")
            elif data.revenue_basis != expected:
                issues.append("ASSESSED_REVENUE_BASIS_REQUIRED_FOR_RESIDENCY")
            elif data.revenue_aed is None:
                issues.append("COMPLETE_TAX_PERIOD_AED_REVENUE_MISSING")
            else:
                threshold_basis = expected
                threshold = data.revenue_aed > Decimal("50000000")
            if threshold is True:
                required, kind = True, "AUDITED_FINANCIAL_STATEMENTS"
            elif group is False and qfzp is False and threshold is False:
                required, kind = False, "NO_MD84_AUDIT_DUTY_ON_ASSESSED_FACTS"
            if qfzp is None and threshold is not True:
                issues.append("QUALIFYING_FREE_ZONE_PERSON_STATUS_UNASSESSED")
        if group is None and required:
            kind = "AUDIT_REQUIRED_STATEMENT_TYPE_UNRESOLVED"
    base_required = required
    if any("CONFLICT" in issue or "ELIGIBILITY_REVIEW" in issue for issue in issues):
        required = None
    if data.other_rule_changes != "assessed_none":
        issues.append("OPERATIVE_RULE_CHANGES_UNRESOLVED")
        required = None
    qfzp_procedures = (
        "SEPARATE_AUTHORITY_PROCEDURES_REQUIRE_ASSESSMENT"
        if qfzp and data.designated_zone_distribution == "assessed_yes"
        else "DESIGNATED_DISTRIBUTION_SCOPE_UNASSESSED"
        if qfzp and data.designated_zone_distribution == "unassessed"
        else "NOT_INDICATED_BY_ASSESSED_FACTS"
        if qfzp
        else "QFZP_PROCEDURE_NOT_DETERMINED"
    )
    row = {
        "id": "MD84:assessed-tax-period",
        "registration": data.registration_reference,
        "period_start": data.tax_period_start.isoformat(),
        "period_end": data.tax_period_end.isoformat(),
        "audited_financial_statements_required": required,
        "dated_source_requirement": base_required,
        "statement_type": kind,
        "tax_group_member": member,
        "threshold_aed": "50000000",
        "revenue_aed": str(data.revenue_aed) if data.revenue_aed is not None else None,
        "threshold_basis": threshold_basis,
        "revenue_exceeds_threshold": threshold,
        "additional_qfzp_procedures": qfzp_procedures,
        "tax_group_procedures": "SEPARATE_FTA_FORM_FRAMEWORK_AND_SUBMISSION_REQUIREMENTS"
        if group or member
        else "NOT_DETERMINED",
        "entity_audit_exemption_established": False,
        "state": "SUPPORTED" if required is not None and not issues else "EXCEPTION",
        "issues": issues,
        "exceptions": issues,
    }
    return {
        "workflow": "uae-ct-audit-duty",
        "contract": CONTRACT,
        "title": data.label,
        "parameters": data.model_dump(mode="json"),
        "rows": [row],
        "row_count": 1,
        "exception_count": int(bool(issues) or required is None),
        "population_completeness": "DECLARED_TAX_PERIOD_AND_RETAINED_ENTITY_FACTS_ONLY",
        "statutory_calculation_qualified": False,
        "professional_conclusion": "NOT_DETERMINED",
        "review_status": "UNVERIFIED",
        "source_sha256": SOURCE_SHA256,
        "source_url": SOURCE_URL,
        "clarification_sha256": CLARIFICATION_SHA256,
        "clarification_url": CLARIFICATION_URL,
        "limitations": [
            "Tax-period validity and completeness are assessed facts; calendar-date validation does not establish a legally valid tax period",
            "Dated MD84 preparation/maintenance duty only, not a company-law or free-zone audit exemption or a complete reporting pack",
            "Taxable-person, Tax Group, QFZP, residency and revenue classifications are independently assessed inputs, not eligibility determinations",
            "Group-member status means approved membership for the entire assessed tax period; partial-period membership or joining/leaving requires a separate assessment",
            "CTP007 page 12 distinguishes the Tax Group audit from standalone member audits regardless of member revenue; other entity audit duties remain separate",
            "Tax Group special-purpose forms, aggregation framework, audit and submission procedures require their separate authority sources; no deadline is inferred here",
            "Designated-zone distribution may require additional prescribed procedures; their applicability and completion are outside this duty assessment",
            "No audit work, opinion, certificate, statutory issuance or government filing is executed or established",
        ],
    }


async def prepare(db, ctx, eng, data, request_id):
    from sqlalchemy import select

    from app.db.models.platform import FinancialPeriod
    from app.modules.country_workflows.service import payroll_rule_documents
    from app.modules.intelligence import service
    from app.modules.jurisdictions.workspace import resolved

    package, _ = await resolved(db, ctx, eng)
    if package.country != "AE":
        raise HTTPException(422, "MD84 audit-duty assessment requires a UAE engagement")
    period = await db.scalar(select(FinancialPeriod).where(FinancialPeriod.id == eng.period_id))
    if (
        not period
        or not period.start_date <= data.tax_period_start <= data.tax_period_end <= period.end_date
    ):
        raise HTTPException(422, "The assessed tax period must be covered by the engagement period")
    rule, _ = await service.evidence(db, ctx, eng, data.rule_evidence_version_id)
    if rule.media_type != "application/pdf" or rule.sha256 != SOURCE_SHA256:
        raise HTTPException(
            422, "Retain the exact original adopted MD84 PDF, not a recreated rule summary"
        )
    clarification, _ = await service.evidence(db, ctx, eng, data.clarification_evidence_version_id)
    if (
        clarification.media_type != "application/pdf"
        or clarification.sha256 != CLARIFICATION_SHA256
    ):
        raise HTTPException(422, "Retain the exact original adopted CTP007 PDF")
    contributors = {str(ctx.user_id)}
    dependencies = await payroll_rule_documents(
        db,
        ctx,
        eng,
        [
            {
                "source_evidence_version_id": str(data.rule_evidence_version_id),
                "source_sha256": SOURCE_SHA256,
            },
            {
                "source_evidence_version_id": str(data.clarification_evidence_version_id),
                "source_sha256": CLARIFICATION_SHA256,
            },
            {
                "source_evidence_version_id": str(data.fact_evidence_version_id),
                "source_sha256": data.fact_sha256,
            },
        ],
        label="MD84 rule and assessed company facts",
        contributors=contributors,
    )
    body = assess(data)
    body["ct_audit_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
    body["contributors"] = sorted(contributors)
    return await service.append(db, ctx, eng, "country-workflow", body, dependencies, request_id)

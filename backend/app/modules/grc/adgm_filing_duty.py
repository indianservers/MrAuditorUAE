"""Three-valued ADGM filing-duty checks over retained, independently assessed facts."""

import uuid
from typing import Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict
from app.modules.grc.deadlines import CalendarDate

PROFILE = "adgm-company-accounts-cr20260626-guidance20261014/2"
Criterion = Literal[
    "restricted_scope_company",
    "registrar_notice_applies",
    "non_registrable_publication_trigger",
    "unlimited_company",
    "limited_parent_at_any_time",
    "limited_joint_control_at_any_time",
    "parent_of_limited_at_any_time",
    "financial_institution_or_parent_group",
    "all_members_limited_or_qualifying_unlimited",
    "dormant_subsidiary_exemption_claimed",
    "subsidiary_undertaking",
    "dormant_whole_financial_year",
    "public_interest_entity_any_time",
    "financial_institution_any_time",
    "all_members_agree_for_year",
    "guarantee_authenticated",
    "guarantee_parent_identity_complete",
    "guarantee_subsidiary_identity_matches",
    "guarantee_statement_dated",
    "guarantee_financial_year_matches",
    "guarantee_all_outstanding_liabilities_covered",
    "included_in_parent_ifrs_accounts",
    "parent_notes_disclose_exemption",
    "members_agreement_notice_delivered",
    "guarantee_statement_delivered",
    "parent_consolidated_accounts_delivered",
    "parent_auditor_report_delivered",
    "parent_consolidated_annual_report_delivered",
    "support_delivery_within_filing_period_assessed",
]
UNLIMITED_EXCLUSIONS = (
    "limited_parent_at_any_time",
    "limited_joint_control_at_any_time",
    "parent_of_limited_at_any_time",
    "financial_institution_or_parent_group",
    "all_members_limited_or_qualifying_unlimited",
)
DORMANT_CONDITIONS = {
    "subsidiary_undertaking": True,
    "dormant_whole_financial_year": True,
    "public_interest_entity_any_time": False,
    "financial_institution_any_time": False,
    "all_members_agree_for_year": True,
    "guarantee_authenticated": True,
    "guarantee_parent_identity_complete": True,
    "guarantee_subsidiary_identity_matches": True,
    "guarantee_statement_dated": True,
    "guarantee_financial_year_matches": True,
    "guarantee_all_outstanding_liabilities_covered": True,
    "included_in_parent_ifrs_accounts": True,
    "parent_notes_disclose_exemption": True,
}
SUPPORT_DOCUMENTS = {
    "members_agreement_notice_delivered": "Written notice of the members' agreement",
    "guarantee_statement_delivered": "Authenticated parent guarantee statement under section 425",
    "parent_consolidated_accounts_delivered": "Parent consolidated accounts",
    "parent_auditor_report_delivered": "Auditor's report on the parent consolidated accounts",
    "parent_consolidated_annual_report_delivered": "Parent consolidated annual report",
}


class FilingDutyFact(Strict):
    key: Criterion
    answer: Literal["assessed_yes", "assessed_no", "unassessed"]
    evidence_ids: list[uuid.UUID] = Field(max_length=10)
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def retained(self):
        if len(self.assessment.strip()) < 10 or len(set(self.evidence_ids)) != len(
            self.evidence_ids
        ):
            raise ValueError("Retain a meaningful duty fact assessment and distinct source links")
        if self.answer != "unassessed" and not self.evidence_ids:
            raise ValueError("Positive and negative filing-duty facts require original evidence")
        return self


class FilingDutyChecks(Strict):
    accounts_period_start: CalendarDate
    accounts_period_end: CalendarDate
    reference_period_start: CalendarDate
    reference_period_end: CalendarDate
    facts: list[FilingDutyFact] = Field(min_length=1, max_length=29)

    @model_validator(mode="after")
    def distinct(self):
        if (
            self.accounts_period_end < self.accounts_period_start
            or self.reference_period_end < self.reference_period_start
            or len({fact.key for fact in self.facts}) != len(self.facts)
        ):
            raise ValueError("Filing-duty facts require ordered periods and distinct criteria")
        return self


def conjunction(values):
    """A known failed condition disproves an exemption; missing is never a negative fact."""
    if False in values:
        return False
    return None if None in values else True


def disjunction(values):
    if True in values:
        return True
    return None if None in values else False


def assess(checks, procedure, *, company_scope_established):
    facts = {fact.key: fact for fact in checks.facts}
    used = set()

    def fact(key):
        used.add(key)
        value = facts.get(key)
        return {"assessed_yes": True, "assessed_no": False}.get(value.answer) if value else None

    restricted = fact("restricted_scope_company") if company_scope_established else None
    chapter_applies = True if restricted is False else None
    if restricted is True:
        trigger = disjunction(
            [fact("registrar_notice_applies"), fact("non_registrable_publication_trigger")]
        )
        chapter_applies = trigger

    unlimited_exempt = dormant_exempt = supporting_required = None
    reason = (
        "CHAPTER_8_APPLICABILITY_UNRESOLVED"
        if company_scope_established
        else "ADGM_COMPANY_SCOPE_NOT_ESTABLISHED"
    )
    required = None
    issues = []
    if chapter_applies is False:
        required = False
        supporting_required = False
        reason = "RESTRICTED_SCOPE_WITHOUT_ASSESSED_NOTICE_OR_PUBLICATION_TRIGGER"
    elif chapter_applies is True:
        unlimited = fact("unlimited_company")
        unlimited_exempt = False if unlimited is False else None
        if unlimited is True:
            unlimited_exempt = conjunction(
                [
                    None if (value := fact(key)) is None else not value
                    for key in UNLIMITED_EXCLUSIONS
                ]
            )
        claim = fact("dormant_subsidiary_exemption_claimed")
        dormant_exempt = False if claim is False else None
        supporting_required = False if claim is False else None
        if claim is True:
            eligibility = conjunction(
                [
                    None if (value := fact(key)) is None else value == expected
                    for key, expected in DORMANT_CONDITIONS.items()
                ]
            )
            supporting_required = True if eligibility is True else None
            if eligibility is False:
                dormant_exempt = False
                issues.append("DORMANT_SUBSIDIARY_CLAIM_CONTRADICTS_ASSESSED_CONDITIONS")
            elif eligibility is True:
                dormant_exempt = conjunction(
                    [fact(key) for key in SUPPORT_DOCUMENTS]
                    + [fact("support_delivery_within_filing_period_assessed")]
                )
        exempt = disjunction([unlimited_exempt, dormant_exempt])
        if procedure == "dormant_subsidiary_supporting_documents":
            required = supporting_required
            reason = (
                "DORMANT_SUPPORT_DOCUMENT_FILING_DUTY"
                if required
                else "DORMANT_SUPPORT_DOCUMENT_SCOPE_UNRESOLVED"
                if required is None
                else "NO_DORMANT_SUBSIDIARY_CLAIM"
            )
        else:
            required = None if exempt is None else not exempt
            reason = (
                "UNLIMITED_COMPANY_SECTION_422_EXEMPTION"
                if unlimited_exempt is True
                else "DORMANT_SUBSIDIARY_INDIVIDUAL_ACCOUNTS_EXEMPTION"
                if dormant_exempt is True
                else "INDIVIDUAL_ACCOUNTS_FILING_REQUIRED"
                if required is True
                else "INDIVIDUAL_ACCOUNTS_EXEMPTION_UNRESOLVED"
            )
    if required is None:
        issues.append("FILING_DUTY_CONDITIONS_INCOMPLETE")
    missing = sorted(key for key in used if key not in facts or facts[key].answer == "unassessed")
    # Display only relevant criteria as missing. All supplied facts remain bound to original sources.
    return {
        "procedure": procedure,
        "filing_required": required,
        "chapter_8_applies": chapter_applies,
        "unlimited_company_exemption": unlimited_exempt,
        "dormant_individual_accounts_exemption": dormant_exempt,
        "supporting_documents_required": supporting_required,
        "reason": reason,
        "issues": issues,
        "missing_criteria": missing,
        "checks": [
            {
                "key": key,
                "answer": facts[key].answer if key in facts else "unassessed",
                "evidence_ids": [str(identifier) for identifier in facts[key].evidence_ids]
                if key in facts
                else [],
                "assessment": facts[key].assessment
                if key in facts
                else "Retain an independent assessment for this criterion",
            }
            for key in sorted(used)
        ],
        "supporting_documents": [
            {
                "key": key,
                "title": title,
                "delivery_assessment": facts[key].answer if key in facts else "unassessed",
            }
            for key, title in SUPPORT_DOCUMENTS.items()
        ]
        if supporting_required
        else [],
        "limitations": "Conditions are independently assessed inputs, not registry/guarantee authentication or proof of external delivery. Individual-accounts exemption does not waive supporting filings, group accounts, audit, tax or other authority duties. Timely delivery requires separately assessed original evidence; no filing or deadline is inferred from a missing receipt.",
    }


def validate_binding(data):
    scope = data.adgm_accounts_scope
    checks = scope.filing_duty_checks
    if checks is None:
        return
    if (
        checks.accounts_period_start != data.obligation_period_start
        or checks.accounts_period_end != data.obligation_period_end
        or checks.reference_period_start != scope.accounting_reference_start
        or checks.reference_period_end != scope.accounting_reference_end
    ):
        raise ValueError(
            "ADGM filing-duty checks must match the exact accounts and reference periods"
        )
    allowed = set(data.fact_evidence_ids)
    if any(not set(fact.evidence_ids) <= allowed for fact in checks.facts):
        raise ValueError(
            "Every filing-duty fact source must be a separately retained company-fact evidence link"
        )
    result = assess(
        checks,
        scope.filing_procedure,
        company_scope_established=scope.registration == "assessed_yes"
        and scope.legal_form == "company",
    )
    expected = (
        "unassessed"
        if result["filing_required"] is None
        else "assessed_required"
        if result["filing_required"]
        else "assessed_exempt"
    )
    if scope.filing_duty != expected:
        raise ValueError(
            "Declared ADGM filing duty contradicts the retained structured condition assessment"
        )

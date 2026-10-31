"""CCL accounts procedures over separately retained legal adoption and company facts."""

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, model_validator

from app.modules.grc.deadlines import CalendarDate
from app.modules.jurisdictions.profiles import Strict

CONTRACT = "uae-ccl-accounts-articles26-27/1"
LAW_SHA256 = "b08a904a9af7102804e96e70c77a975876f3f2705190ecb6bea4f39d533435af"
AMENDMENT_SHA256 = "7e035b6c3616255ffe8f1c4326080bec3f270f165aa63eeb06ab4c1f481e7163"
Answer = Literal["assessed_yes", "assessed_no", "unassessed"]


class CompanyAccountsInput(Strict):
    profile: Literal["uae-ccl-accounts-articles26-27/1"]
    label: str = Field(min_length=1, max_length=200)
    registration_reference: str = Field(min_length=1, max_length=120)
    fiscal_year_start: CalendarDate
    fiscal_year_end: CalendarDate
    assessed_on: CalendarDate
    adopted_from: CalendarDate
    adopted_through: CalendarDate
    amendment_publication_date: CalendarDate | None
    rule_chain_status: Literal["assessed_adopted", "unresolved"]
    other_rule_changes: Literal["assessed_none", "unresolved"]
    rule_adoption_assessment: str = Field(min_length=10, max_length=4000)
    law_scope: Literal["assessed_applies", "assessed_excluded", "unresolved"]
    scope_assessment: str = Field(min_length=10, max_length=4000)
    fiscal_year_validity: Literal["assessed_valid", "unassessed"]
    legal_form: Literal[
        "limited_liability",
        "public_joint_stock",
        "private_joint_stock",
        "general_partnership",
        "limited_partnership",
        "unassessed",
    ]
    holding_company: Answer
    request_population: Literal["assessed_none", "written_request", "unassessed"]
    requester_eligibility: Literal[
        "assessed_partner_or_shareholder", "assessed_other", "unassessed"
    ]
    request_received_on: CalendarDate | None
    selected_year_is_last_audited: Answer
    response_counting: Literal["assessed_calendar_days_excluding_receipt", "unassessed"]
    counting_assessment: str = Field(max_length=4000)
    response_status: Literal["assessed_responded", "assessed_not_responded", "unassessed"]
    responded_on: CalendarDate | None
    accounts_copy_delivered: Answer
    auditor_report_copy_delivered: Answer
    group_accounts_copy_delivered: Answer
    fact_assessment: str = Field(min_length=10, max_length=4000)
    law_evidence_version_id: UUID
    amendment_evidence_version_id: UUID
    adoption_evidence_version_id: UUID
    adoption_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fact_evidence_version_id: UUID
    fact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def dates_and_documents(self):
        if (
            not date(2022, 1, 2)
            <= self.fiscal_year_start
            <= self.fiscal_year_end
            <= self.assessed_on
            <= date.today()
        ):
            raise ValueError(
                "Retain a completed fiscal year commencing from 2 January 2022 and a nonfuture assessment"
            )
        if (
            self.assessed_on < date(2025, 10, 1)
            or not self.adopted_from
            <= self.fiscal_year_start
            <= self.assessed_on
            <= self.adopted_through
        ):
            raise ValueError(
                "The adopted source-chain window must cover the fiscal year and assessment after amendment issuance"
            )
        if (
            self.amendment_publication_date is not None
            and not date(2025, 10, 1) <= self.amendment_publication_date <= self.assessed_on
        ):
            raise ValueError(
                "Declared amendment publication must be after issuance and no later than assessment"
            )
        if self.request_population == "written_request":
            if (
                self.request_received_on is None
                or not self.fiscal_year_end <= self.request_received_on <= self.assessed_on
            ):
                raise ValueError(
                    "Retain the written request date after the selected fiscal year and no later than assessment"
                )
            if self.response_status == "assessed_responded" and self.responded_on is None:
                raise ValueError("An assessed response requires its retained date")
            if self.response_status == "assessed_not_responded" and self.responded_on is not None:
                raise ValueError("A date cannot accompany an assessed absence of response")
        elif self.request_received_on is not None or self.responded_on is not None:
            raise ValueError(
                "Request/response dates require an explicitly selected written-request population"
            )
        if self.responded_on is not None and (
            self.request_received_on is None
            or not self.request_received_on <= self.responded_on <= self.assessed_on
        ):
            raise ValueError(
                "Response date must follow the retained request and not exceed assessment"
            )
        if self.response_counting != "unassessed" and len(self.counting_assessment.strip()) < 10:
            raise ValueError("Retain the independently adopted day-counting assessment")
        if (
            self.request_received_on is not None
            and self.response_counting != "unassessed"
            and self.request_received_on + timedelta(days=10) > self.adopted_through
        ):
            raise ValueError(
                "The adopted source window must cover the full assessed response period"
            )
        versions = [
            self.law_evidence_version_id,
            self.amendment_evidence_version_id,
            self.adoption_evidence_version_id,
            self.fact_evidence_version_id,
        ]
        hashes = [LAW_SHA256, AMENDMENT_SHA256, self.adoption_sha256, self.fact_sha256]
        if len(set(versions)) != 4 or len(set(hashes)) != 4:
            raise ValueError(
                "Original law, amendment, legal adoption and company facts must be separate original documents"
            )
        if (
            not self.label.strip()
            or not self.registration_reference.strip()
            or any(
                len(text.strip()) < 10
                for text in [
                    self.rule_adoption_assessment,
                    self.scope_assessment,
                    self.fact_assessment,
                ]
            )
        ):
            raise ValueError(
                "Retain meaningful label, registration, legal-adoption, scope and fact assessments"
            )
        return self


def response_assessment(data, scope, issues):
    result: dict[str, object] = {
        "response_required": None,
        "response_deadline": None,
        "response_complete": None,
        "response_timing": "UNRESOLVED",
        "group_accounts_copy_required": None,
    }
    if scope is False or data.request_population == "assessed_none":
        result.update(response_required=False, response_timing="OUTSIDE_ASSESSED_REQUEST_SCOPE")
        return result
    if scope is None:
        return result
    if data.request_population == "unassessed":
        issues.append("REQUEST_POPULATION_UNASSESSED")
        return result
    if data.requester_eligibility == "assessed_other":
        result.update(response_required=False, response_timing="OUTSIDE_ASSESSED_REQUEST_SCOPE")
        return result
    if data.requester_eligibility == "unassessed":
        issues.append("REQUESTER_ELIGIBILITY_UNASSESSED")
        return result
    result["response_required"] = True
    if data.selected_year_is_last_audited != "assessed_yes":
        issues.append("SELECTED_YEAR_NOT_ESTABLISHED_AS_LAST_AUDITED")
    holding = {"assessed_yes": True, "assessed_no": False}.get(data.holding_company)
    result["group_accounts_copy_required"] = holding
    if holding is None:
        issues.append("HOLDING_COMPANY_STATUS_UNASSESSED")
    deadline = None
    if data.response_counting == "assessed_calendar_days_excluding_receipt":
        deadline = data.request_received_on + timedelta(days=10)
        result["response_deadline"] = deadline.isoformat()
    else:
        issues.append("REQUEST_DAY_COUNTING_UNASSESSED")
    if data.response_status == "unassessed":
        issues.append("RESPONSE_STATUS_UNASSESSED")
        return result
    if data.response_status == "assessed_not_responded":
        if any(
            value == "assessed_yes"
            for value in [
                data.accounts_copy_delivered,
                data.auditor_report_copy_delivered,
                data.group_accounts_copy_delivered,
            ]
        ):
            issues.append("RESPONSE_DELIVERY_FACTS_CONFLICT")
            return result
        result["response_complete"] = False
        if deadline:
            result["response_timing"] = (
                "OVERDUE"
                if data.assessed_on > deadline
                else "DUE_ON_ASSESSED_DATE"
                if data.assessed_on == deadline
                else "NOT_YET_DUE"
            )
            if data.assessed_on > deadline:
                issues.append("REQUEST_RESPONSE_OVERDUE")
        return result
    copies = [data.accounts_copy_delivered, data.auditor_report_copy_delivered]
    if holding:
        copies.append(data.group_accounts_copy_delivered)
    complete = (
        all(answer == "assessed_yes" for answer in copies)
        and holding is not None
        and data.selected_year_is_last_audited == "assessed_yes"
    )
    result["response_complete"] = complete if "assessed_no" in copies or complete else None
    if not complete:
        issues.append("REQUIRED_RESPONSE_COPIES_NOT_ESTABLISHED")
    if deadline:
        result["response_timing"] = (
            "RESPONDED_LATE" if data.responded_on > deadline else "RESPONDED_WITHIN_ASSESSED_PERIOD"
        )
        if data.responded_on > deadline:
            issues.append("REQUEST_RESPONSE_LATE")
    return result


def assess(data):
    issues = []
    scope = {"assessed_applies": True, "assessed_excluded": False}.get(data.law_scope)
    if scope is None:
        issues.append("COMPANY_LAW_APPLICABILITY_UNRESOLVED")
    annual = scope
    audit = scope
    if scope:
        if data.fiscal_year_validity != "assessed_valid":
            annual = audit = None
            issues.append("FISCAL_YEAR_VALIDITY_UNASSESSED")
        elif data.legal_form == "unassessed":
            audit = None
            issues.append("LEGAL_FORM_UNASSESSED")
        else:
            audit = data.legal_form in {
                "limited_liability",
                "public_joint_stock",
                "private_joint_stock",
            }
    requirements = {
        "accounting_registers_required": scope,
        "annual_accounts_required": annual,
        "annual_audit_required": audit,
        "international_accounting_basis_required": annual,
        "minimum_register_retention_years": 5 if scope else None,
    }
    response = response_assessment(data, scope, issues)
    chain_unresolved = (
        data.rule_chain_status != "assessed_adopted"
        or data.other_rule_changes != "assessed_none"
        or data.amendment_publication_date is None
    )
    if data.rule_chain_status != "assessed_adopted":
        issues.append("OPERATIVE_SOURCE_CHAIN_UNRESOLVED")
    if data.other_rule_changes != "assessed_none":
        issues.append("OTHER_OPERATIVE_RULE_CHANGES_UNRESOLVED")
    if data.amendment_publication_date is None:
        issues.append("AMENDMENT_PUBLICATION_NOT_ESTABLISHED")
    row = {
        "id": "CCL:assessed-fiscal-year",
        "registration": data.registration_reference,
        "period_start": data.fiscal_year_start.isoformat(),
        "period_end": data.fiscal_year_end.isoformat(),
        "legal_form": data.legal_form,
        **{key: None if chain_unresolved else value for key, value in requirements.items()},
        **{key: None if chain_unresolved else value for key, value in response.items()},
        "dated_source_requirements": requirements,
        "dated_source_request_assessment": response,
        "amendment_commencement_from_declared_publication": (
            data.amendment_publication_date + timedelta(days=1)
        ).isoformat()
        if data.amendment_publication_date
        else None,
        "entity_audit_exemption_established": False,
        "issues": issues,
        "exceptions": issues,
        "state": "EXCEPTION" if issues or chain_unresolved else "SUPPORTED",
    }
    return {
        "workflow": "uae-company-accounts-duty",
        "contract": CONTRACT,
        "title": data.label,
        "parameters": data.model_dump(mode="json"),
        "rows": [row],
        "row_count": 1,
        "exception_count": int(bool(issues) or chain_unresolved),
        "population_completeness": "ONE_DECLARED_FISCAL_YEAR_AND_EXPLICIT_REQUEST_POPULATION",
        "source_sha256": [LAW_SHA256, AMENDMENT_SHA256],
        "source_url": "https://www.moet.gov.ae/en/laws",
        "english_source_is_unofficial_translation": True,
        "statutory_calculation_qualified": False,
        "professional_conclusion": "NOT_DETERMINED",
        "review_status": "UNVERIFIED",
        "limitations": [
            "Original Ministry-hosted English PDF is marked unofficial translation; the source chain, publication and later changes require separate retained engagement-specific adoption",
            "Applicability including Articles3–5, exclusions, legal form, last-audited-year scope and delivery are independently assessed facts, not registry authentication",
            "Fiscal-year dates are bound to the engagement; this does not establish Article28 first/subsequent-year validity",
            "Article27 audit duty is separate from corporate-tax thresholds and free-zone/special-law procedures; no general audit exemption is established",
            "A ten-day response candidate uses an explicitly adopted calendar-day/excluded-receipt interpretation only; legal counting and delivery are not authenticated",
            "Minimum five-year register retention is not permission to destroy records or a complete retention-policy assessment",
            "No accounts are prepared, audit performed, opinion issued or government filing executed by this duty assessment",
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
        raise HTTPException(422, "CCL accounts assessment requires a UAE engagement")
    period = await db.scalar(select(FinancialPeriod).where(FinancialPeriod.id == eng.period_id))
    if not period or (period.start_date, period.end_date) != (
        data.fiscal_year_start,
        data.fiscal_year_end,
    ):
        raise HTTPException(422, "Select the engagement for the exact assessed fiscal year")
    for version, expected in [
        (data.law_evidence_version_id, LAW_SHA256),
        (data.amendment_evidence_version_id, AMENDMENT_SHA256),
    ]:
        original, _ = await service.evidence(db, ctx, eng, version)
        if original.media_type != "application/pdf" or original.sha256 != expected:
            raise HTTPException(
                422,
                "Retain the exact original Ministry-hosted law and amendment PDFs; recreated summaries are not accepted",
            )
    contributors = {str(ctx.user_id)}
    documents = [
        (data.law_evidence_version_id, LAW_SHA256),
        (data.amendment_evidence_version_id, AMENDMENT_SHA256),
        (data.adoption_evidence_version_id, data.adoption_sha256),
        (data.fact_evidence_version_id, data.fact_sha256),
    ]
    try:
        dependencies = await payroll_rule_documents(
            db,
            ctx,
            eng,
            [
                {"source_evidence_version_id": str(version), "source_sha256": digest}
                for version, digest in documents
            ],
            label="CCL originals, legal adoption and assessed company facts",
            contributors=contributors,
        )
    except (OSError, ValueError):
        raise HTTPException(
            422, "Retained company-law evidence failed original-file integrity or is unavailable"
        ) from None
    body = assess(data)
    body["company_accounts_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
    body["contributors"] = sorted(contributors)
    return await service.append(db, ctx, eng, "country-workflow", body, dependencies, request_id)

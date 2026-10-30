"""Source-pinned ADGM company filing timetables over explicitly assessed facts."""

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from app.modules.audit_execution.schemas import Strict
from app.modules.grc.adgm_filing_duty import PROFILE as DUTY_PROFILE
from app.modules.grc.adgm_filing_duty import FilingDutyChecks
from app.modules.grc.deadlines import CalendarDate, calendar_offset, candidates

PROFILE = "adgm-company-accounts-cr20260626-guidance20261014/1"
REGULATIONS_SHA256 = "8aae2ffcfa9cdc927894ad82e41e08e3eba235092c63d4a64a3349e0268249f0"
GUIDANCE_SHA256 = "aa34c1cf43afd0b4a281750f072b55bf177f48ed361f86bb6c614bf9204745af"


class ADGMAccountsScope(Strict):
    profile: Literal[
        "adgm-company-accounts-cr20260626-guidance20261014/1",
        "adgm-company-accounts-cr20260626-guidance20261014/2",
    ]
    registration: Literal["assessed_yes", "assessed_no", "unassessed"]
    legal_form: Literal["company", "llp", "foundation", "branch", "unassessed"]
    company_status_at_reference_end: Literal["private", "public", "unassessed"]
    filing_duty: Literal["assessed_required", "assessed_exempt", "unassessed"]
    duty_basis: str = Field(min_length=10, max_length=4000)
    accounting_reference_start: CalendarDate
    accounting_reference_end: CalendarDate
    incorporation_date: CalendarDate | None = None
    period_classification: Literal["subsequent", "first_standard", "first_long", "unassessed"]
    first_anniversary: CalendarDate | None = None
    period_validity: Literal["assessed_valid", "unresolved"]
    shortened_period: Literal["assessed_yes", "assessed_no", "unassessed"]
    shortening_notice_date: CalendarDate | None = None
    shortening_receipt_date: CalendarDate | None = None
    other_authority_modifications: Literal["assessed_none", "unresolved"]
    operative_from: CalendarDate
    operative_through: CalendarDate
    assessed_on: CalendarDate
    assessment: str = Field(min_length=10, max_length=4000)
    extension_applied_at: AwareDatetime | None = None
    filing_procedure: (
        Literal["individual_accounts", "dormant_subsidiary_supporting_documents"] | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    filing_duty_checks: FilingDutyChecks | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def facts(self):
        if self.profile == DUTY_PROFILE:
            if self.filing_procedure is None or self.filing_duty_checks is None:
                raise ValueError(
                    "ADGM filing-duty profile v2 requires an explicit procedure and structured condition assessment"
                )
        elif self.filing_procedure is not None or self.filing_duty_checks is not None:
            raise ValueError("Structured filing-duty checks require the explicit ADGM v2 profile")
        if self.accounting_reference_end < self.accounting_reference_start:
            raise ValueError("Retain an ordered ADGM accounting reference period")
        if self.operative_through < self.operative_from or any(
            len(value.strip()) < 10 for value in (self.assessment, self.duty_basis)
        ):
            raise ValueError(
                "Retain meaningful ADGM assessments and an ordered adopted rule window"
            )
        if self.period_classification == "subsequent" and self.first_anniversary is not None:
            raise ValueError("A subsequent ADGM period cannot retain a first-period anniversary")
        if self.shortened_period == "assessed_no" and (
            self.shortening_notice_date is not None or self.shortening_receipt_date is not None
        ):
            raise ValueError("A non-shortened ADGM period cannot retain shortening notice dates")
        return self


def expected_candidates(scope):
    """The reference period, not the potentially different accounts date, drives s416."""
    if (
        scope.company_status_at_reference_end == "unassessed"
        or scope.period_classification == "unassessed"
    ):
        return []
    months = 9 if scope.company_status_at_reference_end == "private" else 6
    if scope.period_classification == "first_long":
        if scope.first_anniversary is None:
            return []
        result = [(scope.first_anniversary, months), (scope.accounting_reference_end, 3)]
    else:
        result = [(scope.accounting_reference_end, months)]
    if scope.shortened_period == "assessed_yes":
        if scope.shortening_notice_date is None:
            return []
        result.append((scope.shortening_notice_date, 3))
    return result


def assess(data):
    scope = data.adgm_accounts_scope
    if scope is None:
        return None
    issues = []
    required = {"assessed_required": True, "assessed_exempt": False}.get(scope.filing_duty)
    duty = None
    if scope.filing_duty_checks is not None:
        from app.modules.grc.adgm_filing_duty import assess as assess_duty

        duty = assess_duty(
            scope.filing_duty_checks,
            scope.filing_procedure,
            company_scope_established=scope.registration == "assessed_yes"
            and scope.legal_form == "company",
        )
        required = duty["filing_required"]
        issues.extend(duty["issues"])
    if scope.registration != "assessed_yes":
        required = None
        issues.append("ADGM_COMPANY_REGISTRATION_NOT_ESTABLISHED")
    if scope.legal_form != "company":
        required = None
        issues.append("SEPARATE_LEGAL_FORM_REGULATIONS_REQUIRED")
    if required is None:
        issues.append("SECTION_415_FILING_DUTY_AND_EXCEPTIONS_REQUIRE_ASSESSMENT")
    if scope.assessed_on < date(2026, 10, 14):
        issues.append("JOINT_SOURCE_PROFILE_NOT_AVAILABLE_AT_ASSESSMENT_DATE")
    if (
        not scope.operative_from
        <= scope.accounting_reference_end
        <= scope.assessed_on
        <= scope.operative_through
    ):
        issues.append("ADOPTED_WINDOW_MUST_COVER_REFERENCE_END_AND_ASSESSMENT")
    if scope.other_authority_modifications != "assessed_none":
        issues.append("OTHER_AUTHORITY_MODIFICATIONS_UNRESOLVED")
    if required:
        if any(
            abs((actual - reference).days) > 7
            for actual, reference in (
                (data.obligation_period_start, scope.accounting_reference_start),
                (data.obligation_period_end, scope.accounting_reference_end),
            )
        ):
            issues.append("ACCOUNTS_PERIOD_AND_REFERENCE_PERIOD_MAPPING_REQUIRE_ASSESSMENT")
        if scope.company_status_at_reference_end == "unassessed":
            issues.append("COMPANY_STATUS_IMMEDIATELY_BEFORE_REFERENCE_END_UNASSESSED")
        if scope.period_classification == "unassessed" or scope.period_validity != "assessed_valid":
            issues.append("ACCOUNTING_REFERENCE_PERIOD_CLASSIFICATION_UNRESOLVED")
        incorporation = scope.incorporation_date
        if incorporation is None or incorporation > scope.accounting_reference_start:
            issues.append("INCORPORATION_AND_REFERENCE_PERIOD_FACTS_REQUIRE_ASSESSMENT")
        elif scope.period_classification.startswith("first_"):
            anniversary = calendar_offset(incorporation, 12, 0)
            if (
                scope.accounting_reference_start != incorporation
                or data.obligation_period_start != incorporation
                or scope.first_anniversary != anniversary
                or not calendar_offset(incorporation, 6, 0)
                <= scope.accounting_reference_end
                < calendar_offset(incorporation, 18, 0)
                or (scope.period_classification == "first_long")
                != (scope.accounting_reference_end >= anniversary)
            ):
                issues.append("FIRST_PERIOD_DATES_LENGTH_AND_ANNIVERSARY_REQUIRE_ASSESSMENT")
            if (incorporation.month, incorporation.day) == (2, 29):
                issues.append("LEAP_DAY_INCORPORATION_ANNIVERSARY_REQUIRES_SEPARATE_QUALIFICATION")
        elif (
            scope.period_classification == "subsequent"
            and scope.accounting_reference_start <= incorporation
        ):
            issues.append("SUBSEQUENT_PERIOD_CANNOT_START_AT_INCORPORATION")
        if scope.shortened_period == "unassessed":
            issues.append("SHORTENING_NOTICE_APPLICABILITY_UNASSESSED")
        elif scope.shortened_period == "assessed_yes":
            if (
                scope.shortening_notice_date is None
                or scope.shortening_receipt_date is None
                or scope.shortening_notice_date != scope.shortening_receipt_date
                or not scope.incorporation_date
                or not scope.incorporation_date <= scope.shortening_notice_date <= scope.assessed_on
            ):
                issues.append("NOTICE_DATE_AND_REGISTRAR_RECEIPT_REQUIRE_SEPARATE_ASSESSMENT")
        if data.deadline_rule is None:
            issues.append("EXPLICIT_MATCHING_DEADLINE_RULE_REQUIRED")
        if data.deadline and not scope.operative_from <= data.deadline <= scope.operative_through:
            issues.append("ADOPTED_WINDOW_DOES_NOT_COVER_BASE_DEADLINE")
    return {
        "profile": scope.profile,
        "filing_duty_assessment": duty,
        "state": "REVIEW_REQUIRED"
        if issues
        else "TIMETABLE_ON_ASSESSED_FACTS"
        if required
        else "ASSESSED_NO_FILING_DUTY",
        "filing_required": required,
        "company_status_at_reference_end": scope.company_status_at_reference_end,
        "accounting_reference_start": scope.accounting_reference_start.isoformat(),
        "accounting_reference_end": scope.accounting_reference_end.isoformat(),
        "period_classification": scope.period_classification,
        "shortened_period": scope.shortened_period,
        "assessed_on": scope.assessed_on.isoformat(),
        "issues": issues,
        "limitations": "Timetable over retained assessed company facts only. Filing-duty exceptions, period validity and operative versions need independent professional assessment. No complete accounts/audit pack, exemption certification, registry authenticity, tax conclusion or external filing is established.",
    }


def validate(data):
    scope = data.adgm_accounts_scope
    if scope is None:
        if data.adgm_guidance_evidence_id:
            raise ValueError("ADGM guidance evidence belongs to an explicit ADGM assessment")
        return
    if (
        data.dmcc_audit_scope is not None
        or data.module not in {"license", "governance"}
        or not data.jurisdiction_scope
        or data.jurisdiction_scope.obligation_country != "AE"
        or not data.jurisdiction_scope.registration_reference
        or data.obligation_period_start is None
        or data.obligation_period_end is None
        or not data.adgm_guidance_evidence_id
        or data.adgm_guidance_evidence_id == data.rule_evidence_id
        or data.adgm_guidance_evidence_id in data.fact_evidence_ids
    ):
        raise ValueError(
            "ADGM timetable requires separate UAE authority scope, accounts period, regulation, guidance and fact evidence"
        )
    if (
        scope.registration == "assessed_yes"
        and scope.legal_form == "company"
        and data.jurisdiction_scope.entity_country != "AE"
    ):
        raise ValueError(
            "An ADGM company needs its own UAE legal entity; a foreign parent's branch cannot inherit this company timetable"
        )
    from app.modules.grc.adgm_filing_duty import validate_binding as validate_duty_binding

    validate_duty_binding(data)
    result = assess(data)
    required = result["filing_required"]
    applicability = data.jurisdiction_scope.applicability
    if required is None and applicability != "potential":
        raise ValueError("Unresolved ADGM applicability must remain potential")
    if required is False and (
        applicability != "assessed_not_applicable"
        or data.deadline_rule
        or data.deadline
        or data.extension_deadline
    ):
        raise ValueError("An assessed ADGM filing exemption cannot retain an applicable deadline")
    if required is True and applicability == "assessed_not_applicable":
        raise ValueError("ADGM filing duty contradicts declared non-applicability")
    rule = data.deadline_rule
    if rule:
        if data.calendar_evidence_id in {
            data.rule_evidence_id,
            data.adgm_guidance_evidence_id,
            *data.fact_evidence_ids,
        }:
            raise ValueError(
                "ADGM calendar evidence must be separate from rule, guidance and company facts"
            )
        expected = expected_candidates(scope)
        actual = [(candidate.trigger, candidate.months_after) for candidate in candidates(rule)]
        if (
            not expected
            or sorted(actual) != sorted(expected)
            or any(
                candidate.days_after or candidate.date_basis != "specified_event"
                for candidate in candidates(rule)
            )
            or rule.month_end_policy != "preserve_month_end"
            or rule.day_count_basis != "calendar"
            or rule.convention != "following"
            or rule.rolling_calendar is None
            or set(rule.rolling_calendar.weekend_days) != {5, 6}
            or rule.timezone != "Asia/Dubai"
            or any(
                not scope.operative_from <= candidate.trigger <= scope.operative_through
                for candidate in candidates(rule)
            )
        ):
            raise ValueError(
                "ADGM deadline must retain the exact reference/anniversary/notice candidates, month-end preservation and independently evidenced following-day calendar"
            )
    if bool(data.extension_deadline) != bool(scope.extension_applied_at):
        raise ValueError(
            "ADGM extension requires its retained application timestamp and separate authority outcome"
        )
    if data.extension_evidence_id and data.extension_evidence_id in {
        data.rule_evidence_id,
        data.adgm_guidance_evidence_id,
        data.calendar_evidence_id,
        *data.fact_evidence_ids,
    }:
        raise ValueError(
            "ADGM extension outcome must be separate from authority, calendar and company-fact sources"
        )
    applied = (
        scope.extension_applied_at.astimezone(ZoneInfo("Asia/Dubai")).date()
        if scope.extension_applied_at
        else None
    )
    if data.extension_deadline and (
        not data.deadline
        or applied is None
        or applied > data.deadline
        or applied < scope.accounting_reference_start
        or data.extension_deadline
        > calendar_offset(scope.accounting_reference_end, 12, 0, "preserve_month_end")
        or data.extension_deadline > calendar_offset(data.deadline, 3, 0, "preserve_month_end")
        or data.extension_deadline > scope.operative_through
    ):
        raise ValueError(
            "ADGM extension must retain a timely application and respect the assessed three-month and reference-end twelve-month limits"
        )
    if result["issues"] and (
        data.filing_stage in {"approved_for_submission", "submitted", "acknowledged"}
        or data.compliance_assessment == "supported"
    ):
        raise ValueError(
            "Resolve ADGM timetable assessment issues before filing approval or supported compliance"
        )


def saved_assessment(body):
    if body.get("adgm_accounts_scope") is None:
        return None
    from app.modules.grc.schemas import Obligation
    from app.modules.grc.service import clean

    try:
        return assess(Obligation.model_validate(clean(body)))
    except (ValueError, TypeError, KeyError, OverflowError):
        raw_scope = body.get("adgm_accounts_scope")
        saved_profile = raw_scope.get("profile") if isinstance(raw_scope, dict) else None
        return {
            "profile": DUTY_PROFILE if saved_profile == DUTY_PROFILE else PROFILE,
            "state": "REVIEW_REQUIRED",
            "filing_required": None,
            "issues": ["SAVED_ADGM_SCOPE_REQUIRES_REASSESSMENT"],
        }


async def verify_sources(db, ctx, data, checked):
    from app.modules.grc.authority_sources import verify_original_sources

    await verify_original_sources(
        db,
        ctx,
        checked,
        "ADGM",
        [
            (data.rule_evidence_id, REGULATIONS_SHA256),
            (data.adgm_guidance_evidence_id, GUIDANCE_SHA256),
        ],
        data.extension_evidence_id,
    )

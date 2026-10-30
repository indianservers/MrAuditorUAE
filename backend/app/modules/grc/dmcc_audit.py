"""Source-pinned DMCC procedure checks over independently assessed entity facts."""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.modules.audit_execution.schemas import Strict
from app.modules.grc.deadlines import CalendarDate

PROFILE = "dmcc-company-2024-amended-2025-and-afs-guidance-2025/1"
REGULATIONS_SHA256 = "96748cccb799efffb84d89492cee342faf52eaac39bbe45d997eb8db656e45d1"
GUIDELINE_SHA256 = "8fa1747da919b757f1605bf411638345d428f44ad492bfa62173eb4ff8847aa7"
Fact = Literal["assessed_yes", "assessed_no", "unassessed", "not_applicable"]
Notice = Literal["assessed_valid", "assessed_none", "unassessed", "not_applicable"]


class DMCCAuditScope(Strict):
    profile: Literal["dmcc-company-2024-amended-2025-and-afs-guidance-2025/1"]
    procedure: Literal["accounts_timetable", "registrar_filing", "portal_submission"]
    legal_form: Literal["company_limited_by_shares", "branch", "limited_by_guarantee", "unassessed"]
    membership: Fact
    dormant_whole_year: Fact
    holding_company: Fact
    accounts_notice: Notice
    audit_notice: Notice
    branch_group_auditor: Fact
    auditor_status: Literal[
        "assessed_approved",
        "assessed_not_approved",
        "group_auditor_exception",
        "unassessed",
        "not_applicable",
    ]
    auditor_reference: str = Field(max_length=200)
    other_authority_modifications: Literal["assessed_none", "unresolved"]
    operative_from: CalendarDate
    operative_through: CalendarDate
    assessed_on: CalendarDate
    meeting_date: CalendarDate | None = None
    assessment: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def facts(self):
        if self.operative_through < self.operative_from or len(self.assessment.strip()) < 10:
            raise ValueError(
                "Retain an ordered adopted rule window and meaningful DMCC scope assessment"
            )
        if self.auditor_reference != self.auditor_reference.strip():
            raise ValueError("Retain the exact assessed auditor reference")
        if (
            self.auditor_status in {"assessed_approved", "group_auditor_exception"}
            and not self.auditor_reference
        ):
            raise ValueError("Positive auditor assessment requires its retained identity reference")
        if self.legal_form == "branch" and any(
            value != "not_applicable"
            for value in (
                self.dormant_whole_year,
                self.holding_company,
                self.accounts_notice,
                self.audit_notice,
            )
        ):
            raise ValueError(
                "Company dormancy and shareholder-notice criteria cannot be reused for a branch"
            )
        if (
            self.legal_form == "company_limited_by_shares"
            and self.branch_group_auditor != "not_applicable"
        ):
            raise ValueError(
                "The branch group-auditor exception is separate from a registered company"
            )
        return self


def assess(data):
    scope = data.dmcc_audit_scope
    if scope is None:
        return None
    issues = []
    accounts = audit = groups = required = None
    approved_rule = "UNASSESSED"
    if scope.membership == "assessed_no":
        required = False
    elif scope.membership != "assessed_yes":
        issues.append("DMCC_MEMBERSHIP_UNASSESSED")
    elif scope.legal_form == "company_limited_by_shares":
        if scope.dormant_whole_year == "assessed_no":
            accounts = audit = True
        elif scope.dormant_whole_year == "assessed_yes":
            accounts = {"assessed_valid": True, "assessed_none": False}.get(scope.accounts_notice)
            audit = {"assessed_valid": True, "assessed_none": False}.get(scope.audit_notice)
            if accounts is None or audit is None:
                issues.append("DORMANCY_SHAREHOLDER_NOTICES_UNASSESSED")
            if audit is True and accounts is False:
                accounts = None
                issues.append("AUDIT_NOTICE_AND_ACCOUNTS_EXEMPTION_REQUIRE_SEPARATE_ASSESSMENT")
        else:
            issues.append("WHOLE_YEAR_DORMANCY_UNASSESSED")
        groups = {"assessed_yes": True, "assessed_no": False}.get(scope.holding_company)
        if groups is None:
            issues.append("GROUP_ACCOUNTS_SCOPE_UNASSESSED")
        if groups and scope.dormant_whole_year == "assessed_yes":
            issues.append("DORMANT_HOLDING_COMPANY_GROUP_ACCOUNTS_REQUIRE_SEPARATE_ASSESSMENT")
        if audit:
            approved_rule = "DMCC_APPROVED_AUDITOR_REQUIRED"
            if scope.auditor_status != "assessed_approved":
                issues.append("DMCC_APPROVED_AUDITOR_ASSESSMENT_REQUIRED")
        else:
            approved_rule = (
                "AUDIT_REQUIREMENT_NOT_ESTABLISHED"
                if audit is None
                else "NO_AUDIT_REQUIRED_UNDER_ASSESSED_COMPANY_FACTS"
            )
        if scope.procedure == "portal_submission":
            if scope.dormant_whole_year == "assessed_no":
                required = True
            else:
                issues.append("DORMANT_PORTAL_TREATMENT_REQUIRES_SEPARATE_AUTHORITY_ASSESSMENT")
        else:
            required = accounts
    elif scope.legal_form == "branch":
        if scope.procedure != "portal_submission":
            issues.append("COMPANY_SECTION_11_PROCEDURE_DOES_NOT_ESTABLISH_BRANCH_REQUIREMENTS")
        else:
            required = True
            if scope.branch_group_auditor == "assessed_yes":
                approved_rule = "BRANCH_GROUP_AUDITOR_EXCEPTION_ASSESSED"
                if scope.auditor_status != "group_auditor_exception":
                    issues.append("ASSESS_RETAINED_BRANCH_GROUP_AUDITOR_EXCEPTION")
            elif scope.branch_group_auditor == "assessed_no":
                approved_rule = "DMCC_APPROVED_AUDITOR_REQUIRED"
                if scope.auditor_status != "assessed_approved":
                    issues.append("DMCC_APPROVED_AUDITOR_ASSESSMENT_REQUIRED")
            else:
                issues.append("BRANCH_GROUP_AUDITOR_UNASSESSED")
    else:
        issues.append("LEGAL_FORM_REQUIRES_ITS_SEPARATE_REGULATIONS")
    if scope.assessed_on < date(2025, 4, 29):
        issues.append("JOINT_SOURCE_PROFILE_NOT_AVAILABLE_AT_ASSESSMENT_DATE")
    if scope.assessed_on < data.obligation_period_end:
        issues.append("FINANCIAL_YEAR_NOT_COMPLETE_AT_ASSESSMENT")
    if (
        not scope.operative_from
        <= data.obligation_period_end
        <= scope.assessed_on
        <= scope.operative_through
    ):
        issues.append("ADOPTED_RULE_WINDOW_DOES_NOT_COVER_PERIOD_END_AND_ASSESSMENT")
    if scope.other_authority_modifications != "assessed_none":
        issues.append("OTHER_AUTHORITY_MODIFICATIONS_UNRESOLVED")
    if required and scope.procedure == "registrar_filing":
        if (
            scope.meeting_date is None
            or not data.obligation_period_end <= scope.meeting_date <= scope.assessed_on
        ):
            issues.append("RETAIN_ACTUAL_IN_SCOPE_GENERAL_MEETING_DATE")
    if required and data.deadline_rule is None:
        issues.append("EXPLICIT_MATCHING_DEADLINE_RULE_REQUIRED")
    return {
        "profile": PROFILE,
        "procedure": scope.procedure,
        "legal_form": scope.legal_form,
        "accounts_required": accounts,
        "audit_required": audit,
        "group_accounts_required": groups,
        "procedure_required": required,
        "approved_auditor_rule": approved_rule,
        "state": "REVIEW_REQUIRED"
        if issues or required is None
        else "REQUIRED_ON_ASSESSED_FACTS"
        if required
        else "NOT_REQUIRED_ON_ASSESSED_FACTS",
        "issues": issues,
        "assessed_on": scope.assessed_on.isoformat(),
        "limitations": "Assessed entity facts and adopted source window only; no registry/auditor authenticity, complete legal qualification, filing or audit opinion. Dormant portal, dormant group accounts, separate legal forms and authority variations need separate assessment.",
    }


def validate(data):
    scope = data.dmcc_audit_scope
    if scope is None:
        if data.dmcc_guideline_evidence_id:
            raise ValueError("DMCC guideline evidence belongs to an explicit DMCC assessment")
        return
    if (
        data.module not in {"license", "governance"}
        or not data.jurisdiction_scope
        or data.jurisdiction_scope.obligation_country != "AE"
        or not data.jurisdiction_scope.registration_reference
        or data.obligation_period_start is None
        or data.obligation_period_end is None
        or not data.dmcc_guideline_evidence_id
        or data.dmcc_guideline_evidence_id == data.rule_evidence_id
    ):
        raise ValueError(
            "DMCC profile requires explicit UAE authority scope, registration, financial period and separate regulation/guideline evidence"
        )
    if (
        scope.membership == "assessed_yes"
        and scope.legal_form == "company_limited_by_shares"
        and data.jurisdiction_scope.entity_country != "AE"
    ):
        raise ValueError(
            "A registered DMCC company needs its own UAE legal-entity scope; a foreign parent can assess a separately declared branch"
        )
    result = assess(data)
    required = result["procedure_required"]
    if required is None and data.jurisdiction_scope.applicability != "potential":
        raise ValueError("Unresolved DMCC applicability must remain potential")
    if required is False:
        if (
            data.jurisdiction_scope.applicability == "assessed_applicable"
            or data.deadline_rule
            or data.deadline
        ):
            raise ValueError(
                "An assessed DMCC non-requirement cannot retain an applicable filing deadline"
            )
    elif required is True and data.jurisdiction_scope.applicability == "assessed_not_applicable":
        raise ValueError("DMCC requirement contradicts the declared non-applicability")
    rule = data.deadline_rule
    if rule and rule.later_of:
        raise ValueError(
            "The adopted DMCC timetable does not permit additional deadline candidates"
        )
    if required and rule:
        if scope.procedure == "registrar_filing":
            if (
                rule.date_basis != "specified_event"
                or rule.trigger != scope.meeting_date
                or rule.day_count_basis != "business"
                or rule.days_after != 5
                or rule.business_trigger_policy != "exclude"
                or rule.business_calendar is None
                or set(rule.business_calendar.weekend_days) != {5, 6}
            ):
                raise ValueError(
                    "DMCC registrar filing requires the assessed meeting event and five business days with Dubai weekends"
                )
        elif (
            rule.date_basis != "period_end"
            or rule.trigger != data.obligation_period_end
            or rule.day_count_basis != "calendar"
            or rule.months_after != 6
            or rule.days_after
            or rule.convention != "calendar"
            or rule.weekend_days
            or rule.holidays
        ):
            raise ValueError(
                "DMCC accounts/portal timetable requires six calendar months from the exact financial year end"
            )
        if rule.timezone != "Asia/Dubai":
            raise ValueError("DMCC deadline must retain the Dubai timezone")
    if result["issues"] and (
        data.filing_stage in {"approved_for_submission", "submitted", "acknowledged"}
        or data.compliance_assessment == "supported"
    ):
        raise ValueError(
            "Resolve DMCC procedure assessment issues before filing approval or supported compliance"
        )


def saved_assessment(body):
    if body.get("dmcc_audit_scope") is None:
        return None
    from app.modules.grc.schemas import Obligation
    from app.modules.grc.service import clean

    try:
        return assess(Obligation.model_validate(clean(body)))
    except (ValueError, TypeError, KeyError):
        return {
            "profile": PROFILE,
            "state": "REVIEW_REQUIRED",
            "procedure_required": None,
            "issues": ["SAVED_DMCC_SCOPE_REQUIRES_REASSESSMENT"],
        }


async def verify_sources(db, ctx, data, checked):
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.modules.audit_execution.models import EvidenceVersion
    from app.modules.lineage.storage import ObjectStore, hash_file

    if data.extension_evidence_id and checked[str(data.extension_evidence_id)].kind != "evidence":
        raise HTTPException(
            422, "DMCC deadline extensions require original retained authority evidence"
        )

    for identifier, digest in (
        (data.rule_evidence_id, REGULATIONS_SHA256),
        (data.dmcc_guideline_evidence_id, GUIDELINE_SHA256),
    ):
        if checked[str(identifier)].kind != "evidence":
            raise HTTPException(
                422, "DMCC profile requires original regulation and guideline evidence"
            )
        version = await db.scalar(
            select(EvidenceVersion)
            .where(
                EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == identifier
            )
            .order_by(EvidenceVersion.number.desc())
            .limit(1)
        )
        if (
            not version
            or version.scan_status != "CLEAN"
            or version.sha256 != digest
            or version.media_type != "application/pdf"
        ):
            raise HTTPException(
                409, "Select the exact retained original PDFs for the adopted DMCC profile version"
            )
        try:
            with ObjectStore().local(version.object_key, version.object_version) as path:
                if path.stat().st_size != version.size or hash_file(path) != digest:
                    raise HTTPException(
                        409, "Retained DMCC source bytes do not match the adopted profile"
                    )
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Retained DMCC source bytes are unavailable") from error

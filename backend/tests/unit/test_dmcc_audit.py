"""Assessed DMCC facts and exact procedure boundaries, not professional qualification."""

import hashlib
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.grc.dmcc_audit import (
    GUIDELINE_SHA256,
    PROFILE,
    REGULATIONS_SHA256,
    assess,
    saved_assessment,
)
from app.modules.grc.schemas import Obligation
from tests.unit.test_business_day_deadlines import parameters as business_rule


def payload():
    return {
        "owner_id": str(uuid4()),
        "entity_id": str(uuid4()),
        "module": "license",
        "source_url": "https://dmcc.ae/members/support/knowledge-bank/compliance-and-regulations",
        "jurisdiction": "AE",
        "jurisdiction_scope": {
            "entity_country": "AE",
            "obligation_country": "AE",
            "relationship": "domestic",
            "applicability": "assessed_applicable",
            "registration_reference": "SYN-DMCC-123",
            "assessment": "SYNTHETIC independently assessed exact DMCC entity scope",
        },
        "obligation_period_start": "2025-01-01",
        "obligation_period_end": "2025-12-31",
        "effective_from": "2025-01-01",
        "deadline_kind": "firm_internal",
        "rule_evidence_id": str(uuid4()),
        "dmcc_guideline_evidence_id": str(uuid4()),
        "fact_evidence_ids": [str(uuid4())],
        "entity_facts": {
            "assessment": "SYNTHETIC original licence, company facts and auditor assessment"
        },
        "required_evidence": "Independent exact source versions and company facts",
        "compliance_assessment": "pending",
        "deadline_rule": {
            "identifier": "SYNTHETIC-DMCC-six-month-timetable",
            "version": 1,
            "effective_from": "2024-10-10",
            "trigger": "2025-12-31",
            "date_basis": "period_end",
            "months_after": 6,
            "timezone": "Asia/Dubai",
        },
        "dmcc_audit_scope": {
            "profile": PROFILE,
            "procedure": "accounts_timetable",
            "legal_form": "company_limited_by_shares",
            "membership": "assessed_yes",
            "dormant_whole_year": "assessed_no",
            "holding_company": "assessed_no",
            "accounts_notice": "not_applicable",
            "audit_notice": "not_applicable",
            "branch_group_auditor": "not_applicable",
            "auditor_status": "assessed_approved",
            "auditor_reference": "SYNTHETIC-AUDITOR-1",
            "other_authority_modifications": "assessed_none",
            "operative_from": "2024-10-10",
            "operative_through": "2026-12-31",
            "assessed_on": "2026-06-30",
            "assessment": "SYNTHETIC adopted source window and retained company/auditor facts; not legal or client qualification",
        },
    }


@pytest.mark.parametrize("procedure", ["accounts_timetable", "portal_submission"])
def test_active_company_procedures_retain_six_calendar_months_and_separate_audit_scope(procedure):
    value = payload()
    value["dmcc_audit_scope"]["procedure"] = procedure
    data = Obligation.model_validate(value)
    result = assess(data)
    assert data.deadline.isoformat() == "2026-06-30"
    assert result["accounts_required"] is True and result["audit_required"] is True
    assert result["procedure_required"] is True and result["issues"] == []


def test_registrar_deadline_uses_actual_meeting_not_six_month_deadline():
    value = payload()
    value["dmcc_audit_scope"].update(
        procedure="registrar_filing", meeting_date="2026-06-26", assessed_on="2026-07-06"
    )
    value.update(deadline_rule=business_rule(), calendar_evidence_id=str(uuid4()))
    data = Obligation.model_validate(value)
    assert data.deadline.isoformat() == "2026-07-06" and assess(data)["issues"] == []


@pytest.mark.parametrize(
    "group,status,expected",
    [
        ("assessed_yes", "group_auditor_exception", "BRANCH_GROUP_AUDITOR_EXCEPTION_ASSESSED"),
        ("assessed_no", "assessed_approved", "DMCC_APPROVED_AUDITOR_REQUIRED"),
    ],
)
def test_branch_group_auditor_exception_does_not_exempt_portal_submission(group, status, expected):
    value = payload()
    value["dmcc_audit_scope"].update(
        procedure="portal_submission",
        legal_form="branch",
        dormant_whole_year="not_applicable",
        holding_company="not_applicable",
        branch_group_auditor=group,
        auditor_status=status,
    )
    result = assess(Obligation.model_validate(value))
    assert result["procedure_required"] is True and result["audit_required"] is None
    assert result["approved_auditor_rule"] == expected and result["issues"] == []


def test_dormant_company_notices_remain_distinct_and_exemption_has_no_filing_date():
    value = payload()
    value["dmcc_audit_scope"].update(
        dormant_whole_year="assessed_yes",
        accounts_notice="assessed_none",
        audit_notice="assessed_none",
        auditor_status="not_applicable",
        auditor_reference="",
    )
    value["jurisdiction_scope"]["applicability"] = "assessed_not_applicable"
    value["deadline_rule"] = None
    data = Obligation.model_validate(value)
    result = assess(data)
    assert result["accounts_required"] is False and result["audit_required"] is False
    assert result["procedure_required"] is False and data.deadline is None
    value["jurisdiction_scope"]["applicability"] = "assessed_applicable"
    with pytest.raises(ValueError, match="non-requirement"):
        Obligation.model_validate(value)


def test_valid_assessed_notices_restore_separate_company_requirements():
    value = payload()
    value["dmcc_audit_scope"].update(
        dormant_whole_year="assessed_yes",
        accounts_notice="assessed_valid",
        audit_notice="assessed_valid",
    )
    result = assess(Obligation.model_validate(value))
    assert result["accounts_required"] and result["audit_required"] and not result["issues"]


@pytest.mark.parametrize(
    "change",
    [
        {
            "procedure": "portal_submission",
            "dormant_whole_year": "assessed_yes",
            "accounts_notice": "assessed_none",
            "audit_notice": "assessed_none",
        },
        {"dormant_whole_year": "unassessed"},
        {"legal_form": "limited_by_guarantee"},
    ],
)
def test_unknown_or_separate_scope_cannot_be_declared_applicable(change):
    value = payload()
    value["dmcc_audit_scope"].update(change)
    value["deadline_rule"] = None
    with pytest.raises(ValueError, match="remain potential"):
        Obligation.model_validate(value)
    value["jurisdiction_scope"]["applicability"] = "potential"
    assert assess(Obligation.model_validate(value))["state"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("other_authority_modifications", "unresolved"),
        ("holding_company", "unassessed"),
        ("auditor_status", "unassessed"),
        ("assessed_on", "2025-12-30"),
        ("operative_through", "2026-05-31"),
    ],
)
def test_known_requirement_with_unresolved_readiness_cannot_advance_to_filing(field, value):
    body = payload()
    body["dmcc_audit_scope"][field] = value
    data = Obligation.model_validate(body)
    assert assess(data)["issues"]
    body.update(
        filing_stage="approved_for_submission",
        reviewer_id=str(uuid4()),
        readiness_evidence_ids=[str(uuid4())],
    )
    with pytest.raises(ValueError, match="Resolve DMCC"):
        Obligation.model_validate(body)


@pytest.mark.parametrize(
    "change",
    [
        {"months_after": 0, "days_after": 180},
        {"trigger": "2026-01-01"},
        {"timezone": "Asia/Kolkata"},
        {"convention": "following", "weekend_days": [5, 6]},
    ],
)
def test_dmcc_profile_rejects_a_similar_but_different_deadline(change):
    body = payload()
    body["deadline_rule"].update(change)
    with pytest.raises(ValueError):
        Obligation.model_validate(body)


@pytest.mark.parametrize(
    "field,value",
    [
        ("module", "corporate_tax"),
        ("obligation_period_end", None),
        ("dmcc_guideline_evidence_id", None),
    ],
)
def test_profile_is_separate_from_ct_and_requires_authority_period_and_sources(field, value):
    body = payload()
    body[field] = value
    with pytest.raises(ValueError):
        Obligation.model_validate(body)


def test_india_entity_can_assess_foreign_uae_branch_without_domestic_uae_engine():
    body = payload()
    body["jurisdiction_scope"].update(entity_country="IN", relationship="foreign")
    with pytest.raises(ValueError, match="own UAE legal-entity scope"):
        Obligation.model_validate(body)
    body["dmcc_audit_scope"].update(
        procedure="portal_submission",
        legal_form="branch",
        dormant_whole_year="not_applicable",
        holding_company="not_applicable",
        branch_group_auditor="assessed_yes",
        auditor_status="group_auditor_exception",
    )
    assert assess(Obligation.model_validate(body))["procedure_required"] is True
    body["jurisdiction"] = "IN"
    body["jurisdiction_scope"].update(obligation_country="IN", relationship="domestic")
    with pytest.raises(ValueError):
        Obligation.model_validate(body)


def test_source_constants_match_the_exact_original_retained_authority_files():
    root = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/authority-references/dmcc-audit-2026-10-30"
    )
    for name, digest in [
        ("dmcc-company-regulations-amended.pdf", REGULATIONS_SHA256),
        ("dmcc-afs-guidelines-2025-04-29.pdf", GUIDELINE_SHA256),
    ]:
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest


def test_saved_malformed_profile_is_visible_as_reassessment_not_a_server_error():
    body = deepcopy(payload())
    body["dmcc_audit_scope"]["membership"] = "invented"
    assert saved_assessment(body)["issues"] == ["SAVED_DMCC_SCOPE_REQUIRES_REASSESSMENT"]


@pytest.mark.parametrize("scope", [{}, "", False])
def test_empty_or_invalid_saved_profile_does_not_silently_become_no_profile(scope):
    body = payload()
    body["dmcc_audit_scope"] = scope
    assert saved_assessment(body)["state"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("stage", ["approved_for_submission", "submitted", "acknowledged"])
@pytest.mark.parametrize("change", ["scope", "guideline", "remove_profile"])
async def test_approved_dmcc_scope_cannot_change_without_preparing(monkeypatch, stage, change):
    from app.modules.grc import filing

    body = payload()
    reviewer, rid = uuid4(), uuid4()
    body.update(
        filing_stage=stage,
        reviewer_id=str(reviewer),
        readiness_evidence_ids=[str(uuid4())],
        submission_evidence_id=str(uuid4()) if stage != "approved_for_submission" else None,
        acknowledgment_evidence_id=str(uuid4()) if stage == "acknowledged" else None,
    )
    original = Obligation.model_validate(body)
    previous = SimpleNamespace(body=original.model_dump(mode="json"), status="REVISED")

    async def record(*args):
        return previous if args[3] == rid else SimpleNamespace(kind="evidence")

    monkeypatch.setattr(filing.audit, "get_record", record)
    monkeypatch.setattr(filing, "engagement_permissions", AsyncMock())
    changed = original.model_dump(mode="json")
    if change == "scope":
        changed["dmcc_audit_scope"]["assessed_on"] = "2026-07-01"
    elif change == "guideline":
        changed["dmcc_guideline_evidence_id"] = str(uuid4())
    else:
        changed.pop("dmcc_audit_scope")
        changed.pop("dmcc_guideline_evidence_id")
    ctx, eng = SimpleNamespace(user_id=reviewer, tenant_id=uuid4()), SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException, match="Approved filing inputs changed"):
        await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)
    changed["filing_stage"] = "preparing"
    await filing.validate_transition(None, ctx, eng, Obligation.model_validate(changed), rid)


def test_active_holding_company_retains_a_separate_group_accounts_requirement():
    body = payload()
    body["dmcc_audit_scope"]["holding_company"] = "assessed_yes"
    result = assess(Obligation.model_validate(body))
    assert result["group_accounts_required"] is True and result["audit_required"] is True


def test_dormant_accounts_notice_does_not_automatically_become_an_audit_notice():
    body = payload()
    body["dmcc_audit_scope"].update(
        dormant_whole_year="assessed_yes",
        accounts_notice="assessed_valid",
        audit_notice="assessed_none",
        auditor_status="not_applicable",
        auditor_reference="",
    )
    result = assess(Obligation.model_validate(body))
    assert result["accounts_required"] is True and result["audit_required"] is False


def test_dormant_audit_notice_and_claimed_accounts_exemption_stay_unresolved():
    body = payload()
    body["dmcc_audit_scope"].update(
        dormant_whole_year="assessed_yes",
        accounts_notice="assessed_none",
        audit_notice="assessed_valid",
    )
    body["jurisdiction_scope"]["applicability"] = "potential"
    body["deadline_rule"] = None
    result = assess(Obligation.model_validate(body))
    assert result["procedure_required"] is None
    assert "AUDIT_NOTICE_AND_ACCOUNTS_EXEMPTION_REQUIRE_SEPARATE_ASSESSMENT" in result["issues"]


@pytest.mark.parametrize(
    "membership,applicability,state",
    [
        ("assessed_no", "assessed_not_applicable", "NOT_REQUIRED_ON_ASSESSED_FACTS"),
        ("unassessed", "potential", "REVIEW_REQUIRED"),
    ],
)
def test_assessed_non_membership_is_distinct_from_missing_membership(
    membership, applicability, state
):
    body = payload()
    body["dmcc_audit_scope"]["membership"] = membership
    body["jurisdiction_scope"]["applicability"] = applicability
    body["deadline_rule"] = None
    assert assess(Obligation.model_validate(body))["state"] == state


def test_branch_cannot_inherit_the_company_registrar_meeting_procedure():
    body = payload()
    body["dmcc_audit_scope"].update(
        legal_form="branch",
        procedure="registrar_filing",
        dormant_whole_year="not_applicable",
        holding_company="not_applicable",
        branch_group_auditor="assessed_yes",
        auditor_status="group_auditor_exception",
    )
    body["jurisdiction_scope"]["applicability"] = "potential"
    body["deadline_rule"] = None
    assert assess(Obligation.model_validate(body))["procedure_required"] is None


def test_dormant_holding_company_cannot_silently_waive_group_accounts():
    body = payload()
    body["dmcc_audit_scope"].update(
        dormant_whole_year="assessed_yes",
        holding_company="assessed_yes",
        accounts_notice="assessed_none",
        audit_notice="assessed_none",
        auditor_status="not_applicable",
        auditor_reference="",
    )
    body["jurisdiction_scope"]["applicability"] = "assessed_not_applicable"
    body["deadline_rule"] = None
    assert (
        "DORMANT_HOLDING_COMPANY_GROUP_ACCOUNTS_REQUIRE_SEPARATE_ASSESSMENT"
        in assess(Obligation.model_validate(body))["issues"]
    )


def test_registrar_business_week_cannot_be_replaced_with_a_different_country_calendar():
    body = payload()
    body["dmcc_audit_scope"].update(
        procedure="registrar_filing", meeting_date="2026-06-26", assessed_on="2026-07-06"
    )
    body.update(deadline_rule=business_rule(), calendar_evidence_id=str(uuid4()))
    body["deadline_rule"]["business_calendar"]["weekend_days"] = [6]
    with pytest.raises(ValueError, match="Dubai weekends"):
        Obligation.model_validate(body)

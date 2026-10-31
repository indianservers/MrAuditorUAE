from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.uae_company_accounts import (
    AMENDMENT_SHA256,
    CONTRACT,
    LAW_SHA256,
    CompanyAccountsInput,
    assess,
)


def sample(**changes):
    return {
        "profile": CONTRACT,
        "label": "SYNTHETIC company-law accounts assessment",
        "registration_reference": "SYN-CCL-REGISTRATION",
        "fiscal_year_start": "2025-01-01",
        "fiscal_year_end": "2025-12-31",
        "assessed_on": "2026-10-01",
        "adopted_from": "2025-01-01",
        "adopted_through": "2026-12-31",
        # Declared synthetic publication date, not an assertion of the actual Gazette date.
        "amendment_publication_date": "2025-11-01",
        "rule_chain_status": "assessed_adopted",
        "other_rule_changes": "assessed_none",
        "rule_adoption_assessment": "SYNTHETIC independently adopted complete period source chain; no real legal qualification",
        "law_scope": "assessed_applies",
        "scope_assessment": "SYNTHETIC independently assessed Articles3–5 applicability, exclusions and whole-period facts",
        "fiscal_year_validity": "assessed_valid",
        "legal_form": "limited_liability",
        "holding_company": "assessed_no",
        "request_population": "assessed_none",
        "requester_eligibility": "unassessed",
        "request_received_on": None,
        "selected_year_is_last_audited": "unassessed",
        "response_counting": "unassessed",
        "counting_assessment": "",
        "response_status": "unassessed",
        "responded_on": None,
        "accounts_copy_delivered": "unassessed",
        "auditor_report_copy_delivered": "unassessed",
        "group_accounts_copy_delivered": "unassessed",
        "fact_assessment": "SYNTHETIC independent company and exact fiscal-year facts with no written requests in scope",
        "law_evidence_version_id": str(uuid4()),
        "amendment_evidence_version_id": str(uuid4()),
        "adoption_evidence_version_id": str(uuid4()),
        "adoption_sha256": "a" * 64,
        "fact_evidence_version_id": str(uuid4()),
        "fact_sha256": "b" * 64,
        **changes,
    }


def row(**changes):
    return assess(CompanyAccountsInput.model_validate(sample(**changes)))["rows"][0]


def written(**changes):
    return row(
        **{
            "request_population": "written_request",
            "requester_eligibility": "assessed_partner_or_shareholder",
            "request_received_on": "2026-09-20",
            "selected_year_is_last_audited": "assessed_yes",
            "response_counting": "assessed_calendar_days_excluding_receipt",
            "counting_assessment": "SYNTHETIC independently adopted calendar-day counting excluding receipt day",
            "response_status": "assessed_responded",
            "responded_on": "2026-09-30",
            "accounts_copy_delivered": "assessed_yes",
            "auditor_report_copy_delivered": "assessed_yes",
            **changes,
        },
    )


@pytest.mark.parametrize(
    "form,required",
    [
        ("limited_liability", True),
        ("public_joint_stock", True),
        ("private_joint_stock", True),
        ("general_partnership", False),
        ("limited_partnership", False),
        ("unassessed", None),
    ],
)
def test_annual_audit_is_a_separate_company_law_branch_without_revenue_threshold(form, required):
    result = row(legal_form=form)
    assert result["annual_audit_required"] is required
    assert result["annual_accounts_required"] is True
    assert result["accounting_registers_required"] is True
    assert result["minimum_register_retention_years"] == 5
    assert result["entity_audit_exemption_established"] is False
    assert result["response_required"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("law_scope", "unresolved"),
        ("rule_chain_status", "unresolved"),
        ("other_rule_changes", "unresolved"),
        ("amendment_publication_date", None),
    ],
)
def test_unknown_scope_or_chain_cannot_become_a_negative_duty(field, value):
    result = row(**{field: value})
    assert result["annual_audit_required"] is None
    assert result["state"] == "EXCEPTION"
    assert result["entity_audit_exemption_established"] is False
    if field != "law_scope":
        assert result["dated_source_requirements"]["annual_audit_required"] is True


def test_assessed_exclusion_does_not_establish_any_other_audit_exemption():
    result = row(law_scope="assessed_excluded", legal_form="unassessed")
    assert result["annual_audit_required"] is False
    assert result["annual_accounts_required"] is False
    assert result["minimum_register_retention_years"] is None
    assert result["entity_audit_exemption_established"] is False


def test_unassessed_fiscal_validity_does_not_clear_annual_procedures():
    result = row(fiscal_year_validity="unassessed")
    assert result["annual_audit_required"] is None
    assert result["annual_accounts_required"] is None
    assert result["accounting_registers_required"] is True


def test_written_request_boundary_keeps_copies_and_calendar_interpretation_explicit():
    result = written()
    assert result["response_deadline"] == "2026-09-30"
    assert result["response_timing"] == "RESPONDED_WITHIN_ASSESSED_PERIOD"
    assert result["response_complete"] is True
    assert result["group_accounts_copy_required"] is False
    assert written(responded_on="2026-10-01")["response_timing"] == "RESPONDED_LATE"
    assert written(auditor_report_copy_delivered="assessed_no")["response_complete"] is False
    assert written(auditor_report_copy_delivered="unassessed")["response_complete"] is None


def test_holding_company_requires_the_group_copy_and_unknown_is_not_nonholding():
    result = written(holding_company="assessed_yes")
    assert result["group_accounts_copy_required"] is True
    assert result["response_complete"] is None
    assert (
        written(holding_company="assessed_yes", group_accounts_copy_delivered="assessed_yes")[
            "response_complete"
        ]
        is True
    )
    assert written(holding_company="unassessed")["response_complete"] is None


@pytest.mark.parametrize(
    "as_of,expected",
    [
        ("2026-09-29", "NOT_YET_DUE"),
        ("2026-09-30", "DUE_ON_ASSESSED_DATE"),
        ("2026-10-01", "OVERDUE"),
    ],
)
def test_assessed_no_response_is_distinct_from_unknown_response(as_of, expected):
    result = written(
        assessed_on=as_of,
        response_status="assessed_not_responded",
        responded_on=None,
        accounts_copy_delivered="unassessed",
        auditor_report_copy_delivered="unassessed",
    )
    assert result["response_timing"] == expected
    assert result["response_complete"] is False
    assert ("REQUEST_RESPONSE_OVERDUE" in result["issues"]) is (expected == "OVERDUE")


def test_missing_counting_and_last_audited_scope_do_not_establish_compliant_delivery():
    result = written(
        response_counting="unassessed",
        counting_assessment="",
        selected_year_is_last_audited="unassessed",
    )
    assert result["response_deadline"] is None
    assert result["response_complete"] is None
    assert result["state"] == "EXCEPTION"
    assert written(response_status="unassessed", responded_on=None)["response_complete"] is None


def test_unknown_request_population_is_not_cleared_by_an_irrelevant_requester_flag():
    result = row(request_population="unassessed", requester_eligibility="assessed_other")
    assert result["response_required"] is None
    assert "REQUEST_POPULATION_UNASSESSED" in result["issues"]


@pytest.mark.parametrize(
    "changes",
    [
        {"assessed_on": "2100-01-01"},
        {"fiscal_year_start": "2021-01-01"},
        {"fiscal_year_end": "2027-12-31"},
        {"adopted_from": "2025-02-01"},
        {"amendment_publication_date": "2025-09-30"},
        {"amendment_publication_date": "2027-01-01"},
        {"request_received_on": "2026-01-01"},
        {"scope_assessment": " " * 20},
        {"fact_sha256": LAW_SHA256},
        {"adoption_sha256": AMENDMENT_SHA256},
        {"adoption_sha256": "b" * 64},
        {"holding_company": False},
    ],
)
def test_invalid_dates_facts_and_cloned_document_roles_fail_closed(changes):
    with pytest.raises(ValidationError):
        CompanyAccountsInput.model_validate(sample(**changes))


def test_reused_versions_fail_and_saved_unbound_assessments_cannot_be_approved():
    from app.modules.country_workflows.review import approval_error

    data = sample()
    data["fact_evidence_version_id"] = data["adoption_evidence_version_id"]
    with pytest.raises(ValidationError):
        CompanyAccountsInput.model_validate(data)
    body = assess(CompanyAccountsInput.model_validate(sample()))
    assert approval_error(body)
    body["company_accounts_document_binding"] = "RETAINED_DOCUMENT_BYTES_VERIFIED"
    assert approval_error(body) is None
    assert body["statutory_calculation_qualified"] is False

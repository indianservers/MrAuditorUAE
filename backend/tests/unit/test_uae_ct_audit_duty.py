from uuid import uuid4

import pytest

from app.modules.country_workflows.uae_ct_audit_duty import CONTRACT, CTAuditDutyInput, assess


def sample(**changes):
    return {
        "profile": CONTRACT,
        "label": "SYNTHETIC MD84 duty assessment",
        "registration_reference": "SYN-CT-REGISTRATION",
        "tax_period_start": "2026-01-01",
        "tax_period_end": "2026-09-30",
        "assessed_on": "2026-10-01",
        "adopted_from": "2025-01-01",
        "adopted_through": "2026-12-31",
        "other_rule_changes": "assessed_none",
        "rule_adoption_assessment": "SYNTHETIC independently adopted dated source and declared completed tax period",
        "taxable_person": "assessed_yes",
        "tax_group": "assessed_no",
        "tax_group_member": "assessed_no",
        "qualifying_free_zone_person": "assessed_no",
        "residency": "resident",
        "revenue_basis": "whole_person",
        "revenue_aed": "50000000.00",
        "currency": "AED",
        "designated_zone_distribution": "assessed_no",
        "fact_assessment": "SYNTHETIC independent classifications and complete period revenue",
        "rule_evidence_version_id": str(uuid4()),
        "clarification_evidence_version_id": str(uuid4()),
        "fact_evidence_version_id": str(uuid4()),
        "fact_sha256": "a" * 64,
        **changes,
    }


def row(**changes):
    return assess(CTAuditDutyInput.model_validate(sample(**changes)))["rows"][0]


@pytest.mark.parametrize(
    "amount,expected",
    [
        ("0", False),
        ("49999999.99", False),
        ("50000000", False),
        ("50000000.01", True),
        ("99999999999999999999.99", True),
    ],
)
def test_strict_threshold_uses_exact_aed_and_never_establishes_entity_audit_exemption(
    amount, expected
):
    result = row(revenue_aed=amount)
    assert result["audited_financial_statements_required"] is expected
    assert not result["entity_audit_exemption_established"] and result["state"] == "SUPPORTED"


def test_nonresident_worldwide_revenue_is_not_substituted_for_pe_nexus_revenue():
    result = row(residency="non_resident", revenue_basis="whole_person", revenue_aed="90000000")
    assert result["audited_financial_statements_required"] is None
    assert "ASSESSED_REVENUE_BASIS_REQUIRED_FOR_RESIDENCY" in result["issues"]
    assert (
        row(residency="non_resident", revenue_basis="uae_pe_and_nexus", revenue_aed="50000000.01")[
            "audited_financial_statements_required"
        ]
        is True
    )


@pytest.mark.parametrize("amount", [None, "0", "50000000.01"])
@pytest.mark.parametrize(
    "flag,kind",
    [
        ("tax_group", "AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS"),
        ("qualifying_free_zone_person", "AUDITED_FINANCIAL_STATEMENTS"),
    ],
)
def test_group_and_qfzp_duties_do_not_depend_on_revenue(amount, flag, kind):
    result = row(**{flag: "assessed_yes", "revenue_aed": amount})
    assert (
        result["audited_financial_statements_required"] is True and result["statement_type"] == kind
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"taxable_person": "unassessed"},
        {"tax_group": "unassessed"},
        {"qualifying_free_zone_person": "unassessed"},
        {"revenue_aed": None},
        {"residency": "unassessed"},
        {"revenue_basis": "unassessed"},
        {"other_rule_changes": "unresolved"},
    ],
)
def test_missing_material_facts_or_operative_rule_changes_remain_unresolved(changes):
    result = row(**changes)
    assert (
        result["audited_financial_statements_required"] is None
        and result["state"] == "EXCEPTION"
        and result["issues"]
    )


def test_known_positive_duty_does_not_hide_unknown_statement_type():
    result = row(tax_group="unassessed", revenue_aed="50000000.01")
    assert result["audited_financial_statements_required"] is True
    assert (
        result["statement_type"] == "AUDIT_REQUIRED_STATEMENT_TYPE_UNRESOLVED"
        and result["state"] == "EXCEPTION"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"taxable_person": "assessed_no", "tax_group": "assessed_yes"},
        {"taxable_person": "assessed_no", "qualifying_free_zone_person": "assessed_yes"},
        {"tax_group": "assessed_yes", "qualifying_free_zone_person": "assessed_yes"},
    ],
)
def test_conflicting_classifications_are_not_clean_compliance(changes):
    result = row(**changes)
    assert result["state"] == "EXCEPTION" and result["issues"]


def test_designated_distribution_does_not_claim_complete_additional_procedures():
    assert (
        row(
            qualifying_free_zone_person="assessed_yes", designated_zone_distribution="assessed_yes"
        )["additional_qfzp_procedures"]
        == "SEPARATE_AUTHORITY_PROCEDURES_REQUIRE_ASSESSMENT"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_period_start": "2024-12-31"},
        {"tax_period_end": "2027-01-01"},
        {"adopted_from": "2026-01-02"},
        {"adopted_through": "2026-09-30"},
        {
            "assessed_on": "2025-03-24",
            "tax_period_start": "2025-01-01",
            "tax_period_end": "2025-03-01",
        },
        {"revenue_aed": "-0.01"},
        {"revenue_aed": "NaN"},
        {"revenue_aed": 50000000.01},
        {"revenue_aed": True},
        {"currency": "USD"},
        {"fact_assessment": " " * 20},
        {"registration_reference": " "},
        {"tax_period_start": "2026-01-01T00:00:00Z"},
        {"tax_period_start": True},
        {"revenue_aed": "50000000.001"},
    ],
)
def test_period_currency_and_amount_boundaries_fail_closed(changes):
    with pytest.raises(ValueError):
        CTAuditDutyInput.model_validate(sample(**changes))


def test_dated_positive_requirement_does_not_clear_unresolved_operative_changes():
    result = row(revenue_aed="50000000.01", other_rule_changes="unresolved")
    assert result["dated_source_requirement"] is True
    assert result["audited_financial_statements_required"] is None


def test_assessed_non_taxable_scope_does_not_establish_other_law_audit_exemption():
    result = row(taxable_person="assessed_no", revenue_aed="90000000")
    assert result["audited_financial_statements_required"] is False
    assert result["entity_audit_exemption_established"] is False


def test_rule_and_fact_document_cannot_be_the_same_original():
    data = sample()
    data["fact_evidence_version_id"] = data["rule_evidence_version_id"]
    with pytest.raises(ValueError, match="separate"):
        CTAuditDutyInput.model_validate(data)


def test_retained_source_bytes_match_adopted_original():
    import hashlib
    from pathlib import Path

    from app.modules.country_workflows.uae_ct_audit_duty import SOURCE_SHA256

    original = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/authority-references/uae-ct-audit-2025/md84-2025-original.pdf"
    )
    assert hashlib.sha256(original.read_bytes()).hexdigest() == SOURCE_SHA256


@pytest.mark.parametrize(
    "amount", [None, "0", "50000000", "50000000.01", "99999999999999999999.99"]
)
def test_ctp007_whole_period_member_has_no_standalone_ct_audit_regardless_of_revenue(amount):
    result = row(tax_group_member="assessed_yes", revenue_aed=amount)
    assert result["audited_financial_statements_required"] is False
    assert result["statement_type"] == "NO_STANDALONE_CT_AUDIT_DUTY_FOR_ASSESSED_GROUP_MEMBER"
    assert result["tax_group_member"] is True
    assert result["entity_audit_exemption_established"] is False
    assert result["revenue_exceeds_threshold"] is None
    assert (
        result["tax_group_procedures"] == "SEPARATE_FTA_FORM_FRAMEWORK_AND_SUBMISSION_REQUIREMENTS"
    )
    assert result["state"] == "SUPPORTED"


@pytest.mark.parametrize("amount", [None, "0", "50000000.01"])
def test_unknown_membership_does_not_imply_standalone_audit_or_exemption(amount):
    result = row(tax_group_member="unassessed", revenue_aed=amount)
    assert result["audited_financial_statements_required"] is None
    assert result["issues"] == ["TAX_GROUP_MEMBERSHIP_UNASSESSED"]


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_group": "assessed_yes"},
        {"qualifying_free_zone_person": "assessed_yes"},
        {"taxable_person": "assessed_no"},
        {"residency": "non_resident"},
    ],
)
def test_member_conflicts_never_issue_false_exemption(changes):
    result = row(tax_group_member="assessed_yes", **changes)
    assert result["audited_financial_statements_required"] is None
    assert result["dated_source_requirement"] is None
    assert "TAX_GROUP_MEMBER_CLASSIFICATION_CONFLICT" in result["issues"]


@pytest.mark.parametrize(
    "changes",
    [
        {"tax_group": "unassessed"},
        {"qualifying_free_zone_person": "unassessed"},
        {"residency": "unassessed"},
    ],
)
def test_member_scope_needs_explicit_consistent_classifications(changes):
    result = row(tax_group_member="assessed_yes", **changes)
    assert result["audited_financial_statements_required"] is None
    assert "TAX_GROUP_MEMBER_SCOPE_UNASSESSED" in result["issues"]


def test_group_audit_is_not_conditional_on_standalone_member_status():
    result = row(tax_group="assessed_yes", tax_group_member="unassessed", revenue_aed=None)
    assert result["audited_financial_statements_required"] is True
    assert result["statement_type"] == "AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS"


@pytest.mark.parametrize("role", ["rule_evidence_version_id", "fact_evidence_version_id"])
def test_clarification_must_have_its_own_document_version(role):
    data = sample()
    data["clarification_evidence_version_id"] = data[role]
    with pytest.raises(ValueError, match="separate"):
        CTAuditDutyInput.model_validate(data)


def test_fact_hash_cannot_be_original_clarification():
    from app.modules.country_workflows.uae_ct_audit_duty import CLARIFICATION_SHA256

    with pytest.raises(ValueError, match="separate"):
        CTAuditDutyInput.model_validate(sample(fact_sha256=CLARIFICATION_SHA256))


async def test_old_contract_cannot_remain_current_or_be_approved():
    from types import SimpleNamespace

    from app.modules.country_workflows.review import approval_error
    from app.modules.intelligence.service import current

    body = {
        "workflow": "uae-ct-audit-duty",
        "contract": "uae-ct-audited-statements-md84-2025/1",
        "ct_audit_document_binding": "RETAINED_DOCUMENT_BYTES_VERIFIED",
    }
    assert "Regenerate" in approval_error(body)
    tenant = uuid4()
    assert not await current(
        None,
        SimpleNamespace(tenant_id=tenant),
        SimpleNamespace(tenant_id=tenant, kind="country-workflow", body=body),
    )


def test_original_ctp007_hash_matches_bound_source():
    import hashlib
    from pathlib import Path

    from app.modules.country_workflows.uae_ct_audit_duty import CLARIFICATION_SHA256

    original = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/authority-references/uae-tax-group-afs-2026-10-31/ctp007-tax-group-financial-statements-bilingual.pdf"
    )
    assert hashlib.sha256(original.read_bytes()).hexdigest() == CLARIFICATION_SHA256

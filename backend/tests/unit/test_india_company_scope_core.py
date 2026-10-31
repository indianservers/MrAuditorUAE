"""Synthetic legal boundary candidates; no source adoption or professional opinion."""

from datetime import date, timedelta

import pytest

from app.modules.country_workflows.india_company_scope_core import evaluate_company_scope


def facts(**changes):
    return {
        "country": "IN",
        "entity_reference": "SYNTHETIC-INDIA-COMPANY",
        "financial_period_start": "2025-04-01",
        "financial_period_end": "2026-03-31",
        "report_date": "2026-06-30",
        "is_indian_company": True,
        "is_foreign_company": False,
        "is_private_company": True,
        "is_public_company": False,
        "banking_company": False,
        "insurance_company": False,
        "section8_company": False,
        "one_person_company": False,
        "holding_or_subsidiary": False,
        "holding_or_subsidiary_of_public_company": False,
        "governed_by_special_act": False,
        "other_special_exemption_claimed": False,
        "small_paid_up_capital": "100000000",
        "preceding_financial_year_turnover": "1000000000",
        "caro_capital_reserves_and_surplus": "20000000",
        "caro_max_bank_fi_borrowings": "20000000",
        "caro_current_year_total_revenue": "110000000",
        "latest_audited_turnover": "600000000",
        "max_bank_fi_body_corporate_borrowings": "300000000",
        "financial_statements_filing_default": False,
        "annual_return_filing_default": False,
        "statement_scope": "standalone",
        "facts_assessment": "SYNTHETIC independently assessed facts, no client qualification",
        **changes,
    }


def candidate(**changes):
    return evaluate_company_scope(facts(**changes))["candidates"]


def test_small_company_limits_are_inclusive_and_do_not_exempt_the_company_audit():
    result = evaluate_company_scope(facts())
    values = result["candidates"]
    assert values["small_company"] is True
    assert values["companies_act_section139_audit"] is True
    assert values["caro2020_applies"] is False
    assert values["section143_3_i_ifc_reporting"] is False
    assert result["source_binding_verified"] is False
    assert result["ready_for_statutory_issue"] is False
    assert result["professional_conclusion"] == "NOT_DETERMINED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("small_paid_up_capital", "100000000.01"),
        ("preceding_financial_year_turnover", "1000000000.01"),
    ],
)
def test_exceeding_either_small_company_limit_reactivates_separate_duties(field, value):
    result = candidate(**{field: value})
    assert result["small_company"] is False
    assert result["caro2020_applies"] is True
    assert result["section143_3_i_ifc_reporting"] is True


@pytest.mark.parametrize(
    "field", ["holding_or_subsidiary", "section8_company", "governed_by_special_act"]
)
def test_small_company_structural_exclusions_are_independent_of_financial_size(field):
    assert candidate(**{field: True})["small_company"] is False


def test_public_company_is_never_small():
    assert candidate(is_public_company=True, is_private_company=False)["small_company"] is False


def test_preceding_turnover_is_not_replaced_by_current_caro_revenue():
    assert (
        candidate(
            preceding_financial_year_turnover="1000000000.01", caro_current_year_total_revenue="1"
        )["small_company"]
        is False
    )
    assert candidate(caro_current_year_total_revenue="999999999999")["small_company"] is True


def test_late_signing_date_does_not_backdate_the_december_definition():
    result = evaluate_company_scope(
        facts(financial_period_start="2024-04-01", financial_period_end="2025-03-31")
    )
    assert result["candidates"]["small_company"] is None
    assert result["basis"]["small_company_capital_limit_inr"] is None


def test_missing_current_amount_retains_known_limit_without_fabricating_zero():
    result = evaluate_company_scope(facts(small_paid_up_capital=None))
    assert result["candidates"]["small_company"] is None
    assert result["basis"]["small_company_capital_limit_inr"] == "100000000"


@pytest.mark.parametrize(
    "field", ["banking_company", "insurance_company", "section8_company", "one_person_company"]
)
def test_each_caro_entity_exclusion_can_resolve_without_irrelevant_financial_facts(field):
    result = candidate(
        **{
            field: True,
            "small_paid_up_capital": None,
            "preceding_financial_year_turnover": None,
            "caro_capital_reserves_and_surplus": None,
            "caro_max_bank_fi_borrowings": None,
            "caro_current_year_total_revenue": None,
        }
    )
    assert result["caro2020_applies"] is False


def test_caro_private_limits_are_inclusive_even_when_group_structure_prevents_small_status():
    result = candidate(
        holding_or_subsidiary=True,
        caro_capital_reserves_and_surplus="10000000",
        caro_max_bank_fi_borrowings="10000000",
        caro_current_year_total_revenue="100000000",
    )
    assert result["small_company"] is False
    assert result["caro2020_applies"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("caro_capital_reserves_and_surplus", "10000000.01"),
        ("caro_max_bank_fi_borrowings", "10000000.01"),
        ("caro_current_year_total_revenue", "100000000.01"),
    ],
)
def test_private_caro_exemption_requires_every_financial_test(field, value):
    changes = {
        "holding_or_subsidiary": True,
        "caro_capital_reserves_and_surplus": "10000000",
        "caro_max_bank_fi_borrowings": "10000000",
        "caro_current_year_total_revenue": "100000000",
        field: value,
    }
    assert candidate(**changes)["caro2020_applies"] is True


def test_public_parent_prevents_the_narrow_private_exemption():
    assert (
        candidate(
            holding_or_subsidiary=True,
            holding_or_subsidiary_of_public_company=True,
            caro_capital_reserves_and_surplus="1",
            caro_max_bank_fi_borrowings="1",
            caro_current_year_total_revenue="1",
        )["caro2020_applies"]
        is True
    )


def test_consolidated_caro_is_not_blanket_not_applicable():
    result = candidate(holding_or_subsidiary=True, statement_scope="consolidated")
    assert result["caro2020_applies"] is True
    assert result["caro_full_standalone_matters"] is False
    assert result["caro_consolidated_paragraph3_xxi"] is True


@pytest.mark.parametrize(
    "turnover,borrowings,required",
    [
        ("499999999.99", "249999999.99", False),
        ("500000000", "249999999.99", True),
        ("499999999.99", "250000000", True),
        ("300000000", "400000000", True),
        ("600000000", "100000000", True),
    ],
)
def test_ifc_uses_corrected_and_with_strict_limits(turnover, borrowings, required):
    result = candidate(
        holding_or_subsidiary=True,
        latest_audited_turnover=turnover,
        max_bank_fi_body_corporate_borrowings=borrowings,
    )
    assert result["section143_3_i_ifc_reporting"] is required


@pytest.mark.parametrize(
    "field", ["financial_statements_filing_default", "annual_return_filing_default"]
)
def test_filing_default_removes_private_exemption_even_for_a_small_company(field):
    assert candidate(**{field: True})["section143_3_i_ifc_reporting"] is True
    assert candidate(**{field: None})["section143_3_i_ifc_reporting"] is None


def test_other_exemption_claim_never_becomes_automatic_no_audit():
    result = candidate(other_special_exemption_claimed=True)
    assert result["companies_act_section139_audit"] is None
    assert result["caro2020_applies"] is None


def test_foreign_company_can_require_caro_without_inventing_its_audit_or_ifc_regime():
    result = candidate(is_indian_company=False, is_foreign_company=True)
    assert result["caro2020_applies"] is True
    assert result["companies_act_section139_audit"] is None
    assert result["section143_3_i_ifc_reporting"] is None


def test_historical_caro_and_audit_transitions_are_pending():
    result = candidate(financial_period_start="2020-04-01", financial_period_end="2021-03-31")
    assert result["caro2020_applies"] is None
    assert result["companies_act_section139_audit"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"country": "AE"},
        {"is_foreign_company": True},
        {"is_public_company": True},
        {"holding_or_subsidiary_of_public_company": True},
        {"report_date": "2025-01-01"},
        {"report_date": (date.today() + timedelta(days=1)).isoformat()},
        {"small_paid_up_capital": True},
        {"small_paid_up_capital": 100000000.01},
        {"small_paid_up_capital": "-1"},
        {"small_paid_up_capital": "NaN"},
    ],
)
def test_invalid_country_dates_money_or_contradictory_facts_are_rejected(changes):
    with pytest.raises(ValueError):
        evaluate_company_scope(facts(**changes))

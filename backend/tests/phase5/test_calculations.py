from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.ifrs.calculations import calculate
from app.modules.ifrs.schemas import ECL, Adjustment, Mapping, ReportingProfile


def test_large_journal_preserves_eight_decimal_places():
    value = "99999999999999999999.99999999"
    body = {
        "profile_id": "00000000-0000-0000-0000-000000000001",
        "adjustment_date": "2026-12-31",
        "currency": "AED",
        "standard": "IAS 1",
        "narration": "Synthetic precision benchmark",
        "legs": [
            {"account_code": "A", "debit": value},
            {"account_code": "B", "debit": value},
            {"account_code": "C", "credit": value},
            {"account_code": "D", "credit": value},
        ],
    }
    Adjustment.model_validate(body)
    body["legs"][-1]["credit"] = "99999999999999999999.99999998"
    with pytest.raises(ValidationError, match="balance exactly"):
        Adjustment.model_validate(body)


LEASE = {
    "commencement": "2026-01-01",
    "end_date": "2027-01-01",
    "annual_discount_rate": "0.1",
    "payments": [{"date": "2027-01-01", "amount": "1100"}],
    "recognition_assessment": "Synthetic recognized fixed lease",
    "options_assessment": "No renewal/termination options",
}
ECL_INPUT = {
    "approach": "general",
    "exposures": [{"reference": "SYN-1", "amount": "1000", "stage": 1}],
    "scenarios": [
        {
            "name": "base",
            "probability": "0.7",
            "pd_12_month": "0.1",
            "pd_lifetime": "0.3",
            "lgd": "0.5",
        },
        {
            "name": "stress",
            "probability": "0.3",
            "pd_12_month": "0.2",
            "pd_lifetime": "0.4",
            "lgd": "0.5",
        },
    ],
    "effective_interest_rate": "0",
    "historical_data_source": "Synthetic historical experience",
    "sicr_methodology": "Human documented significant increase criteria",
    "default_definition": "Human documented default policy",
    "write_off_policy": "Human approved recovery policy",
}


def test_lease_present_value_interest_and_advance():
    result = calculate("lease", LEASE)
    assert Decimal(result["initial_liability"]) == 1000
    assert Decimal(result["schedule"][0]["interest"]) == 100
    assert Decimal(result["schedule"][0]["closing"]) == 0
    assert Decimal(result["initial_rou"]) == 1000
    upfront = calculate(
        "lease",
        {**LEASE, "payments": [{"date": "2026-01-01", "amount": "100"}, *LEASE["payments"]]},
    )
    assert Decimal(upfront["initial_liability"]) == 1000 and Decimal(upfront["initial_rou"]) == 1100


@pytest.mark.parametrize("stage,expected", [(1, "65"), (2, "165"), (3, "500")])
def test_ecl_probability_weighted_stages(stage, expected):
    result = calculate(
        "ecl",
        {**ECL_INPUT, "exposures": [{"reference": "SYN-1", "amount": "1000", "stage": stage}]},
    )
    assert Decimal(result["total_ecl"]) == Decimal(expected)


def test_ecl_matrix_and_probabilities():
    result = calculate(
        "ecl",
        {**ECL_INPUT, "approach": "provision_matrix", "segment_loss_rates": {"default": "0.02"}},
    )
    assert Decimal(result["total_ecl"]) == 20
    with pytest.raises(ValidationError):
        ECL.model_validate({**ECL_INPUT, "scenarios": [ECL_INPUT["scenarios"][0]]})


def test_effective_interest_amortised_cost():
    result = calculate(
        "instrument",
        {
            "initial_amount": "1000",
            "initial_date": "2026-01-01",
            "cash_flows": [{"date": "2027-01-01", "amount": "1100"}],
            "classification": "amortised_cost",
            "business_model_and_sppi": "Synthetic hold-to-collect contractual principal and interest",
            "asset_or_liability": "asset",
        },
    )
    assert abs(Decimal(result["effective_annual_rate"]) - Decimal(".1")) < Decimal("0.0000000001")
    assert Decimal(result["closing"]) == 0


def test_revenue_allocation_and_contract_liability():
    result = calculate(
        "revenue",
        {
            "contract_reference": "SYN-C1",
            "contract_assessment": "Human validated contract and distinct obligations",
            "reporting_date": "2026-12-31",
            "fixed_price": "300",
            "constraint_rationale": "No variable consideration in this fixture",
            "billed_to_date": "250",
            "obligations": [
                {
                    "reference": "service",
                    "standalone_price": "200",
                    "recognition": "over_time",
                    "progress": "0.5",
                    "over_time_justification": "Human documented criteria and progress measure",
                },
                {
                    "reference": "goods",
                    "standalone_price": "100",
                    "recognition": "point_in_time",
                    "satisfied_on": "2026-12-31",
                },
            ],
        },
    )
    assert (
        Decimal(result["recognised_to_date"]) == 200 and Decimal(result["contract_liability"]) == 50
    )
    assert sum(Decimal(r["allocated_price"]) for r in result["schedule"]) == 300


def test_deferred_tax_assets_liabilities_losses():
    difference = {
        "reference": "asset",
        "jurisdiction": "Synthetic jurisdiction",
        "rate_source": "Approved synthetic rate",
        "rate_effective_date": "2026-01-01",
        "carrying_amount": "100",
        "tax_base": "80",
        "item_type": "asset",
        "tax_rate": "0.2",
        "recognition_rationale": "Human assessment",
    }
    result = calculate(
        "deferred-tax",
        {
            "current_tax_source": "Synthetic accounting provision",
            "differences": [
                difference,
                {
                    **difference,
                    "reference": "liability",
                    "item_type": "liability",
                    "recognise_dta": True,
                    "allocation": "oci",
                },
                {
                    **difference,
                    "reference": "loss",
                    "item_type": "tax_loss",
                    "tax_base": "50",
                    "recognise_dta": True,
                },
            ],
        },
    )
    assert Decimal(result["dtl"]) == 4 and Decimal(result["dta"]) == 14
    assert Decimal(result["movements"]["oci"]) == -4


def test_depreciation_roll_forward():
    result = calculate(
        "fixed-assets",
        {
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "assets": [
                {
                    "reference": "SYN-ASSET",
                    "cost": "3650",
                    "residual": "0",
                    "capitalisation_date": "2026-01-01",
                    "useful_life_years": "10",
                    "method": "straight_line",
                }
            ],
        },
    )
    assert (
        Decimal(result["total_depreciation"]) == 365 and Decimal(result["closing_carrying"]) == 3285
    )


def test_impairment_and_provision():
    result = calculate(
        "impairment",
        {
            "cgu": "SYN-CGU",
            "carrying_amount": "150",
            "cash_flows": ["110"],
            "discount_rate": "0.1",
            "fair_value_less_disposal_costs": "90",
            "goodwill_included": "20",
            "forecast_source": "Approved synthetic forecast",
        },
    )
    assert Decimal(result["value_in_use"]) == 100 and Decimal(result["impairment_loss"]) == 50
    assert Decimal(result["goodwill_loss"]) == 20 and Decimal(result["other_asset_loss"]) == 30
    provision = calculate(
        "provision",
        {
            "recognition": "provision",
            "obligation_assessment": "Human obligation assessment",
            "probability_assessment": "Human probability assessment",
            "best_estimate": "121",
            "settlement_years": "2",
            "discount_rate": "0.1",
            "opening": "80",
            "utilisation": "20",
        },
    )
    assert Decimal(provision["present_value"]) == 100 and Decimal(provision["closing"]) == 80


def test_no_duplicate_mapping_weight():
    import uuid

    with pytest.raises(ValidationError):
        Mapping.model_validate(
            {
                "profile_id": str(uuid.uuid4()),
                "rationale": "synthetic",
                "accounts": [
                    {
                        "account_code": "100",
                        "allocations": [
                            {
                                "line_code": "cash",
                                "label": "Cash",
                                "section": "assets",
                                "weight": "1.1",
                                "note": "cash",
                            }
                        ],
                    }
                ],
            }
        )


def test_ifrs19_ineligible_election_rejected():
    import uuid

    with pytest.raises(ValidationError):
        ReportingProfile.model_validate(
            {
                "snapshot_id": str(uuid.uuid4()),
                "presentation_currency": "AED",
                "technical_validation": "Synthetic",
                "ifrs19_elected": True,
                "is_subsidiary": False,
            }
        )

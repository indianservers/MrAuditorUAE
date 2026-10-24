"""Independent arithmetic examples; all names, values and evidence are synthetic."""

from copy import deepcopy
from decimal import Decimal as D

import pytest

from app.modules.ifrs.calculations import calculate

PROFILE = "00000000-0000-0000-0000-000000000001"
ASSET = {
    "reference": "SYN-A",
    "cost": "3650",
    "residual": "0",
    "capitalisation_date": "2026-01-01",
    "available_for_use_date": "2026-07-01",
    "available_for_use_evidence": "Synthetic commissioning certificate",
    "useful_life_years": "10",
    "method": "straight_line",
}
STOCK = {
    "profile_id": PROFILE,
    "period_start": "2026-01-01",
    "period_end": "2026-12-31",
    "method": "fifo",
    "policy_version": "SYN-policy/1",
    "items": [
        {
            "reference": "SYN-stock-site1",
            "uom": "each",
            "location": "SYN-site",
            "ownership": "owned",
            "opening_quantity": "10",
            "opening_unit_cost": "10",
            "receipts": [
                {
                    "reference": "SYN-R1",
                    "date": "2026-02-01",
                    "quantity": "10",
                    "unit_cost": "20",
                    "landed_cost": "20",
                    "evidence": "SYN invoice and freight",
                }
            ],
            "issues": [
                {
                    "reference": "SYN-I1",
                    "date": "2026-03-01",
                    "quantity": "12",
                    "evidence": "SYN dispatch",
                }
            ],
            "expected_closing_quantity": "8",
            "selling_price": "25",
            "completion_cost": "2",
            "selling_cost": "3",
            "nrv_evidence": "SYN comparable price less completion and sale costs",
        }
    ],
}
BENEFITS = {
    "profile_id": PROFILE,
    "policy_version": "SYN/1",
    "employment_framework": "uae_mainland",
    "framework_assessment": "Synthetic contract/regime review",
    "scheme": "defined_benefit",
    "measurement_source": "SYN supplied expert figures",
    "actuarial_report_reference": "SYN actuarial report",
    "opening_obligation": "100",
    "current_service_cost": "20",
    "net_interest": "5",
    "remeasurement_oci": "7",
    "settlements": "12",
    "closing_ledger_provision": "120",
    "payroll_expense": "1000",
    "opening_payroll_payable": "100",
    "payroll_deductions": "50",
    "confirmed_bank_payments": "900",
    "closing_payroll_ledger_payable": "160",
    "leave_bonus_accrual": "10",
}


def asset(**changes):
    return calculate(
        "fixed-assets",
        {
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "assets": [{**ASSET, **changes}],
        },
    )


def test_available_for_use_and_cip_and_disposal():
    assert D(asset()["total_depreciation"]) == 184  # July 1 through December 31.
    assert D(asset(construction_in_progress=True)["total_depreciation"]) == 0
    disposed = asset(disposal_date="2026-07-11", proceeds="3600")["schedule"][0]
    assert D(disposed["depreciation"]) == 10  # July 1–10; derecognition date excluded.
    assert D(disposed["disposal_gain_loss"]) == -40
    assert D(disposed["closing_carrying"]) == 0


def test_missing_commencement_is_explicitly_provisional():
    output = asset(available_for_use_date=None)
    assert output["issues"][0]["code"] == "AVAILABLE_FOR_USE_UNVERIFIED"
    assert output["issues"][0]["blocking"]


def test_estimate_change_is_prospective():
    output = asset(
        available_for_use_date="2026-01-01",
        estimate_change_date="2026-07-01",
        revised_remaining_life_years="5",
        revised_residual="0",
        estimate_change_rationale="SYN new estimate approved midyear",
    )["schedule"][0]
    # 181 days at 1/day; remaining 3469 over five years for 184 days.
    assert D(output["depreciation"]) == D("530.75123288")
    assert D(output["estimate_change"]["prior_charge"]) == 181


def test_invalid_asset_dates_rejected():
    with pytest.raises(ValueError, match="precedes"):
        asset(disposal_date="2025-12-31")
    with pytest.raises(ValueError, match="requires evidence"):
        asset(available_for_use_evidence="")


@pytest.mark.parametrize("classification", ["investment_property", "held_for_sale", "intangible"])
def test_special_asset_classifications_cannot_use_ppe_engine(classification):
    with pytest.raises(ValueError, match="specialist"):
        asset(asset_class=classification)


def test_residual_above_carrying_does_not_create_negative_depreciation():
    assert D(asset(residual="4000")["total_depreciation"]) == 0


@pytest.mark.parametrize(
    "method,issue_cost,closing,write_down",
    [("fifo", "144", "176", "16"), ("weighted_average", "192", "128", "0")],
)
def test_stock_cost_and_nrv_independent_examples(method, issue_cost, closing, write_down):
    body = {**STOCK, "method": method}
    output = calculate("inventory", body)
    row = output["schedule"][0]
    assert D(row["issue_cost"]) == D(issue_cost)
    assert D(row["closing_cost"]) == D(closing)
    assert D(row["closing_write_down"]) == D(write_down)
    assert D(row["cost_rollforward_difference"]) == 0
    assert not output["issues"]


def test_nrv_reversal_is_capped_at_remaining_original_write_down():
    body = deepcopy(STOCK)
    body["items"][0].update(selling_price="100", prior_write_down_remaining="30")
    row = calculate("inventory", body)["schedule"][0]
    assert D(row["write_down_expense_or_reversal"]) == -30
    assert D(row["accounting_carrying"]) == 176  # Never exceeds historical cost.


def test_custody_stock_excluded_and_quantity_variance_not_a_value_plug():
    body = deepcopy(STOCK)
    body["items"][0].update(ownership="custody_only", expected_closing_quantity="9")
    output = calculate("inventory", body)
    assert D(output["closing_carrying"]) == 0
    assert output["issues"][0]["code"] == "QUANTITY_RECONCILIATION"
    assert D(output["schedule"][0]["closing_quantity"]) == 8


@pytest.mark.parametrize("change", ["negative", "duplicate", "backdated", "ambiguous"])
def test_stock_fail_closed(change):
    body = deepcopy(STOCK)
    item = body["items"][0]
    if change == "negative":
        item["issues"][0]["quantity"] = "21"
    elif change == "duplicate":
        item["issues"][0]["reference"] = "SYN-R1"
    elif change == "backdated":
        item["receipts"][0]["date"] = "2025-12-31"
    else:
        item["issues"][0]["date"] = "2026-02-01"
    with pytest.raises(ValueError):
        calculate("inventory", body)


def test_stock_same_day_sequence_and_matched_transfer_preserve_actual_cost():
    body = deepcopy(STOCK)
    source = body["items"][0]
    source.update(
        sku="SYN-SKU",
        opening_quantity="10",
        opening_unit_cost="10",
        receipts=[],
        issues=[
            {
                "reference": "SYN-TO",
                "date": "2026-02-01",
                "sequence": 1,
                "quantity": "3",
                "evidence": "SYN transfer-out",
                "transaction_type": "transfer_out",
                "transfer_reference": "SYN-T1",
            }
        ],
        expected_closing_quantity="7",
    )
    target = {
        **deepcopy(source),
        "reference": "SYN-stock-site2",
        "location": "SYN-site2",
        "opening_quantity": "0",
        "opening_unit_cost": "0",
        "issues": [],
        "expected_closing_quantity": "3",
        "receipts": [
            {
                "reference": "SYN-TI",
                "date": "2026-02-01",
                "sequence": 2,
                "quantity": "3",
                "unit_cost": "10",
                "evidence": "SYN transfer-in",
                "transaction_type": "transfer_in",
                "transfer_reference": "SYN-T1",
            }
        ],
    }
    body["items"].append(target)
    output = calculate("inventory", body)
    assert output["transfers"][0]["state"] == "MATCHED"
    assert D(output["closing_carrying"]) == 100
    target["receipts"][0]["unit_cost"] = "11"
    output = calculate("inventory", body)
    assert output["issues"][0]["code"] == "TRANSFER_NOT_RECONCILED"
    # A supplied transfer cost difference remains an issue, never a balancing amount.
    assert D(output["schedule"][1]["closing_cost"]) == 33


def test_explicit_same_day_stock_order_is_reproducible():
    body = deepcopy(STOCK)
    body["items"][0]["issues"][0].update(date="2026-02-01", sequence=1)
    assert D(calculate("inventory", body)["schedule"][0]["closing_cost"]) == 176


def test_missing_valuation_inputs_cannot_be_invented():
    with pytest.raises(ValueError):
        calculate(
            "impairment",
            {
                "cgu": "SYN-CGU",
                "carrying_amount": "100",
                "cash_flows": ["10"],
                "forecast_source": "SYN incomplete forecast",
            },
        )


@pytest.mark.parametrize("framework", ["uae_mainland", "difc", "adgm"])
def test_benefits_bridge_never_substitutes_statutory_gratuity_for_ias19(framework):
    output = calculate(
        "employee-benefits",
        {**BENEFITS, "employment_framework": framework, "statutory_settlement_estimate": "999"},
    )
    assert D(output["obligation_rollforward"]["closing"]) == 120
    assert D(output["profit_loss_movement"]) == 25
    assert D(output["oci_movement"]) == 7
    assert D(output["payroll_bridge"]["difference"]) == 0
    assert not output["issues"]
    blocked = calculate("employee-benefits", {**BENEFITS, "actuarial_report_reference": ""})
    assert blocked["issues"][0]["code"] == "ACTUARIAL_INPUTS_MISSING"


def test_tax_loss_without_recovery_evidence_does_not_create_dta():
    output = calculate(
        "deferred-tax",
        {
            "current_tax_source": "SYN accounting only",
            "differences": [
                {
                    "reference": "SYN-loss",
                    "jurisdiction": "AE",
                    "rate_source": "SYN approved rate",
                    "rate_effective_date": "2026-01-01",
                    "carrying_amount": "0",
                    "tax_base": "100",
                    "item_type": "tax_loss",
                    "tax_rate": "0.09",
                    "recognise_dta": True,
                    "recognition_rationale": "Loss exists, but no recovery evidence",
                }
            ],
        },
    )
    assert D(output["dta"]) == 0
    assert D(output["schedule"][0]["unrecognised_dta"]) == 9
    assert output["issues"][0]["blocking"]

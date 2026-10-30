"""Synthetic committed-balance arithmetic, never inventory existence evidence."""

from copy import deepcopy
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest

from app.modules.country_workflows.inventory_performance import InventoryPerformanceInput, calculate


def fixture(currency="AED"):
    payload = {
        "currency": currency,
        "periods_comparable": True,
        "comparability_assessment": "SYNTHETIC assessed periods and accounting-policy comparability",
        "stock_change_threshold_percent": "10",
        "gp_change_threshold_pp": "3",
        "rounding_places": 2,
        "rounding_method": "HALF_UP",
        "label": "SYNTHETIC stock and GP review",
        "rationale": "Explicit selected accounts and independently controlled totals",
    }
    balances = {}
    for side, amounts in (("current", ("120", "1000", "800")), ("prior", ("100", "800", "600"))):
        selection = {"snapshot_id": str(uuid4())}
        lines = []
        for metric, amount in zip(("inventory", "revenue", "cost_of_sales"), amounts, strict=True):
            identifier = str(uuid4())
            selection[metric] = {
                "account_ids": [identifier],
                "expected_accounts": 1,
                "expected_amount": amount,
                "assessment": "SYNTHETIC independent classification, sign and complete account scope",
            }
            opening = Decimal("-50") if metric == "revenue" else Decimal("100")
            debit = (
                Decimal(amount) - opening
                if metric == "inventory"
                else Decimal(amount)
                if metric == "cost_of_sales"
                else Decimal(0)
            )
            credit = Decimal(amount) if metric == "revenue" else Decimal(0)
            lines.append(
                {
                    "id": identifier,
                    "code": metric,
                    "name": "SYN " + metric,
                    "opening": str(opening),
                    "debit": str(debit),
                    "credit": str(credit),
                    "closing": str(opening + debit - credit),
                }
            )
        payload[side] = selection
        balances[side] = {
            "functional_currency": currency,
            "balanced": True,
            "debit_credit_difference": "0",
            "lines": lines,
        }
    periods = {
        "current": {"start": "2026-01-01", "end": "2026-12-31"},
        "prior": {"start": "2025-01-01", "end": "2025-12-31"},
    }
    return payload, balances, periods


@pytest.mark.parametrize("currency", ["AED", "INR"])
def test_stock_ties_to_closing_gp_excludes_openings_and_preserves_exact_controls(currency):
    payload, balances, periods = fixture(currency)
    retained = deepcopy(balances)
    out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert balances == retained
    rows = {row["metric"]: row for row in out["rows"]}
    assert rows["inventory"]["change_raw"] == "20.0"
    assert rows["revenue"]["current_raw"] == "1000"
    assert rows["cost_of_sales"]["current_raw"] == "800"
    assert rows["gross_profit"]["current_raw"] == "200"
    assert rows["gp_margin_percent"]["current_raw"] == "20.0"
    assert rows["gp_margin_percent"]["prior_raw"] == "25.00"
    assert rows["gp_margin_percent"]["change_display"] == "-5.00"
    assert "GP_MARGIN_CHANGE_EXCEEDS_ASSESSED_THRESHOLD" in rows["gp_margin_percent"]["exceptions"]
    assert len(out["inventory_performance_links"]) == 6
    assert len(out["inventory_performance_controls"]) == 6
    assert not out["blocked"] and out["statutory_calculation_qualified"] is False


def test_movement_reversals_are_not_absolute_values():
    payload, balances, periods = fixture()
    row = balances["current"]["lines"][1]
    row.update(debit="1100", credit="1000", closing="50")
    payload["current"]["revenue"]["expected_amount"] = "-100"
    out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert out["rows"][1]["current_raw"] == "-100"
    assert out["rows"][-1]["current_raw"] is None
    assert "GP_MARGIN_UNDEFINED_WITHOUT_POSITIVE_REVENUE" in out["rows"][-1]["exceptions"]


@pytest.mark.parametrize(
    "side,metric",
    [
        (side, metric)
        for side in ("current", "prior")
        for metric in ("inventory", "revenue", "cost_of_sales")
    ],
)
def test_each_independent_component_control_is_verified(side, metric):
    payload, balances, periods = fixture()
    payload[side][metric]["expected_amount"] = "1"
    with pytest.raises(ValueError, match="Independent"):
        calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)


def test_absent_account_does_not_become_zero():
    payload, balances, periods = fixture()
    balances["prior"]["lines"].pop()
    with pytest.raises(ValueError, match="absent"):
        calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)


def test_zero_inventory_requires_a_retained_account_and_explicit_assessment():
    payload, balances, periods = fixture()
    payload["prior"]["inventory"]["expected_amount"] = "0"
    balances["prior"]["lines"][0].update(opening="0", debit="0", credit="0", closing="0")
    with pytest.raises(ValueError, match="Zero inventory"):
        InventoryPerformanceInput.model_validate(payload)
    payload["prior"]["inventory"]["nil_inventory_assessment"] = (
        "SYNTHETIC zero ledger balance independently assessed; no physical conclusion"
    )
    out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert out["rows"][0]["prior_raw"] == "0" and out["rows"][0]["change_raw"] is None
    payload["prior"]["inventory"]["account_ids"] = []
    with pytest.raises(ValueError):
        InventoryPerformanceInput.model_validate(payload)


def test_zero_net_revenue_never_produces_a_fake_zero_gp_percentage():
    payload, balances, periods = fixture()
    payload["current"]["revenue"]["expected_amount"] = "0"
    balances["current"]["lines"][1].update(debit="1000", credit="1000", closing="-50")
    out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert out["rows"][-1]["current_display"] is None
    assert out["rows"][-1]["change_display"] is None


def test_unbalanced_source_and_unassessed_comparability_block_approval():
    payload, balances, periods = fixture()
    balances["prior"]["balanced"] = False
    balances["prior"]["debit_credit_difference"] = "10"
    assert calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)[
        "blocked"
    ]
    balances["prior"]["balanced"] = True
    payload["periods_comparable"] = False
    out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert out["blocked"] and all(row["change_raw"] is None for row in out["rows"])


def test_duplicate_or_overlapping_account_scope_and_wrong_currency_are_rejected():
    payload, balances, periods = fixture()
    payload["current"]["inventory"]["account_ids"] = payload["current"]["revenue"]["account_ids"]
    with pytest.raises(ValueError, match="cannot overlap"):
        InventoryPerformanceInput.model_validate(payload)
    payload, balances, periods = fixture()
    balances["prior"]["functional_currency"] = "USD"
    with pytest.raises(ValueError, match="functional currency"):
        calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)


def test_arithmetic_context_cannot_round_source_account_controls():
    payload, balances, periods = fixture()
    with localcontext() as context:
        context.prec = 6
        out = calculate(InventoryPerformanceInput.model_validate(payload), balances, periods)
    assert out["rows"][-1]["change_display"] == "-5.00"

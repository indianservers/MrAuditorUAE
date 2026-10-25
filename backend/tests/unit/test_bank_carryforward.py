from copy import deepcopy

import pytest

from app.modules.country_workflows.bank_carryforward import CarryforwardInput, source_rows
from app.modules.country_workflows.bank_clearance import clearances
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_bank_clearance import calculate, population


def options(**changes):
    return CarryforwardInput.model_validate({
        "label": "SYNTHETIC carried residuals", "expected_rows": 1,
        "positive_total": "0", "negative_total": "-60",
        "assessment": "Independent retained window completeness and unresolved reversals assessed",
        **changes,
    })


def carry(p, **changes):
    body = calculate(p, review_through="2026-07-31")
    sources = {role: {"rows": rows} for role, rows in p.items()}
    return source_rows(body, sources, options(**changes))


@pytest.mark.parametrize("currency", ["AED", "INR"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_all_residuals_keep_original_date_and_signed_controls(currency, sign):
    p = population(currency, sign)
    original = deepcopy(p)
    controls = {"negative_total": "-60" if sign < 0 else "0", "positive_total": "60" if sign > 0 else "0"}
    rows, totals = carry(p, **controls)
    assert p == original
    assert totals == {currency: str(60 * sign)}
    assert rows[0]["date"] == "2026-06-20"
    assert rows[0]["balance_date"] == "2026-07-31"
    assert rows[0]["amount"] == str(60 * sign)
    assert rows[0]["previous_outstanding_amount"] == str(100 * sign)
    assert rows[0]["cleared_in_previous_window"] == "40"
    assert rows[0]["original_outstanding_amount"] == str(100 * sign)
    assert rows[0]["evidence_reference"] == "SYN-BRS"


def test_next_window_clears_only_remaining_amount_without_resetting_age():
    p = population()
    rows, _ = carry(p)
    next_p = deepcopy(p)
    next_p["outstanding"] = rows
    next_p["statement"][0].update(id="AUG", date="2026-08-05", amount="-60")
    next_p["allocations"][0].update(transaction_id="AUG", amount="40")
    params = WorkflowInput.model_validate({**calculate(p)["parameters"], "as_of": "2026-07-31", "review_through": "2026-08-31"})
    next_body = {**clearances(params, next_p), "workflow": params.workflow, "parameters": params.model_dump(mode="json")}
    next_rows, _ = source_rows(next_body, {role: {"rows": records} for role, records in next_p.items()}, options(negative_total="-20"))
    assert next_rows[0]["amount"] == "-20"
    assert next_rows[0]["balance_date"] == "2026-08-31"
    assert next_rows[0]["date"] == next_rows[0]["original_outstanding_date"] == "2026-06-20"
    assert next_rows[0]["original_outstanding_amount"] == "-100"
    assert next_body["rows"][0]["age_at_reporting_days"] == 41
    next_p["allocations"][0]["amount"] = "100"
    with pytest.raises(ValueError, match="overallocated"):
        clearances(params, next_p)


def test_opposing_residuals_do_not_disappear_under_zero_net_control():
    p = population()
    p["outstanding"].append({**p["outstanding"][0], "id": "O2", "reference": "DEPOSIT", "amount": "60"})
    rows, totals = carry(p, expected_rows=2, positive_total="60")
    assert len(rows) == 2 and totals == {"AED": "0"}
    with pytest.raises(ValueError, match="directional amount controls"):
        carry(p, expected_rows=2, positive_total="0", negative_total="0")


def test_fully_cleared_population_can_be_explicitly_nil():
    p = population()
    p["allocations"][0]["amount"] = "100"
    rows, totals = carry(p, expected_rows=0, negative_total="0")
    assert rows == [] and totals == {"AED": "0"}


@pytest.mark.parametrize("changes", [{"expected_rows": 0}, {"negative_total": "-59"}, {"positive_total": "1"}])
def test_independent_controls_cannot_be_inferred_or_mismatched(changes):
    with pytest.raises(ValueError, match="Independent carry-forward"):
        carry(population(), **changes)


def test_saved_clearance_must_recompute_from_retained_sources():
    p = population()
    body = calculate(p, review_through="2026-07-31")
    body["rows"][0]["remaining_after_review"] = "0"
    with pytest.raises(ValueError, match="recalculate first"):
        source_rows(body, {role: {"rows": records} for role, records in p.items()}, options())


@pytest.mark.parametrize("field,value", [("positive_total", "-1"), ("negative_total", "1"), ("assessment", "          ")])
def test_controls_require_correct_direction_and_meaningful_assessment(field, value):
    with pytest.raises(ValueError):
        options(**{field: value})


def test_maximum_retained_population_carries_every_residual_without_truncation():
    p = population()
    p["outstanding"] = [{**p["outstanding"][0], "id": f"O{index}", "reference": f"SYN-CHEQUE-{index}"} for index in range(5000)]
    p["allocations"][0]["outstanding_id"] = "O0"
    rows, totals = carry(p, expected_rows=5000, negative_total="-499960")
    assert len(rows) == 5000 and totals == {"AED": "-499960"}
    assert rows[0]["amount"] == "-60"
    assert rows[-1]["id"] == "O4999" and rows[-1]["amount"] == "-100"
    assert all(row["date"] == "2026-06-20" and row["balance_date"] == "2026-07-31" for row in rows)

"""Synthetic independently specified project-lot attribution and rejection cases."""

from copy import deepcopy
from decimal import Decimal as D

import pytest

from app.modules.ifrs.calculations import calculate
from tests.unit.test_inventory_identified_units import body, unit


def layer(reference, quantity, cost):
    return {
        "reference": reference,
        "quantity": quantity,
        "unit_cost": cost,
        "evidence": "SYN independently assessed acquisition " + reference,
    }


def allocation(reference, quantity):
    return {
        "layer_reference": reference,
        "quantity": quantity,
        "evidence": "SYN physical issue attribution " + reference,
    }


def project():
    item = unit("SYN-project-A")
    item.update(
        identification_basis="segregated_project_lot",
        identification_assessment="SYN non-interchangeable purchased project lot, assessed separately",
        opening_quantity="5",
        opening_unit_cost="0",
        opening_cost_evidence="",
        opening_layers=[layer("opening-A", "2", "10"), layer("opening-B", "3", "30")],
        receipts=[
            {
                "reference": "purchase-C",
                "date": "2026-02-01",
                "quantity": "4",
                "unit_cost": "50",
                "landed_cost": "4",
                "evidence": "SYN invoice and freight",
            }
        ],
        issues=[
            {
                "reference": "dispatch",
                "date": "2026-03-01",
                "quantity": "3",
                "evidence": "SYN issue acknowledgement",
                "cost_allocations": [allocation("opening-B", "2"), allocation("purchase-C", "1")],
            }
        ],
        expected_closing_quantity="6",
    )
    return item


def test_issue_uses_named_costs_not_fifo_or_average():
    result = calculate("inventory", body(project()))
    row = result["schedule"][0]
    assert D(row["opening_cost"]) == 110
    assert D(row["receipt_cost"]) == 204
    assert D(row["issue_cost"]) == 111
    assert D(row["closing_cost"]) == D(result["closing_carrying"]) == 203
    assert D(row["cost_rollforward_difference"]) == 0
    assert [D(r["remaining_cost"]) for r in result["identified_layers"]] == [20, 30, 153]
    assert [D(r["cost"]) for r in result["identified_allocations"]] == [60, 51]
    assert all(
        r["source_evidence"] and r["allocation_evidence"] for r in result["identified_allocations"]
    )


@pytest.mark.parametrize(
    "change", ["missing", "future", "overdraw", "duplicate", "wrong-total", "blank-evidence"]
)
def test_invalid_issue_allocations_rejected(change):
    item = project()
    issue = item["issues"][0]
    if change == "missing":
        issue["cost_allocations"] = []
    if change == "future":
        issue["date"] = "2026-01-15"
    if change == "overdraw":
        issue["cost_allocations"] = [allocation("opening-A", "3")]
    if change == "duplicate":
        issue["cost_allocations"] = [allocation("opening-B", "1"), allocation("opening-B", "2")]
    if change == "wrong-total":
        issue["cost_allocations"][0]["quantity"] = "1"
    if change == "blank-evidence":
        issue["cost_allocations"][0]["evidence"] = " "
    with pytest.raises(ValueError):
        calculate("inventory", body(item))


@pytest.mark.parametrize(
    "change",
    [
        "opening-quantity",
        "opening-average",
        "duplicate-layer",
        "movement-collision",
        "blank-source",
    ],
)
def test_invalid_opening_layers_rejected(change):
    item = project()
    if change == "opening-quantity":
        item["opening_quantity"] = "6"
    if change == "opening-average":
        item["opening_unit_cost"] = "22"
    if change == "duplicate-layer":
        item["opening_layers"][1]["reference"] = "opening-A"
    if change == "movement-collision":
        item["opening_layers"][0]["reference"] = "dispatch"
    if change == "blank-source":
        item["opening_layers"][0]["evidence"] = " "
    with pytest.raises(ValueError):
        calculate("inventory", body(item))


@pytest.mark.parametrize("method", ["fifo", "weighted_average"])
def test_other_methods_do_not_silently_ignore_project_allocations(method):
    data = body(project())
    data["method"] = method
    with pytest.raises(ValueError):
        calculate("inventory", data)


def test_fractional_issue_and_complete_residual_consumption():
    item = project()
    item.update(opening_quantity="0", opening_layers=[], expected_closing_quantity="0")
    item["receipts"] = [
        {
            "reference": "C",
            "date": "2026-01-01",
            "quantity": "3",
            "unit_cost": "0",
            "landed_cost": "1",
            "evidence": "SYN attributable total cost",
        }
    ]
    item["issues"] = [
        {
            "reference": f"I{i}",
            "date": "2026-02-01",
            "sequence": i,
            "quantity": "1",
            "evidence": "SYN separate physical attribution",
            "cost_allocations": [allocation("C", "1")],
        }
        for i in range(3)
    ]
    result = calculate("inventory", body(item))
    assert D(result["schedule"][0]["issue_cost"]) == 1
    assert D(result["identified_layers"][0]["remaining_cost"]) == 0
    assert (
        sum((D(a["cost"]) for a in result["identified_allocations"]), D(0)).quantize(
            D("0.00000001")
        )
        == 1
    )


def project_transfer():
    source = project()
    source.update(receipts=[], expected_closing_quantity="4")
    source["issues"] = [
        {
            "reference": "out",
            "date": "2026-02-01",
            "quantity": "1",
            "transaction_type": "transfer_out",
            "transfer_reference": "T",
            "evidence": "SYN outward physical lot",
            "cost_allocations": [allocation("opening-B", "1")],
        }
    ]
    target = deepcopy(source)
    target.update(
        reference="project-A-location-B",
        location="Abu Dhabi",
        opening_quantity="0",
        opening_layers=[],
        issues=[],
        expected_closing_quantity="1",
    )
    target["receipts"] = [
        {
            "reference": "in",
            "date": "2026-02-01",
            "sequence": 1,
            "quantity": "1",
            "unit_cost": "30",
            "evidence": "SYN receiving physical lot",
            "transaction_type": "transfer_in",
            "transfer_reference": "T",
        }
    ]
    return source, target


def test_partial_project_transfer_preserves_identity_and_cost():
    result = calculate("inventory", body(*project_transfer()))
    assert result["issues"] == []
    assert result["transfers"][0]["state"] == "MATCHED"
    assert D(result["closing_carrying"]) == 110


def test_project_transfer_cannot_substitute_another_project():
    source, target = project_transfer()
    target["identification_reference"] = "different-project"
    result = calculate("inventory", body(source, target))
    assert result["transfers"][0]["state"] == "BLOCKED"


def test_lot_custody_exclusion_and_per_lot_nrv():
    item = project()
    item["selling_price"] = "10"
    result = calculate("inventory", body(item))
    assert D(result["closing_carrying"]) == 60
    assert D(result["write_down_movement"]) == 143
    item["ownership"] = "custody_only"
    assert D(calculate("inventory", body(item))["closing_carrying"]) == 0

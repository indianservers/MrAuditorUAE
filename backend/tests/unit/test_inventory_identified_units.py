"""Synthetic, independently specified identified-unit arithmetic and custody cases."""

from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.ifrs.calculations import calculate


def unit(reference="serial-A", cost="100"):
    return {
        "reference": reference,
        "sku": "machine",
        "uom": "each",
        "location": "Dubai",
        "ownership": "owned",
        "identification_reference": reference,
        "identification_assessment": "Individually tracked non-interchangeable machine",
        "opening_cost_evidence": "SYN independently checked acquisition invoice",
        "opening_quantity": "1",
        "opening_unit_cost": cost,
        "expected_closing_quantity": "1",
        "selling_price": "500",
        "nrv_evidence": "SYN individual sale quotation",
    }


def body(*items):
    return {
        "profile_id": "00000000-0000-0000-0000-000000000001",
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "method": "specific_identification",
        "policy_version": "SYN-assessed-policy/1",
        "items": list(items or [unit()]),
    }


def issue(**extra):
    return {
        "reference": "dispatch",
        "date": "2026-02-01",
        "quantity": "1",
        "evidence": "SYN serial-number dispatch acknowledgement",
        **extra,
    }


def test_selected_expensive_unit_is_not_averaged_or_fifo_pooled():
    cheap, expensive = unit("A", "100"), unit("B", "300")
    expensive.update(issues=[issue()], expected_closing_quantity="0")
    result = calculate("inventory", body(cheap, expensive))
    assert Decimal(result["closing_carrying"]) == 100
    assert Decimal(result["schedule"][1]["issue_cost"]) == 300
    assert result["movements"][0]["identification_reference"] == "B"
    assert all(Decimal(r["cost_rollforward_difference"]) == 0 for r in result["schedule"])


def transfer():
    source = unit()
    source.update(
        issues=[issue(transaction_type="transfer_out", transfer_reference="T")],
        expected_closing_quantity="0",
    )
    target = deepcopy(source)
    target.update(
        reference="Abu Dhabi serial-A",
        location="Abu Dhabi",
        opening_quantity="0",
        opening_unit_cost="0",
        opening_cost_evidence="",
        issues=[],
        expected_closing_quantity="1",
        receipts=[
            {
                "reference": "in",
                "date": "2026-02-01",
                "sequence": 1,
                "quantity": "1",
                "unit_cost": "100",
                "evidence": "SYN receiving serial acknowledgement",
                "transaction_type": "transfer_in",
                "transfer_reference": "T",
            }
        ],
    )
    return source, target


def test_transfer_preserves_actual_unit_cost_and_identity():
    result = calculate("inventory", body(*transfer()))
    assert result["issues"] == []
    assert result["transfers"][0]["state"] == "MATCHED"
    assert Decimal(result["closing_carrying"]) == 100


@pytest.mark.parametrize(
    "field,value",
    [
        ("sku", " "),
        ("identification_reference", " "),
        ("identification_assessment", "short"),
        ("opening_cost_evidence", " "),
        ("opening_quantity", "2"),
    ],
)
def test_incomplete_or_pooled_identification_rejected(field, value):
    item = unit()
    item[field] = value
    with pytest.raises(ValueError):
        calculate("inventory", body(item))


def test_duplicate_physical_unit_across_locations_rejected():
    other = unit()
    other.update(reference="another-location", location="Mumbai")
    with pytest.raises(ValueError, match="duplicated"):
        calculate("inventory", body(unit(), other))


def test_transfer_cannot_create_an_unacquired_unit():
    _, target = transfer()
    with pytest.raises(ValueError, match="original acquisition"):
        calculate("inventory", body(target))


def test_overlapping_location_custody_rejected():
    source, target = transfer()
    target["receipts"][0]["date"] = "2026-01-15"
    with pytest.raises(ValueError, match="overlapping"):
        calculate("inventory", body(source, target))


def test_wrong_transferred_cost_is_blocking_without_balancing():
    source, target = transfer()
    target["receipts"][0]["unit_cost"] = "101"
    result = calculate("inventory", body(source, target))
    assert result["transfers"][0]["state"] == "BLOCKED"
    assert result["issues"][0]["code"] == "TRANSFER_NOT_RECONCILED"


def test_custody_only_stock_is_not_an_accounting_asset():
    item = unit()
    item["ownership"] = "custody_only"
    assert Decimal(calculate("inventory", body(item))["closing_carrying"]) == 0


def test_individual_nrv_does_not_offset_another_units_write_down():
    impaired, other = unit("A", "300"), unit("B", "100")
    impaired["selling_price"] = "200"
    result = calculate("inventory", body(impaired, other))
    assert Decimal(result["closing_carrying"]) == 300
    assert Decimal(result["write_down_movement"]) == 100


def purchase():
    item = unit()
    item.update(opening_quantity="0", opening_unit_cost="0", opening_cost_evidence="")
    item["receipts"] = [
        {
            "reference": "SYN-purchase",
            "date": "2026-01-02",
            "quantity": "1",
            "unit_cost": "19.12345678",
            "landed_cost": "0.87654322",
            "evidence": "SYN actual acquisition and attributable freight",
        }
    ]
    return item


def test_purchase_and_full_dispatch_consume_exact_landed_unit_cost():
    item = purchase()
    item.update(issues=[issue()], expected_closing_quantity="0")
    result = calculate("inventory", body(item))
    row = result["schedule"][0]
    assert Decimal(row["receipt_cost"]) == Decimal(row["issue_cost"]) == 20
    assert Decimal(row["closing_cost"]) == Decimal(row["cost_rollforward_difference"]) == 0


@pytest.mark.parametrize("quantity", ["0.5", "2"])
def test_fractional_or_pooled_dispatch_rejected(quantity):
    item = unit()
    item["issues"] = [issue(quantity=quantity)]
    with pytest.raises(ValueError, match="exactly one"):
        calculate("inventory", body(item))


def test_movement_whitespace_is_not_evidence():
    item = purchase()
    item["receipts"][0]["evidence"] = " "
    with pytest.raises(ValueError, match="explicit evidence"):
        calculate("inventory", body(item))


@pytest.mark.parametrize("field,value", [("ownership", "custody_only"), ("uom", "box")])
def test_transfer_cannot_change_ownership_or_unit(field, value):
    source, target = transfer()
    target[field] = value
    with pytest.raises(ValueError, match="ownership/UOM"):
        calculate("inventory", body(source, target))


def test_bounded_population_rejected_before_costing():
    first, second = purchase(), purchase()
    first["receipts"] *= 10000
    second["receipts"] *= 10000
    with pytest.raises(ValueError, match="exceeds 20000"):
        calculate("inventory", body(first, second))


@pytest.mark.parametrize("method", ["fifo", "weighted_average"])
def test_identification_evidence_cannot_be_silently_ignored(method):
    data = body()
    data["method"] = method
    with pytest.raises(ValueError, match="requires specific"):
        calculate("inventory", data)

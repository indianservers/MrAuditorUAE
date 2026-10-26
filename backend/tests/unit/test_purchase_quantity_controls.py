"""Independent quantity partitions and price/extension separation for procurement."""

from copy import deepcopy

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.purchase_controls import verify
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from tests.unit.test_practice_audit_workflows import purchase, purchases
from tests.unit.test_shared_audit_workflows import run, source

CONTROL = {"order_id": "PO-1", "line_reference": "LINE-1", "vendor": "V1", "currency": "AED", "uom": "PCS", "document_type": "order", "expected_rows": 1, "quantity": "2"}


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_controlled_purchase_quantities_keep_cash_out_of_goods_controls(country, currency):
    populations = purchases()
    for rows in populations.values():
        rows[0]["currency"] = currency
    populations["payments"][0]["quantity"] = "9999"
    result = run("procurement-match", populations, country=country)
    assert not result["blocked"] and result["exception_count"] == 0
    assert result["purchase_quantity_contract"] == "controlled-purchase-quantities/1"
    assert result["rows"][0]["uom"] == "PCS"
    assert result["rows"][0]["quantities"] == {"orders": "2", "receipts": "2", "invoices": "2"}


@pytest.mark.parametrize("other_unit", ["KG", "pcs", "EA"])
def test_equal_numbers_in_different_units_never_match_or_generate_an_unheld_draft(other_unit):
    populations = purchases()
    populations["receipts"][0]["uom"] = other_unit
    populations["payments"] = []
    result = run("procurement-match", populations)
    row = result["rows"][0]
    assert result["blocked"] and row["quantity_comparison_status"] == "NOT_COMPARABLE"
    assert row["uom"] is None and row["quantities"] == {}
    assert "UNIT_OF_MEASURE_MISSING_OR_DIFFERENT" in row["exceptions"]
    assert {item["uom"] for item in row["source_unit_observations"]} == {"PCS", other_unit}
    assert result["payment_proposals"][0]["state"] == "HOLD"
    row["auditor_status"] = "EXCEPTION_DOCUMENTED"
    assert approval_error(result) is not None


@pytest.mark.parametrize("field,value", [("order_id", "OTHER"), ("line_reference", "OTHER"), ("vendor", "OTHER"), ("currency", "INR"), ("uom", "KG"), ("document_type", "invoice"), ("quantity", "3"), ("expected_rows", 2)])
def test_independent_controls_reject_wrong_partition_or_quantity_even_when_money_agrees(field, value):
    original = [purchase("order")]
    snapshot = deepcopy(original)
    with pytest.raises(ValueError, match="controls do not agree"):
        verify(original, [{**CONTROL, field: value}])
    assert original == snapshot


def test_split_receipts_require_correct_independent_counts_and_duplicate_controls_fail():
    rows = [purchase("receipt", id="R1", quantity="0.75"), purchase("receipt", id="R2", quantity="1.25")]
    control = {**CONTROL, "document_type": "receipt", "expected_rows": 2}
    verify(rows, [control])
    with pytest.raises(ValueError, match="Duplicate"):
        verify(rows, [control, control])
    with pytest.raises(ValueError, match="explicit unit"):
        verify([{**rows[0], "uom": None}], [])
    with pytest.raises(ValueError, match="only to purchase-line"):
        SourceInput.model_validate({"table_type": "stock", "evidence_version_id": "00000000-0000-0000-0000-000000000001", "label": "SYN wrong control scope", "expected_rows": 1, "control_totals": {}, "purchase_quantity_controls": []})


def test_missing_source_controls_cannot_be_bypassed_by_using_a_legacy_source():
    import uuid

    populations = purchases()
    sources = {role: source("purchase-lines", rows) for role, rows in populations.items()}
    sources["receipts"].pop("purchase_quantity_controls")
    data = WorkflowInput.model_validate({"workflow": "procurement-match", "source_ids": {role: uuid.uuid4() for role in sources}, "as_of": "2026-06-30", "title": "SYN controlled purchase", "rationale": "Independent quantity completeness and exact declared units"})
    with pytest.raises(ValueError, match="independently controlled purchase quantities"):
        calculate(data, "AE", sources)


def test_tiny_unit_price_change_is_not_hidden_by_money_tolerance_on_a_large_order():
    populations = purchases()
    for rows in populations.values():
        rows[0].update(quantity="1000000", unit_price="100", amount="100000000")
    populations["invoices"][0].update(unit_price="99.999", amount="99999000")
    populations["payments"][0]["amount"] = "99999000"
    result = run("procurement-match", populations, tolerance="0.01")
    assert result["rows"][0]["exceptions"] == ["PRICE_DIFFERENCE"]


def test_quantity_differences_are_exact_even_with_large_money_tolerance():
    populations = purchases()
    populations["invoices"][0].update(quantity="2.00000001", amount="100.0000005")
    populations["payments"][0]["amount"] = "100.0000005"
    result = run("procurement-match", populations, tolerance="1000")
    assert "INVOICE_EXCEEDS_RECEIPT" in result["rows"][0]["exceptions"]


@pytest.mark.parametrize("preparer", ["", "   ", " SYN-reviewer "])
def test_missing_or_equivalent_preparer_does_not_establish_segregation(preparer):
    populations = purchases()
    populations["payments"] = []
    for role in ("orders", "invoices"):
        populations[role][0].update(approval_status="approved", bank_change_verified=True, prepared_by=preparer, approved_by="SYN-reviewer")
    proposal = run("procurement-match", populations)["payment_proposals"][0]
    assert proposal["state"] == "HOLD" and "SEGREGATION_OF_DUTIES_NOT_ESTABLISHED" in proposal["holds"]


def test_old_uncontrolled_procurement_result_requires_regeneration_before_approval():
    legacy = {"workflow": "procurement-match", "rows": [{"id": "LEGACY", "state": "MATCHED"}], "blocked": False}
    assert "independently controlled quantities" in approval_error(legacy)


def test_maximum_controlled_source_retains_each_distinct_purchase_line():
    rows = [purchase("order", id=f"O{index}", line_reference=f"LINE-{index}") for index in range(5000)]
    controls = [{**CONTROL, "line_reference": f"LINE-{index}"} for index in range(5000)]
    verify(rows, controls)

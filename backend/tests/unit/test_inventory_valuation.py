import csv
import io
import uuid
from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.inventory_valuation import InventoryValuation
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from app.modules.country_workflows.sources import parse_csv


def population(currency="AED"):
    stock = {"id": "SYN-BOOK-1", "account": "INV-001", "site": "SYN-WAREHOUSE", "sku": "SKU-001", "lot": "LOT-001",
        "uom": "PCS", "currency": currency, "quantity": "10", "unit_cost": "100", "unit_nrv": "110",
        "ownership": "owned", "condition": "good", "count_date": "2026-06-30"}
    valuation = {"id": "SYN-VALUE-1", **{field: stock[field] for field in ("site", "sku", "lot", "uom", "currency", "quantity")},
        "as_of": "2026-06-30", "assessed_unit_cost": "100", "selling_unit_price": "120", "completion_unit_cost": "5", "selling_unit_cost": "5",
        "cost_observation_date": "2026-06-10", "nrv_observation_date": "2026-07-03", "cost_evidence_version_id": str(uuid.uuid4()),
        "nrv_evidence_version_id": str(uuid.uuid4()), "cost_source_sha256": "a" * 64, "nrv_source_sha256": "b" * 64,
        "cost_reference": "SYN-COST-PAGE-2", "nrv_reference": "SYN-SELLING-EVIDENCE-PAGE-3",
        "assessment": "Independently assessed fictional cost policy and selling/completion/selling-cost evidence applicable at reporting date"}
    return {"books": [stock], "valuations": [valuation], "controls": [{"id": "SYN-GL-1", "account": "INV-001", "currency": currency, "as_of": "2026-06-30", "amount": "1000"}]}


def source(table, rows, **changes):
    data = {"evidence_version_id": uuid.uuid4(), "table_type": table, "label": "SYNTHETIC independent inventory " + table,
        "expected_rows": len(rows), "control_totals": {}}
    if table == "stock":
        data["inventory_quantity_controls"] = [{**{field: row.get(field, "") for field in ("site", "sku", "lot", "uom", "currency")},
            "expected_rows": 1, "positive_quantity": max(Decimal(0), Decimal(row["quantity"])), "negative_quantity": min(Decimal(0), Decimal(row["quantity"]))} for row in rows]
    elif table == "inventory-valuations":
        data["inventory_valuation_controls"] = [{"currency": row["currency"], "expected_rows": 1,
            "cost_value": "1000", "nrv_value": "1100"} for row in rows]
    else:
        data["control_totals"] = {row["currency"]: row["amount"] for row in rows}
    data.update(changes)
    if not rows:
        data["nil_reason"] = "Independently assessed fictional nil source population"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else ["id"])
    writer.writeheader()
    writer.writerows(rows)
    return parse_csv(buffer.getvalue().encode(), SourceInput.model_validate(data))


def run(rows=None, country="AE", sources=None, **changes):
    rows = population() if rows is None else rows
    sources = sources or {role: source(table, rows[role]) for role, table in (("books", "stock"), ("valuations", "inventory-valuations"), ("controls", "accounting-controls"))}
    data = WorkflowInput.model_validate({"workflow": "inventory-valuation-control", "source_ids": {role: uuid.uuid4() for role in sources},
        "as_of": "2026-06-30", "review_through": "2026-07-15", "inventory_gl_basis": "gross-cost",
        "inventory_scope_assessment": "Independent fictional framework/cost policy and GL account mapping assessment",
        "title": "SYNTHETIC inventory valuation review", "rationale": "Independent book quantities, valuation evidence and recorded GL controls", **changes})
    return calculate(data, country, sources)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
def test_unit_price_evidence_and_recorded_gl_control_are_separate(country, currency):
    rows = population(currency)
    original = deepcopy(rows)
    result = run(rows, country)
    assert rows == original and result["exception_count"] == 0 and not result["blocked"]
    valuation, control = result["rows"]
    assert valuation["assessed_unit_nrv"] == "110" and valuation["assessed_lower_cost_nrv_value"] == "1000"
    assert control["recorded_book_value"] == control["gl_amount"] == "1000"
    assert result["statutory_calculation_qualified"] is False


def test_lower_nrv_and_different_unit_cost_do_not_hide_behind_matching_gl():
    rows = population()
    rows["valuations"][0].update(assessed_unit_cost="95", selling_unit_price="100", completion_unit_cost="10", selling_unit_cost="5")
    sources = {"books": source("stock", rows["books"]), "controls": source("accounting-controls", rows["controls"]),
        "valuations": source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 1, "cost_value": "950", "nrv_value": "850"}])}
    result = run(sources=sources)
    valuation, control = result["rows"]
    assert control["state"] == "MATCHED" and valuation["state"] == "EXCEPTIONS"
    assert set(valuation["exceptions"]) == {"UNIT_COST_DIFFERENCE", "UNIT_NRV_DIFFERENCE", "NRV_BELOW_ASSESSED_COST"}
    assert valuation["recorded_minus_assessed_value"] == "150"


def test_net_recorded_gl_basis_is_explicit_and_never_uses_assessed_value_as_book():
    rows = population()
    rows["books"][0]["unit_nrv"] = "90"
    rows["controls"][0]["amount"] = "900"
    result = run(rows, inventory_gl_basis="recorded-lower-of-cost-nrv")
    assert result["rows"][-1]["state"] == "MATCHED"
    assert result["rows"][-1]["recorded_book_value"] == "900"
    assert result["rows"][0]["assessed_lower_cost_nrv_value"] == "1000"
    assert result["rows"][0]["unit_nrv_difference"] == "-20"


@pytest.mark.parametrize("field,value", [("site", "OTHER"), ("sku", "OTHER"), ("lot", "OTHER"), ("uom", "KG"), ("currency", "USD")])
def test_price_evidence_cannot_cross_stock_partitions(field, value):
    rows = population()
    rows["valuations"][0][field] = value
    result = run(rows)
    assert result["blocked"]
    assert any("MISSING_VALUATION_EVIDENCE" in row.get("exceptions", []) for row in result["rows"])
    assert any("MISSING_BOOK_POSITION" in row.get("exceptions", []) for row in result["rows"])


@pytest.mark.parametrize("role,field,value", [("books", "ownership", "third-party"), ("books", "count_date", "2026-06-29"),
    ("books", "account", ""), ("controls", "amount", "999")])
def test_missing_ownership_date_mapping_or_gl_agreement_blocks(role, field, value):
    rows = population()
    rows[role][0][field] = value
    assert run(rows)["blocked"]


def test_source_money_and_directional_quantity_controls_are_mandatory():
    rows = population()
    with pytest.raises(ValueError, match="extended-cost"):
        source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 1, "cost_value": "999", "nrv_value": "1100"}])
    sources = {role: source(table, rows[role]) for role, table in (("books", "stock"), ("valuations", "inventory-valuations"), ("controls", "accounting-controls"))}
    sources["books"].pop("inventory_quantity_controls")
    with pytest.raises(ValueError, match="independent book quantity"):
        run(sources=sources)


def test_negative_nrv_remains_unresolved_instead_of_becoming_zero_or_liability():
    rows = population()
    rows["valuations"][0].update(selling_unit_price="1", selling_unit_cost="5", completion_unit_cost="5")
    sources = {"books": source("stock", rows["books"]), "controls": source("accounting-controls", rows["controls"]),
        "valuations": source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 1, "cost_value": "1000", "nrv_value": "-90"}])}
    result = run(sources=sources)
    assert result["blocked"] and result["rows"][0]["assessed_lower_cost_nrv_value"] is None
    assert "NEGATIVE_NRV_REQUIRES_SEPARATE_ASSESSMENT" in result["rows"][0]["exceptions"]


@pytest.mark.parametrize("change", [{"inventory_gl_basis": None}, {"review_through": None}, {"review_through": "2026-06-29"}, {"inventory_scope_assessment": " "}])
def test_scope_basis_and_review_window_are_explicit(change):
    with pytest.raises(ValueError):
        run(**change)


def test_invalid_assessment_and_future_observation_fail():
    rows = population()
    with pytest.raises(ValueError):
        InventoryValuation.model_validate({**rows["valuations"][0], "quantity": "-1"})
    rows["valuations"][0]["nrv_observation_date"] = "2026-07-16"
    with pytest.raises(ValueError, match="observation date"):
        run(rows)


def test_equal_total_costs_cannot_net_opposing_unit_price_variances_between_lots():
    rows = population()
    rows["books"].append({**rows["books"][0], "id": "SYN-BOOK-2", "lot": "LOT-002"})
    rows["valuations"].append({**rows["valuations"][0], "id": "SYN-VALUE-2", "lot": "LOT-002"})
    rows["valuations"][0]["assessed_unit_cost"] = "95"
    rows["valuations"][1]["assessed_unit_cost"] = "105"
    rows["controls"][0]["amount"] = "2000"
    sources = {"books": source("stock", rows["books"]), "controls": source("accounting-controls", rows["controls"]),
        "valuations": source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 2, "cost_value": "2000", "nrv_value": "2200"}])}
    result = run(sources=sources)
    assert result["rows"][-1]["state"] == "MATCHED"
    assert {row["unit_cost_difference"] for row in result["rows"] if row["kind"] == "valuation-test"} == {"5", "-5"}
    assert result["exception_count"] == 2


def test_quantity_scope_is_not_implicitly_scaled_and_missing_net_basis_is_not_zero():
    rows = population()
    rows["valuations"][0]["quantity"] = "9"
    sources = {"books": source("stock", rows["books"]), "controls": source("accounting-controls", rows["controls"]),
        "valuations": source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 1, "cost_value": "900", "nrv_value": "990"}])}
    result = run(sources=sources)
    assert result["blocked"] and result["rows"][0]["assessed_lower_cost_nrv_value"] is None
    rows = population()
    rows["books"][0]["unit_nrv"] = None
    result = run(rows, inventory_gl_basis="recorded-lower-of-cost-nrv")
    assert result["blocked"] and result["rows"][-1]["recorded_book_value"] is None


def test_empty_inventory_is_not_inferred_as_a_qualified_nil_balance():
    rows = {role: [] for role in ("books", "valuations", "controls")}
    with pytest.raises(ValueError, match="nil inventory requires"):
        run(rows)


def test_maximum_controlled_population_retains_all_positions_and_one_gl_scope():
    rows = population()
    rows["books"] = [{**rows["books"][0], "id": f"BOOK-{index}", "lot": f"LOT-{index:04d}"} for index in range(5000)]
    rows["valuations"] = [{**rows["valuations"][0], "id": f"VALUE-{index}", "lot": f"LOT-{index:04d}"} for index in range(5000)]
    rows["controls"][0]["amount"] = "5000000"
    sources = {"books": source("stock", rows["books"]), "controls": source("accounting-controls", rows["controls"]),
        "valuations": source("inventory-valuations", rows["valuations"], inventory_valuation_controls=[{"currency": "AED", "expected_rows": 5000, "cost_value": "5000000", "nrv_value": "5500000"}])}
    result = run(sources=sources)
    assert not result["blocked"] and result["exception_count"] == 0 and len(result["rows"]) == 5001
    assert result["rows"][4999]["lot"] == "LOT-4999"
    assert result["rows"][-1]["recorded_book_value"] == "5000000"

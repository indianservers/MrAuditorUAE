"""Same wrong books/return totals must not establish a correct VAT201 schedule."""

import io
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from app.modules.country_workflows.vat201_arithmetic import checks
from app.modules.intelligence.exports import render
from tests.unit.test_vat_box_scope import full_filed_boxes
from tests.unit.test_vat_emirates import compare, detailed_rows


@pytest.mark.parametrize(
    "layout,factory", [("aggregate-14", full_filed_boxes), ("emirate-20", detailed_rows)]
)
def test_complete_arithmetic_keeps_both_sources_and_original_identities(layout, factory):
    rows = factory()
    result = checks(layout, {"books": rows, "return": deepcopy(rows)})
    assert len(result) == 30
    assert all(row["status"] == "MATCHED" for row in result)
    assert all(row["source_row_ids"] for row in result)


@pytest.mark.parametrize(
    "box,field,value",
    [
        ("8", "tax", "54.99"),
        ("8", "taxable_amount", "1099.99"),
        ("11", "adjustment", "0.01"),
        ("12", "tax", "54.99"),
        ("13", "tax", "5.01"),
        ("14", "tax", "49.99"),
        ("14", "taxable_amount", "50"),
    ],
)
def test_identical_wrong_sources_block_despite_all_comparison_rows_matching(box, field, value):
    rows = detailed_rows()
    next(row for row in rows if row["box"] == box)[field] = value
    result = compare(rows, deepcopy(rows), tolerance="100")
    assert all(row["state"] == "MATCHED" for row in result["rows"])
    assert result["blocked"] and result["vat201_arithmetic_error_count"] >= 2
    assert result["exception_count"] == result["vat201_arithmetic_error_count"]
    assert {
        row["source_role"]
        for row in result["vat201_arithmetic_checks"]
        if row["status"] == "ARITHMETIC_ERROR"
    } == {"books", "return"}


def test_signed_adjustments_and_refund_are_not_clamped_or_inferred_as_recoverable():
    rows = full_filed_boxes()
    by = {row["box"]: row for row in rows}
    by["1"]["adjustment"] = by["8"]["adjustment"] = "-1.23"
    by["9"]["adjustment"] = by["11"]["adjustment"] = "100.01"
    by["12"]["tax"] = "53.77"
    by["13"]["tax"] = "105.01"
    by["14"]["tax"] = "-51.24"
    result = checks("aggregate-14", {"books": rows})
    assert all(row["status"] == "MATCHED" for row in result)
    assert (
        next(row for row in result if row["box"] == "14" and row["field"] == "tax")["expected"]
        == "-51.24"
    )


def test_missing_detail_stays_missing_custom_layout_not_assessed_and_explicit_nil_is_valid():
    rows = detailed_rows()
    rows = [row for row in rows if row["box"] != "1g"]
    result = compare(rows, deepcopy(rows))
    assert result["blocked"]
    assert any(
        row["status"] == "MISSING_INPUT" and row["missing_boxes"] == ["1g"]
        for row in result["vat201_arithmetic_checks"]
    )
    assert checks("custom", {"books": rows}) == []
    nil = [
        {**row, "taxable_amount": "0", "tax": "0", "adjustment": "0"} for row in full_filed_boxes()
    ]
    assert all(row["status"] == "MATCHED" for row in checks("aggregate-14", {"books": nil}))


def test_export_contains_all_checks_and_exact_values():
    result = compare()
    content, _ = render(
        {
            "kind": "country-workflow",
            "id": "synthetic",
            "version": 1,
            "sha256": "0" * 64,
            "created_at": "2026-06-30",
            "dependencies": [],
            "body": result,
        },
        "xlsx",
    )
    sheet = list(load_workbook(io.BytesIO(content))["VAT201 arithmetic"].values)
    assert len(sheet) == 31
    assert "source_row_ids" in sheet[0] and "difference" in sheet[0]
    assert any("Box 12 tax - Box 13 tax" in row for row in sheet)

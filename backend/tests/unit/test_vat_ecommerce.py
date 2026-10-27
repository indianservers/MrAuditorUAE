"""Synthetic split arithmetic is not qualifying-registrant or allocation advice."""

from copy import deepcopy

import pytest
from fastapi import HTTPException

from app.modules.country_workflows.vat201_layouts import EMIRATES, LAYOUTS, SPLIT_FIELDS
from app.modules.regulatory.report_packs import manifest, validate_source
from tests.unit.test_vat_emirates import compare, detailed_rows


def split_rows(prefix="SYNTHETIC-SPLIT"):
    rows = detailed_rows(prefix)
    for row in rows:
        for field in SPLIT_FIELDS:
            row[field] = None
        if row["box"] in EMIRATES:
            for field in ("taxable_amount", "tax", "adjustment"):
                row["ecommerce_" + field] = row[field]
                row["other_standard_" + field] = "0"
    return rows


def run(books=None, filed=None, **kwargs):
    return compare(
        split_rows() if books is None else books,
        split_rows() if filed is None else filed,
        vat201_layout="ecommerce-20",
        required_boxes=LAYOUTS["ecommerce-20"]["boxes"],
        **kwargs,
    )


def test_all_emirate_splits_and_explicit_nil_survive_with_separate_sources():
    result = run()
    assert not result["blocked"] and result["exception_count"] == 0
    assert len(result["vat201_arithmetic_checks"]) == 72
    assert all(c["status"] == "MATCHED" for c in result["vat201_arithmetic_checks"])
    for row in result["rows"][:7]:
        assert all(row["differences"][field] == "0" for field in SPLIT_FIELDS)
        assert row["book_source_ids"] and row["return_source_id"]
    pack = manifest("uae-vat201-review:ecommerce-20/1")
    validate_source(pack, result, [r["key"] for r in pack["requirements"]])


@pytest.mark.parametrize("field", SPLIT_FIELDS)
def test_missing_breakdown_is_not_nil_and_fractions_beyond_fils_fail(field):
    rows = split_rows()
    rows[0][field] = None
    with pytest.raises(ValueError, match="both explicit"):
        run(rows)
    rows[0][field] = "0.001"
    with pytest.raises(ValueError, match="nearest fils"):
        run(rows)


def test_equal_wrong_sources_still_fail_emirate_addition_despite_tolerance():
    rows = split_rows()
    rows[0]["other_standard_tax"] = "0.01"
    result = run(rows, deepcopy(rows), tolerance="100")
    assert all(row["state"] == "MATCHED" for row in result["rows"])
    assert result["blocked"] and result["vat201_arithmetic_error_count"] == 2


def test_opposite_category_variances_do_not_hide_behind_equal_emirate_total():
    rows = split_rows()
    rows[0]["ecommerce_tax"] = "4"
    rows[0]["other_standard_tax"] = "1"
    result = run(rows)
    assert result["vat201_arithmetic_error_count"] == 0
    assert result["rows"][0]["state"] == "VARIANCE"
    assert result["rows"][0]["differences"]["ecommerce_tax"] == "-1"
    assert result["rows"][0]["differences"]["other_standard_tax"] == "1"
    with pytest.raises(HTTPException, match="exact book/return agreement"):
        validate_source(manifest("uae-vat201-review:ecommerce-20/1"), result, ["vat201.box.1a"])


@pytest.mark.parametrize("layout", ["custom", "emirate-20", "aggregate-14"])
def test_split_sources_cannot_be_silently_downgraded(layout):
    with pytest.raises(ValueError):
        compare(
            split_rows(),
            split_rows(),
            vat201_layout=layout,
            required_boxes=LAYOUTS.get(layout, LAYOUTS["emirate-20"])["boxes"],
        )

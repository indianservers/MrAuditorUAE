"""Declared count coverage is per position, bounded and distinct from attendance."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.country_workflows.calculations import inventory
from app.modules.country_workflows.review import approval_error
from tests.unit.country_workflow_cases import stock


def run(books, counts):
    return inventory(SimpleNamespace(as_of=date(2026, 6, 30)), {"books": books, "count": counts})


@pytest.mark.parametrize("currency", ["AED", "INR", "USD"])
def test_partial_and_excess_counts_are_capped_per_position(currency):
    result = run([stock(currency=currency)], [stock(currency=currency, quantity="4")])
    row = result["rows"][0]
    assert row["book_quantity"] == "10" and row["count_quantity"] == "4"
    assert row["count_supported_quantity"] == "4"
    assert row["quantity_coverage_percent"] == "40.0"
    assert result["coverage"]["count_supported_value"] == "40"
    excess = run([stock()], [stock(quantity="12")])["rows"][0]
    assert excess["count_supported_quantity"] == "10"
    assert excess["quantity_coverage_percent"] == "100"
    assert excess["quantity_difference"] == "2" and excess["state"] == "VARIANCE"


@pytest.mark.parametrize(
    "book,count,state",
    [
        (stock(), stock(quantity="-10"), "NEGATIVE_QUANTITY"),
        (stock(quantity="-10"), stock(), "NEGATIVE_QUANTITY"),
        (stock(), stock(count_date="2026-06-29"), "COUNT_DATE_BRIDGE_REQUIRED"),
        (stock(), stock(ownership="third-party"), "OWNERSHIP_UNCONFIRMED"),
        (stock(), None, "BOOKS_ONLY"),
        (None, stock(), "COUNT_ONLY"),
    ],
)
def test_unusable_count_is_unknown_and_does_not_inflate_money_coverage(book, count, state):
    result = run([book] if book else [], [count] if count else [])
    row = result["rows"][0]
    assert row["state"] == state
    assert row["count_supported_quantity"] is None
    assert row["quantity_coverage_percent"] is None
    assert result["coverage"]["count_supported_value"] in ("0", None)


def test_explicit_zero_count_differs_from_zero_book_denominator():
    zero_count = run([stock()], [stock(quantity="0")])["rows"][0]
    assert zero_count["count_supported_quantity"] == "0"
    assert zero_count["quantity_coverage_percent"] == "0"
    zero_book = run([stock(quantity="0")], [stock(quantity="0")])["rows"][0]
    assert zero_book["count_supported_quantity"] == "0"
    assert zero_book["quantity_coverage_percent"] is None


def test_units_currencies_and_lots_remain_separate_and_no_quantity_total_is_invented():
    books = [stock(lot="A"), stock(lot="B", uom="KG", currency="INR", quantity="20")]
    counts = [{**books[0], "quantity": "5"}, {**books[1], "quantity": "5"}]
    result = run(books, counts)
    assert [row["quantity_coverage_percent"] for row in result["rows"]] == ["50.0", "25.00"]
    assert result["coverage"]["percent"] is None
    assert "no quantity aggregation or physical verification" in result["quantity_coverage_basis"]


def test_condition_risk_remains_even_when_declared_quantity_is_fully_covered():
    row = run([stock()], [stock(condition="damaged")])["rows"][0]
    assert row["quantity_coverage_percent"] == "100"
    assert row["state"] == "CONDITION_EXCEPTION"


def test_legacy_stock_result_requires_regeneration_without_rewriting_it():
    legacy = {"workflow": "stock-audit", "rows": [], "coverage": {"percent": "100"}}
    assert "Regenerate stock count coverage" in approval_error(legacy)
    assert legacy == {"workflow": "stock-audit", "rows": [], "coverage": {"percent": "100"}}
    current = {**run([stock()], [stock()]), "workflow": "stock-audit"}
    assert approval_error(current) is None


async def test_legacy_reviewed_stock_cannot_generate_a_new_paper(monkeypatch):
    from fastapi import HTTPException

    from app.api.v1 import intelligence
    from app.modules.intelligence.schemas import GeneratePaper

    legacy = {
        "workflow": "stock-audit",
        "review_status": "REVIEWED",
        "coverage": {"percent": "100"},
    }
    monkeypatch.setattr(intelligence.audit, "engagement", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(
        intelligence.service, "event", AsyncMock(return_value=SimpleNamespace(body=legacy))
    )
    create = AsyncMock()
    monkeypatch.setattr(intelligence.audit, "create", create)
    with pytest.raises(HTTPException) as error:
        await intelligence.generate_paper(
            uuid4(),
            uuid4(),
            GeneratePaper(
                reference="LEGACY",
                title="Historical stock",
                objective="Attempt a new paper from a legacy stock calculation",
            ),
            None,
            None,
            SimpleNamespace(),
        )
    assert error.value.status_code == 409
    assert "Regenerate stock count coverage" in error.value.detail
    create.assert_not_awaited()
    assert legacy["coverage"]["percent"] == "100"

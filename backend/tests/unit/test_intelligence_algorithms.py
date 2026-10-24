"""Deterministic accounting controls, independent of provider availability."""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.intelligence.documents import money, structured
from app.modules.intelligence.matching import age_open_items, reconcile_transactions
from app.modules.intelligence.schemas import JobInput


def row(identifier, amount, reference="INV-1", currency="AED", party="Supplier A"):
    return dict(
        id=identifier,
        amount=amount,
        reference=reference,
        currency=currency,
        counterparty=party,
        date="2026-10-01",
    )


def test_exact_decimal_matching_and_ambiguity():
    result = reconcile_transactions([row("a", "0.30")], [row("b", "0.30")])
    assert result["matches"][0]["variance"] == "0.00"
    assert result["matches"][0]["auditor_status"] == "NOT_REVIEWED"
    duplicate = reconcile_transactions([row("a", "10")], [row("b", "10"), row("c", "10")])
    assert not duplicate["matches"]
    assert len(duplicate["ambiguous"]) == 1
    assert len(duplicate["unmatched_right"]) == 2
    different_party = reconcile_transactions([row("a", "10")], [row("b", "10", party="Other")])
    assert not different_party["matches"]


def test_grouping_tolerance_currency_and_duplicate_ids():
    result = reconcile_transactions([row("a", "0.10"), row("b", "0.20")], [row("c", "0.30")])
    assert result["matches"][0]["rule"] == "BOUNDED_REFERENCE_GROUP"
    assert result["matched_left_count"] == 2
    result = reconcile_transactions([row("a", "1.00")], [row("b", "1.01")], Decimal("0.01"))
    assert result["matches"][0]["variance"] == "-0.01"
    assert not reconcile_transactions([row("a", "1")], [row("b", "1", currency="USD")])["matches"]
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_transactions([row("a", "1"), row("a", "1")], [])


def test_ageing_uses_open_balances_and_explicit_fallback():
    source = [dict(id="a", currency="AED", open_amount="12.34", due_date="2026-09-01")]
    result = age_open_items(source, date(2026, 10, 1), [30, 60, 90])
    assert result["totals_by_currency"]["AED"]["buckets"]["1–30"] == "12.34"
    missing = [dict(id="a", currency="AED", open_amount="-2.34", document_date="2026-09-01")]
    with pytest.raises(ValueError, match="Due date"):
        age_open_items(missing, date(2026, 10, 1), [30, 60])
    assert age_open_items(missing, date(2026, 10, 1), [30, 60], True)["assumptions"]


def test_extraction_conflicts_missing_values_and_conventions():
    pages = [
        dict(
            page=1,
            blocks=[dict(id="a", text="Invoice No: INV-1\nGrand Total: 1.234,50\nCurrency: AED")],
        )
    ]
    result = structured(pages, "AE", ",")
    assert result["fields"]["gross_amount"] == "1234.50"
    assert result["fields"]["tax_amount"] is None
    assert result["review_status"] == "UNVERIFIED"
    pages[0]["blocks"].append(dict(id="b", text="Invoice No: INV-2"))
    assert structured(pages, "AE")["fields"]["invoice_number"] is None
    for value in ["NaN", "Infinity", "1e21", "0.000000001", "1,2", "1.234,50", "nonsense"]:
        with pytest.raises(ValueError):
            money(value)


def test_job_payload_is_strict_and_typed():
    with pytest.raises(ValueError):
        JobInput(operation="ageing", payload={"as_of": "2026-10-01", "fake": True})

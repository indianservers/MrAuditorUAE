"""Exact signed ledger conversion and explicit country/period/nil boundaries."""

import uuid

import pytest
from pydantic import ValidationError

from app.modules.country_workflows.turnover_ledger import TurnoverLedgerInput, source_rows


def payload(country="AE", **changes):
    return dict(
        snapshot_id=str(uuid.uuid4()),
        account_ids=[str(uuid.uuid4())],
        registration="100000000000001" if country == "AE" else "27ABCDE1234F1Z5",
        period_start="2026-06-01",
        period_end="2026-06-30",
        currency="AED" if country == "AE" else "INR",
        expected_rows=2,
        expected_amount="95.00000001",
        assessment="Selected revenue accounts allocated to this registration",
        label="SYNTHETIC committed turnover",
        **changes,
    )


def entries(currency="AED"):
    return [
        dict(
            id=str(uuid.uuid4()),
            reference="J1",
            account_code="400",
            date="2026-06-15",
            amount=amount,
            currency=currency,
            source_record_id=str(uuid.uuid4()),
        )
        for amount in ["-100.00000001", "5"]
    ]


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_exact_credit_normal_reversals_and_lineage(country):
    data = TurnoverLedgerInput(**payload(country))
    original = entries(data.currency)
    rows, totals = source_rows(data, original, country)
    assert totals == {data.currency: "95.00000001"}
    assert [r["amount"] for r in rows] == ["100.00000001", "-5"]
    assert rows[0]["reference"] != rows[1]["reference"]
    assert rows[0]["source_journal_reference"] == "J1"
    assert rows[0]["source_record_id"] == original[0]["source_record_id"]


@pytest.mark.parametrize(
    "change, message",
    [
        ({"expected_rows": 1}, "line count"),
        ({"expected_amount": "-95.00000001"}, "signed amount"),
        ({"registration": "١" * 15}, "registration syntax"),
        ({"currency": "USD"}, "return currency"),
    ],
)
def test_controls_and_country_are_not_inferred(change, message):
    data = payload()
    data.update(change)
    with pytest.raises(ValueError, match=message):
        source_rows(TurnoverLedgerInput(**data), entries(), "AE")


@pytest.mark.parametrize("change", [{"date": "2026-05-31"}, {"currency": "INR"}])
def test_ledger_rows_cannot_escape_declared_scope(change):
    original = entries()
    original[0].update(change)
    with pytest.raises(ValueError, match="selected functional currency and period"):
        source_rows(TurnoverLedgerInput(**payload()), original, "AE")


def test_nil_is_explicit_and_long_assessment_stays_valid():
    data = payload()
    data.update(
        expected_rows=0,
        expected_amount="0",
        nil_reason="No movements in assessed accounts",
        assessment="a" * 2000,
    )
    rows, totals = source_rows(TurnoverLedgerInput(**data), [], "AE")
    assert len(rows) == 1 and rows[0]["id"] == "assessed-nil" and totals == {"AED": "0"}
    assert len(rows[0]["assessment"]) == 2000
    data["nil_reason"] = ""
    with pytest.raises(ValidationError, match="nil reason"):
        TurnoverLedgerInput(**data)


def test_duplicate_accounts_and_reversed_period_are_rejected():
    data = payload()
    data["account_ids"] *= 2
    with pytest.raises(ValidationError, match="Distinct accounts"):
        TurnoverLedgerInput(**data)
    data = payload()
    data["period_end"] = "2026-05-31"
    with pytest.raises(ValidationError, match="ordered ledger period"):
        TurnoverLedgerInput(**data)

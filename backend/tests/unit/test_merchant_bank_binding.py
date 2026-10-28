"""Shared reviewed account binding over literal UAE/India merchant evidence."""

import uuid
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import parse_native
from app.modules.country_workflows.review import approval_error
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_bank_accounts import population
from tests.unit.test_bank_accounts import run as account_review
from tests.unit.test_merchant_settlements import payload, populations, sources
from tests.unit.test_native_workflow_sources import options


def example(country="AE"):
    currency = "AED" if country == "AE" else "INR"
    number = population(country)["bank"][0]["account_number"]
    content = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-UAE-bank-browser.xml"
    ).read_bytes()
    content = (
        content.replace(b"SYNTHETIC-UAE-BANK", number.encode())
        .replace(b"100.20", b"800.00")
        .replace(b"AED", currency.encode())
    )
    data = options().model_copy(
        update={"expected_rows": 1, "control_totals": {currency: Decimal("800")}}
    )
    native = parse_native(content, data, country, "SYNTHETIC-merchant.xml")
    p = populations(country)
    p["allocations"][0]["bank_transaction_id"] = native["rows"][0]["id"]
    prepared = sources(p)
    prepared["bank"] = native
    account_rows = population(country)
    for rows in account_rows.values():
        rows[0]["account"] = "ACCT"
    review = account_review(rows=account_rows, country=country, account="ACCT")
    review["review_status"] = "REVIEWED"
    receipt = {
        "type": "event",
        "id": str(uuid.uuid4()),
        "root_id": str(uuid.uuid4()),
        "version": 2,
        "sha256": "a" * 64,
    }
    request = WorkflowInput(
        **payload(
            currency=currency,
            bank_account_review_id=receipt["id"],
            bank_account_scope_assessment="Synthetic reviewed original bank number to ledger label and entire June window assessment",
        )
    )
    return request, prepared, review, receipt


@pytest.mark.parametrize("country", ["AE", "IN"])
def test_native_merchant_account_alias_requires_review_and_preserves_originals(country):
    request, prepared, review, receipt = example(country)
    original = deepcopy(prepared)
    with pytest.raises(ValueError, match="mixes accounts"):
        calculate(request, country, prepared)
    result = calculate(request, country, prepared, bank_account_review=(review, receipt))
    assert result["rows"][0]["state"] == "MATCHED" and not result["blocked"]
    link = result["bank_account_evidence"]
    assert link["original_bank_source_account"] == population(country)["bank"][0]["account_number"]
    assert link["account"] == "ACCT" and link["account_label_mapping_applied"]
    assert link["source_account_binding"] == "NATIVE_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS"
    assert link["window_start"] == "2026-06-01" and link["window_end"] == "2026-06-30"
    assert link["bank_authentication_status"] == "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"
    assert prepared == original


@pytest.mark.parametrize(
    "fault,message",
    [
        ("unreviewed", "independently reviewed"),
        ("owner-country", "owner country"),
        ("currency", "currency"),
        ("account", "account"),
        ("late-start", "entire financial"),
        ("early-end", "entire financial"),
        ("wrong-number", "Native statement account"),
    ],
)
def test_merchant_link_cannot_bypass_account_or_full_period_scope(fault, message):
    request, prepared, review, receipt = example()
    if fault == "unreviewed":
        review["review_status"] = "UNVERIFIED"
    elif fault in {"owner-country", "currency", "account"}:
        review["bank_account_scope"][
            {"owner-country": "owner_country", "currency": "currency", "account": "account"}[fault]
        ] = "IN" if fault == "owner-country" else "OTHER"
    elif fault == "wrong-number":
        prepared["bank"]["native_metadata"]["account"] = "OTHER"
    else:
        # Even when the first native receipt is June 15, evidence must cover June 1.
        review["rows"][0]["valid_from" if fault == "late-start" else "valid_through"] = (
            "2026-06-02" if fault == "late-start" else "2026-06-29"
        )
    with pytest.raises(ValueError, match=message):
        calculate(request, "AE", prepared, bank_account_review=(review, receipt))


def test_requested_link_without_verified_receipt_blocks_independent_approval():
    request, _, _, _ = example()
    result = calculate(request, "AE", sources(populations()))
    assert result["bank_account_evidence"]["status"] == "LINK_REQUESTED_NOT_VERIFIED"
    assert "Verify the requested bank account" in approval_error(result)


@pytest.mark.parametrize("fault", ["reversal", "value-date"])
def test_reviewed_account_does_not_waive_merchant_bank_movement_requirements(fault):
    request, prepared, review, receipt = example()
    row = prepared["bank"]["rows"][0]
    if fault == "reversal":
        row["is_reversal"] = True
    else:
        row.update(
            bank_date_basis="VALUE_DATE_FALLBACK",
            bank_booking_date=None,
            bank_value_date=row["date"],
        )
    with pytest.raises(ValueError, match="unreversed booked-date evidence"):
        calculate(request, "AE", prepared, bank_account_review=(review, receipt))

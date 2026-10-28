from copy import deepcopy

import pytest
from fastapi import HTTPException

from app.modules.intelligence.bank_matches import select_group


def test_native_browser_fixture_retains_booked_entry_once_and_literal_controls():
    from pathlib import Path
    from uuid import uuid4

    from app.modules.country_workflows.native_sources import parse_native
    from app.modules.country_workflows.schemas import SourceInput

    path = (
        Path(__file__).resolve().parents[3]
        / "docs/country-workflows/sample-inputs/SYNTHETIC-UAE-bank-browser.xml"
    )
    data = SourceInput(
        evidence_version_id=uuid4(),
        file_format="camt053",
        table_type="transactions",
        label="SYNTHETIC native bank browser fixture",
        expected_rows=1,
        control_totals={"AED": "100.20"},
    )
    source = parse_native(path.read_bytes(), data, "AE", path.name)
    assert len(source["rows"]) == 1
    assert source["rows"][0]["reference"] == "SALE"
    assert source["rows"][0]["amount"] == "100.20"
    assert source["rows"][0]["bank_date_basis"] == "BOOKING_DATE"
    assert source["native_metadata"]["opening"] == "0.00"
    assert source["native_metadata"]["closing"] == "100.20"
    assert source["native_metadata"]["bank_identity_verified"] is False


def population():
    return (
        [
            {
                "left_ids": ["B2", "B1"],
                "right_ids": ["S1"],
                "rule": "SYNTHETIC_SPLIT",
                "variance": "0",
            }
        ],
        [
            {"id": "B1", "reference": "ONE", "amount": "40", "currency": "AED"},
            {
                "id": "B2",
                "reference": "TWO",
                "amount": "60",
                "currency": "AED",
                "source_record_id": "ORIGINAL",
                "raw_private_payload": "not returned",
            },
        ],
        [
            {
                "id": "S1",
                "reference": "BANK",
                "amount": "100",
                "currency": "AED",
                "bank_booking_date": "2026-06-15",
                "bank_value_date": "2026-06-16",
            }
        ],
    )


def test_exact_saved_group_order_values_and_dual_dates_are_preserved():
    args = population()
    original = deepcopy(args)
    result = select_group(args[0], 0, args[1], args[2])
    assert [r["id"] for r in result["books"]] == ["B2", "B1"]
    assert result["books"][0]["source_record_id"] == "ORIGINAL"
    assert "raw_private_payload" not in result["books"][0]
    assert result["statement"][0]["bank_value_date"] == "2026-06-16"
    assert result["statement"][0]["amount"] == "100"
    assert args == original


@pytest.mark.parametrize(
    "fault",
    [
        "missing-id",
        "duplicate-group",
        "duplicate-source",
        "missing-source",
        "too-many",
        "bad-group",
        "bad-collection",
        "bad-source",
    ],
)
def test_incomplete_legacy_or_ambiguous_groups_fail_closed(fault):
    matches, books, bank = population()
    if fault == "missing-id":
        matches[0]["left_ids"] = []
    elif fault == "duplicate-group":
        matches[0]["right_ids"] = ["S1", "S1"]
    elif fault == "duplicate-source":
        books.append(deepcopy(books[0]))
    elif fault == "missing-source":
        bank.clear()
    elif fault == "too-many":
        matches[0]["right_ids"] = [str(i) for i in range(101)]
    elif fault == "bad-group":
        matches[0] = None
    elif fault == "bad-collection":
        matches = None
    elif fault == "bad-source":
        books = None
    with pytest.raises(HTTPException) as error:
        select_group(matches, 0, books, bank)
    assert error.value.status_code == 409


@pytest.mark.parametrize("index,status", [(-1, 422), (True, 422), (1, 404), (10**30, 404)])
def test_only_existing_nonnegative_indices_can_be_inspected(index, status):
    matches, books, bank = population()
    with pytest.raises(HTTPException) as error:
        select_group(matches, index, books, bank)
    assert error.value.status_code == status

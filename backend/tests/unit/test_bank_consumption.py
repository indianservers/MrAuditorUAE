"""Independent cash capacity examples; these are synthetic, not bank attestations."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.country_workflows.bank_consumption import (
    ACTIVE,
    CONTRACT,
    WITHDRAWN,
    capacity_error,
    event_manifest,
    is_active,
    manifest,
)
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_dues_allocations import example, parameters, run


def capture():
    data = WorkflowInput(**parameters())
    source = {
        "table_type": "transactions",
        "parser_version": "country-csv-2",
        "evidence_sha256": "a" * 64,
        "rows": example()["bank"],
    }
    return data, source, run()


def claim(amount="60", **changes):
    return {
        "contract": CONTRACT,
        "rows": [
            {
                "cash_key": "cash-1",
                "economic_key": "movement-1",
                "origin_key": "file-1",
                "currency": "AED",
                "capacity": "100",
                "allocated": amount,
                **changes,
            }
        ],
    }


def test_manifest_retains_original_capacity_and_allocated_total():
    data, source, result = capture()
    value = manifest(data, source, result)
    assert [row["capacity"] for row in value["rows"]] == ["150", "30"]
    assert [row["allocated"] for row in value["rows"]] == ["150", "30"]
    assert value["scope"] == "OBLIGATION_APPROVALS_WITHIN_ONE_ENGAGEMENT"


@pytest.mark.parametrize("kind", ["supporting", "snapshot", "native"])
def test_original_positions_survive_selection_and_row_order_changes(kind):
    data, source, result = capture()
    if kind == "supporting":
        source["supporting_table_id"] = "table-a"
        for index, row in enumerate(source["rows"], 10):
            row["supporting_source_row"] = index
            row["supporting_source_worksheet"] = "Sheet1"
    elif kind == "snapshot":
        source.update(source_snapshot_id="snapshot", account_ids=["a"])
        for row in source["rows"]:
            row["source_record_id"] = "original-" + row["id"]
    else:
        source["native_format"] = "camt053"
        for index, row in enumerate(source["rows"], 20):
            row["source_row"] = index
    original = manifest(data, source, result)
    source["rows"].reverse()
    source.update(supporting_table_id="table-b" if kind == "supporting" else None,
                  account_ids=["a", "b"])
    assert manifest(data, source, result)["cash_keys"] == original["cash_keys"]


def test_remapping_row_ids_or_declared_account_does_not_free_same_file_cash():
    data, source, result = capture()
    before = manifest(data, source, result)
    for row in source["rows"]:
        old = row["id"]
        row["id"] += "-mapped"
        next(r for r in result["rows"] if r.get("kind") == "bank" and r["source_id"] == old)[
            "source_id"
        ] = row["id"]
    data.account = "ANOTHER-GL-ALIAS"
    after = manifest(data, source, result)
    assert before["cash_keys"] == after["cash_keys"]
    assert capacity_error([before, after]) == "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"


@pytest.mark.parametrize("mutation", ["amount", "missing", "total", "reversal", "duplicate"])
def test_manifest_rejects_source_result_disagreement(mutation):
    data, source, result = capture()
    if mutation == "amount":
        source["rows"][0]["amount"] = "-149"
    elif mutation == "missing":
        source["rows"].pop()
    elif mutation == "total":
        result["allocation_controls"]["allocated_amount"] = "179"
    elif mutation == "reversal":
        source["rows"][0]["is_reversal"] = True
    else:
        source["rows"].append(deepcopy(source["rows"][0]))
    with pytest.raises(ValueError):
        manifest(data, source, result)


def test_partial_reviews_share_exact_decimal_capacity():
    assert capacity_error([claim(), claim("40")]) is None
    assert (
        capacity_error([claim(), claim("40.00000001")])
        == "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"
    )


def test_two_identical_rows_in_same_capture_are_distinct_but_reuploads_are_ambiguous():
    assert capacity_error([claim("100"), claim("100", cash_key="cash-2")]) is None
    assert (
        capacity_error([claim("100"), claim("1", cash_key="reupload", origin_key="file-2")])
        == "INDISTINGUISHABLE_BANK_CASH_OVERALLOCATED"
    )
    assert (
        capacity_error([claim("60"), claim("40", cash_key="reupload", origin_key="file-2")]) is None
    )


@pytest.mark.parametrize("changes", [{"currency": "INR"}, {"capacity": "101"}])
def test_same_origin_cannot_change_currency_or_capacity(changes):
    assert capacity_error([claim(), claim("1", **changes)]) == "CONFLICTING_BANK_REPRESENTATIONS"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "0", "-1"])
def test_nonpositive_or_nonfinite_claims_fail_closed(amount):
    assert capacity_error([claim(amount)]) == "UNVERIFIABLE_CLAIM"


def test_claim_limits_and_contract():
    assert capacity_error([{"contract": "unknown", "rows": []}]) == "UNVERIFIABLE_CLAIM"
    value = claim()
    value["rows"] *= 5001
    assert capacity_error([value]) == "UNVERIFIABLE_CLAIM"


def test_explicit_withdrawal_releases_but_prepared_note_preserves_active_marker():
    assert is_active({"review_status": "REVIEWED"})
    assert is_active({"review_status": "PREPARED", "bank_consumption_review": {"status": ACTIVE}})
    assert not is_active(
        {"review_status": "REVIEWED", "bank_consumption_review": {"status": WITHDRAWN}}
    )


@pytest.mark.parametrize("tampered", [False, True])
async def test_legacy_manifest_reconstruction_and_cached_integrity(monkeypatch, tampered):
    from app.modules.intelligence import service

    data, source, result = capture()
    result["parameters"] = data.model_dump(mode="json")
    calls = []

    async def retained(db, ctx, eid, source_id, current):
        calls.append((eid, source_id, current))
        return SimpleNamespace(body=source)

    monkeypatch.setattr(service, "event", retained)
    obj = SimpleNamespace(body=result, engagement_id="eng")
    if tampered:
        result["bank_consumption_manifest"] = {"contract": CONTRACT, "rows": []}
        with pytest.raises(HTTPException) as rejected:
            await event_manifest(None, None, obj)
        assert rejected.value.status_code == 409
    else:
        rebuilt = await event_manifest(None, None, obj)
        assert [row["allocated"] for row in rebuilt["rows"]] == ["150", "30"]
    assert calls == [("eng", data.source_ids["bank"], False)]

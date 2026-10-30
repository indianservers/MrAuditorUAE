"""Shared bank claim identity across merchant and obligation procedures."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.country_workflows.bank_consumption import capacity_error, event_manifest, manifest
from app.modules.country_workflows.schemas import WorkflowInput
from tests.unit.test_bank_consumption import capture
from tests.unit.test_dues_allocations import example
from tests.unit.test_merchant_settlements import payload, populations, run, sources


def shared_population(country="AE", direction=-1):
    currency = "AED" if country == "AE" else "INR"
    population = populations(country)
    population["bank"] = example(currency)["bank"]
    for row in population["bank"]:
        row["amount"] = str(abs(int(row["amount"])) * direction)
    book = population["books"][0]
    book.update(kind="REFUND" if direction < 0 else "SALE", amount="180", date="2026-06-01")
    population["books"] = [book]
    batch = population["processor"][0]
    for key in (
        "sales",
        "refunds",
        "chargebacks",
        "fees",
        "fee_tax",
        "withholding",
        "reserve_held",
        "reserve_released",
    ):
        batch[key] = "0"
    batch.update(
        **{"refunds" if direction < 0 else "sales": "180"},
        amount=str(180 * direction),
        period_end="2026-06-01",
        settlement_date="2026-06-01",
        fee_tax_kind="NO_TAX_ASSESSED",
    )
    template = population["allocations"][0]
    population["allocations"] = [
        {
            **template,
            "id": "LINK-" + bank["id"],
            "bank_transaction_id": bank["id"],
            "amount": bank["amount"],
        }
        for bank in population["bank"]
    ]
    return population


def captured(country="AE", direction=-1):
    population = shared_population(country, direction)
    currency = "AED" if country == "AE" else "INR"
    data = WorkflowInput(**payload(currency=currency, account="BANK-1"))
    retained = sources(population)
    retained["bank"]["evidence_sha256"] = hashlib.sha256(
        json.dumps(population["bank"], sort_keys=True).encode()
    ).hexdigest()
    result = run(population, country, currency=currency, account="BANK-1")
    return data, retained, result


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("direction", [-1, 1])
def test_signed_merchant_movements_share_exact_capacity_without_netting(country, direction):
    data, retained, result = captured(country, direction)
    built = manifest(data, retained["bank"], result, allocations=retained["allocations"])
    assert [row["capacity"] for row in built["rows"]] == ["150", "30"]
    assert [row["allocated"] for row in built["rows"]] == ["150", "30"]
    assert capacity_error([built, built]) == "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"
    assert not result["blocked"]


def test_same_bank_file_is_not_reusable_between_obligation_and_merchant_approvals():
    data, retained, result = captured()
    obligation, bank, body = capture()
    merchant = manifest(data, bank, result, allocations=retained["allocations"])
    other = manifest(obligation, bank, body)
    assert merchant["cash_keys"] == other["cash_keys"]
    assert merchant["economic_keys"] == other["economic_keys"]
    assert capacity_error([merchant, other]) == "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "wrong_currency",
        "direction",
        "overallocated",
        "saved_amount",
        "source_type",
        "missing_source",
        "reversal",
    ],
)
def test_original_merchant_allocation_disagreement_fails_closed(mutation):
    data, retained, result = captured()
    allocations = retained["allocations"]
    if mutation == "missing":
        allocations["rows"][0]["bank_transaction_id"] = "ABSENT"
    elif mutation == "duplicate":
        allocations["rows"].append(deepcopy(allocations["rows"][0]))
    elif mutation == "wrong_currency":
        allocations["rows"][0]["currency"] = "USD"
    elif mutation == "direction":
        allocations["rows"][0]["amount"] = "150"
    elif mutation == "overallocated":
        allocations["rows"][0]["amount"] = "-151"
        result["rows"][0]["bank_allocated"] = "-181"
    elif mutation == "saved_amount":
        result["rows"][0]["bank_allocated"] = "-179"
    elif mutation == "source_type":
        allocations["table_type"] = "transactions"
    elif mutation == "missing_source":
        allocations = None
    else:
        retained["bank"]["rows"][0]["is_reversal"] = True
    with pytest.raises(ValueError):
        manifest(data, retained["bank"], result, allocations=allocations)


async def test_historical_merchant_approval_without_cached_manifest_is_reconstructed(monkeypatch):
    from app.modules.intelligence import service

    data, retained, result = captured()
    result["parameters"] = data.model_dump(mode="json")
    calls = []

    async def retained_event(db, ctx, eid, source_id, current):
        role = next(key for key, value in data.source_ids.items() if value == source_id)
        calls.append((role, current))
        return SimpleNamespace(body=retained[role])

    monkeypatch.setattr(service, "event", retained_event)
    obj = SimpleNamespace(body=result, engagement_id="eng")
    built = await event_manifest(None, None, obj)
    assert [row["allocated"] for row in built["rows"]] == ["150", "30"]
    assert calls == [("bank", False), ("allocations", False)]


def test_opposite_direction_batches_never_release_capacity_by_netting_to_zero():
    positive, negative = shared_population(direction=1), shared_population(direction=-1)
    for row in negative["books"] + negative["processor"]:
        row["batch"] = "DEBIT-BATCH"
        row["id"] = "DEBIT-" + row["id"]
    for row in negative["bank"]:
        row["id"] = "DEBIT-" + row["id"]
    for row in negative["allocations"]:
        row["id"] = "DEBIT-" + row["id"]
        row["bank_transaction_id"] = "DEBIT-" + row["bank_transaction_id"]
        row["settlement_id"] = "DEBIT-" + row["settlement_id"]
    combined = {key: positive[key] + negative[key] for key in positive}
    retained = sources(combined)
    retained["bank"]["evidence_sha256"] = "b" * 64
    result = run(combined, account="BANK-1")
    built = manifest(
        WorkflowInput(**payload(account="BANK-1")),
        retained["bank"],
        result,
        allocations=retained["allocations"],
    )
    assert not result["blocked"]
    assert retained["bank"]["control_totals"] == {"AED": "0"}
    assert [row["allocated"] for row in built["rows"]] == ["150", "30", "150", "30"]
    assert capacity_error([built, built]) == "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS"

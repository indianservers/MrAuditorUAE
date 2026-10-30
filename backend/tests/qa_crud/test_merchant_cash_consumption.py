"""Atomic approval across merchant and obligation procedures; synthetic source files."""

import asyncio
import os
from copy import deepcopy
from decimal import Decimal

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_bank_consumption import prepare_cash
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_merchant_cash_consumption import shared_population
from tests.unit.test_merchant_settlements import COMPONENTS, ROLES, payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned migrated test DB required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("separate_engagement", [False, True])
async def test_merchant_obligation_race_stale_claim_and_explicit_release(
    environment, monkeypatch, country, currency, direction, separate_engagement
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "merchant-cash-reviewer")
    await grant(c, h, base, reviewer)
    obligation_eid = eid
    if separate_engagement:
        engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
        created = await c.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": engagement["entity_id"],
                "period_id": engagement["period_id"],
                "name": "SYNTHETIC other engagement sharing original bank movements",
                "engagement_type": "External Audit",
            },
        )
        assert created.status_code == 201, created.text
        obligation_eid = created.json()["id"]
        await grant(c, h, f"/api/v1/engagements/{obligation_eid}/audit", reviewer)
    population = shared_population(country, direction)
    retained = {}
    for role, records in population.items():
        options = {}
        if role == "processor":
            options["merchant_component_controls"] = {
                currency: {key: records[0][key] for key in COMPONENTS}
            }
        obj = await source(
            c,
            h,
            eid,
            records,
            "SYNTHETIC merchant cash " + role,
            ROLES[role],
            {currency: str(sum((Decimal(row["amount"]) for row in records), Decimal(0)))},
            **options,
        )
        response = await decision(c, reviewer[0], eid, obj)
        assert response.status_code == 201, response.text
        retained[role] = response.json()
    params = payload(
        currency=currency,
        account="BANK-1",
        source_ids={role: obj["id"] for role, obj in retained.items()},
    )
    merchant = await execute(c, h, eid, "country-workflow", params)
    assert [row["allocated"] for row in merchant["body"]["bank_consumption_manifest"]["rows"]] == [
        "150",
        "30",
    ]
    args = await prepare_cash(c, h, obligation_eid, reviewer, currency)
    bank_id = retained["bank"]["id"]
    if separate_engagement:
        bank = await source(
            c,
            h,
            obligation_eid,
            population["bank"],
            "SYNTHETIC same bank capture in another engagement",
            "transactions",
            {currency: str(180 * direction)},
        )
        bank_review = await decision(c, reviewer[0], obligation_eid, bank)
        assert bank_review.status_code == 201, bank_review.text
        bank_id = bank_review.json()["id"]
    args["source_ids"]["bank"] = bank_id
    args["bank_payment_sign"] = "debit-negative" if direction < 0 else "debit-positive"
    obligation = await execute(c, h, obligation_eid, "country-workflow", args)
    candidates = [merchant, obligation]
    engagements = [eid, obligation_eid]
    replies = await asyncio.gather(
        *(
            decision(c, reviewer[0], engagement_id, obj)
            for engagement_id, obj in zip(engagements, candidates, strict=True)
        )
    )
    assert sorted(reply.status_code for reply in replies) == [201, 409], [
        reply.text for reply in replies
    ]
    winner_index = next(i for i, reply in enumerate(replies) if reply.status_code == 201)
    winner, loser = replies[winner_index].json(), candidates[1 - winner_index]
    assert "OVERALLOCATED" in replies[1 - winner_index].text
    winner_eid, loser_eid = engagements[winner_index], engagements[1 - winner_index]
    prefix = f"/api/v1/intelligence/engagements/{winner_eid}/events/"
    loser_prefix = f"/api/v1/intelligence/engagements/{loser_eid}/events/"
    # Staleness preserves an approved cash claim. Only explicit withdrawal releases it.
    support = (
        retained["processor"]
        if winner_index == 0
        else (await c.get(prefix + args["source_ids"]["expected"], headers=h)).json()
    )
    prior = deepcopy(winner["body"])
    rejected = await decision(c, reviewer[0], winner_eid, support, "reject")
    assert rejected.status_code == 201, rejected.text
    historical = (await c.get(prefix + winner["id"], headers=h)).json()
    assert historical["freshness"] == "STALE" and historical["body"] == prior
    conflict = await decision(c, reviewer[0], loser_eid, loser)
    assert conflict.status_code == 409 and "OVERALLOCATED" in conflict.text
    status = await c.get(loser_prefix + loser["id"] + "/bank-cash-status", headers=reviewer[0])
    assert status.status_code == 200, status.text
    assert status.json()["related_reviews"][0]["root_id"] == winner["root_id"]
    released = await c.post(
        prefix + winner["id"] + "/withdraw-bank-cash",
        headers=reviewer[0],
        json={
            "action": "reject",
            "expected_version": winner["version"],
            "comments": "SYNTHETIC superseded cash claim explicitly released",
        },
    )
    assert released.status_code == 201, released.text
    approved = await decision(c, reviewer[0], loser_eid, loser)
    assert approved.status_code == 201, approved.text
    assert (
        approved.json()["body"]["bank_consumption_review"]["status"] == "ACTIVE_APPROVED_ALLOCATION"
    )

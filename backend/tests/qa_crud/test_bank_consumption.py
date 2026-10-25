"""Engagement-locked cross-review cash approval against real PostgreSQL."""

import asyncio
import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_dues_allocations import example, parameters

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_atomic_approval_release_and_reapproval(environment, monkeypatch, country, currency):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "shared-cash-reviewer")
    await grant(c, h, base, reviewer)
    population = example(currency)
    for role in ("expected", "reported"):
        for obligation in population[role]:
            obligation["due_date"] = "2026-06-30"
    ids = {}
    for role, table, total in [
        ("expected", "obligations", "180"),
        ("reported", "obligations", "180"),
        ("bank", "transactions", "-180"),
        ("allocations", "obligation-allocations", "180"),
    ]:
        value = await source(
            c, h, eid, population[role], "SYNTHETIC shared cash " + role, table, {currency: total}
        )
        approved = await decision(c, reviewer[0], eid, value)
        assert approved.status_code == 201, approved.text
        ids[role] = approved.json()["id"]
    args = {**parameters(), "source_ids": ids, "currency": currency}
    one = await execute(c, h, eid, "country-workflow", args)
    two = await execute(c, h, eid, "country-workflow", args)
    responses = await asyncio.gather(
        decision(c, reviewer[0], eid, one), decision(c, reviewer[0], eid, two)
    )
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    winner = next(r.json() for r in responses if r.status_code == 201)
    loser = two if responses[0].status_code == 201 else one
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    # Same root may be re-reviewed without charging itself twice.
    repeated = await decision(c, reviewer[0], eid, winner)
    assert repeated.status_code == 201, repeated.text
    winner = repeated.json()
    bad = await c.post(
        prefix + winner["id"] + "/withdraw-bank-cash",
        headers=reviewer[0],
        json={"action": "reject", "expected_version": winner["version"], "comments": "short"},
    )
    assert bad.status_code == 422
    released = await decision(c, reviewer[0], eid, winner, action="reject")
    assert released.status_code == 201, released.text
    assert (await decision(c, reviewer[0], eid, loser)).status_code == 201
    # Withdrawing does not permit reapproval after another review used the cash.
    assert (await decision(c, reviewer[0], eid, released.json())).status_code == 409

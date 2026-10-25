"""Entity-locked cross-engagement cash approval against real PostgreSQL."""

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


async def prepare_cash(c, h, eid, reviewer, currency):
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
    return args


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
    args = await prepare_cash(c, h, eid, reviewer, currency)
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


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_entity_cash_cross_engagement_race_access_and_release(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, first, _ = await setup(c)
    else:
        h, first, _ = await india_context(c)
    engagement = (await c.get("/api/v1/engagements/" + first, headers=h)).json()

    async def new_engagement(entity_id, period_id):
        value = await c.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": entity_id,
                "period_id": period_id,
                "name": "SYNTHETIC parallel bank cash review",
                "engagement_type": "External Audit",
            },
        )
        assert value.status_code == 201, value.text
        return value.json()["id"]

    second = await new_engagement(engagement["entity_id"], engagement["period_id"])
    reviewer = await actor(h, "Firm Administrator", "entity-cash-reviewer")
    results = []
    for eid in (first, second):
        await grant(c, h, f"/api/v1/engagements/{eid}/audit", reviewer)
        args = await prepare_cash(c, h, eid, reviewer, currency)
        results.append(await execute(c, h, eid, "country-workflow", args))
    responses = await asyncio.gather(
        *[
            decision(c, reviewer[0], eid, value)
            for eid, value in zip((first, second), results, strict=True)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    winner_index = next(i for i, response in enumerate(responses) if response.status_code == 201)
    winner, loser = responses[winner_index].json(), results[1 - winner_index]
    win_eid, lose_eid = (first, second)[winner_index], (first, second)[1 - winner_index]
    marker = winner["body"]["bank_consumption_review"]
    assert marker["entity_id"] == engagement["entity_id"]
    assert marker["approval_scope"] == "OBLIGATION_APPROVALS_WITHIN_ONE_TENANT_LEGAL_ENTITY"
    status_url = (
        f"/api/v1/intelligence/engagements/{lose_eid}/events/{loser['id']}/bank-cash-status"
    )
    status = await c.get(status_url, headers=reviewer[0])
    assert status.status_code == 200, status.text
    assert status.json()["related_reviews"][0]["engagement_id"] == win_eid
    limited = await actor(h, "Auditor", "limited-entity-cash-reviewer")
    # Full review permissions on this assignment, without a firm-admin role
    # or an assignment to the competing engagement.
    assigned = (limited[0], limited[1], reviewer[2], limited[3])
    await grant(c, h, f"/api/v1/engagements/{lose_eid}/audit", assigned)
    private = await c.get(status_url, headers=limited[0])
    assert private.status_code == 200, private.text
    assert private.json()["related_reviews"] == []
    assert "authorized reviewer" in private.json()["approval_error"]
    assert win_eid not in private.text and winner["id"] not in private.text
    blocked = await decision(c, limited[0], lose_eid, loser)
    assert blocked.status_code == 409 and "authorized reviewer" in blocked.text
    assert winner["id"] not in blocked.text
    withdrawal = await c.post(
        f"/api/v1/intelligence/engagements/{win_eid}/events/{winner['id']}/withdraw-bank-cash",
        headers=reviewer[0],
        json={
            "action": "reject",
            "expected_version": winner["version"],
            "comments": "Synthetic superseded engagement claim explicitly released",
        },
    )
    assert withdrawal.status_code == 201, withdrawal.text
    accepted = await decision(c, limited[0], lose_eid, loser)
    assert accepted.status_code == 201, accepted.text
    # An identical fictional bank export for a separate legal entity has its
    # own budget. No entity or firm-wide account-name pooling is inferred.
    entity = (await c.get("/api/v1/entities/" + engagement["entity_id"], headers=h)).json()
    another = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": entity["client_id"],
            "name": "SYNTHETIC separate cash owner",
            "country": country,
            "jurisdiction": "Synthetic",
            "functional_currency": currency,
            "presentation_currency": currency,
        },
    )
    assert another.status_code == 201, another.text
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={
            "entity_id": another.json()["id"],
            "start_date": "2026-04-01" if country == "IN" else "2026-01-01",
            "end_date": "2027-03-31" if country == "IN" else "2026-12-31",
        },
    )
    assert period.status_code == 201, period.text
    third = await new_engagement(another.json()["id"], period.json()["id"])
    await grant(c, h, f"/api/v1/engagements/{third}/audit", reviewer)
    args = await prepare_cash(c, h, third, reviewer, currency)
    separate = await execute(c, h, third, "country-workflow", args)
    approved = await decision(c, reviewer[0], third, separate)
    assert approved.status_code == 201, approved.text

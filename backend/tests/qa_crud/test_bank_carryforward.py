import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_bank_clearance import population

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required")


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_reviewed_residuals_carry_once_per_window_keep_age_and_stale_lineage(environment, monkeypatch, country, currency):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "carryforward-reviewer")
    await grant(c, h, base, reviewer)
    p = population(currency)
    selected = {}
    for role, kind in [("outstanding", "bank-outstanding"), ("statement", "transactions"), ("allocations", "bank-clearances")]:
        imported = await source(c, h, eid, p[role], "SYNTHETIC carry " + role, table_type=kind, totals={currency: "40" if role == "allocations" else "-100"})
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        selected[role] = response.json()["id"]
    payload = {
        "workflow": "bank-subsequent-clearance", "source_ids": selected,
        "account": "BANK-1", "currency": currency, "as_of": "2026-06-30", "review_through": "2026-07-31",
        "title": "SYNTHETIC partial clearance", "rationale": "Retained source window and reversal completeness assessed independently",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    controls = {"label": "SYNTHETIC next-window residuals", "expected_rows": 1, "positive_total": "0", "negative_total": "-60", "assessment": "Retained statement-window completeness and unresolved reversals independently assessed"}
    denied = await c.post(prefix + result["id"] + "/bank-carryforward-source", headers=h, json=controls)
    assert denied.status_code == 409, denied.text
    for row in result["body"]["rows"]:
        accepted = await decision(c, h, eid, result, "accept", item_id=row["id"])
        assert accepted.status_code == 201, accepted.text
        result = accepted.json()
    response = await decision(c, reviewer[0], eid, result)
    assert response.status_code == 201, response.text
    result = response.json()
    path = prefix + result["id"] + "/bank-carryforward-source"
    bad = await c.post(path, headers=h, json={**controls, "negative_total": "-59"})
    assert bad.status_code == 422, bad.text
    response = await c.post(path, headers=h, json=controls)
    assert response.status_code == 201, response.text
    carried = response.json()
    row = carried["body"]["rows"][0]
    assert row["date"] == "2026-06-20" and row["balance_date"] == "2026-07-31"
    assert row["amount"] == "-60" and row["original_outstanding_amount"] == "-100"
    assert carried["dependencies"][0]["id"] == result["id"]
    assert (await decision(c, h, eid, carried)).status_code == 403
    next_selected = {"outstanding": carried["id"]}
    p["statement"][0].update(date="2026-08-05", amount="-60")
    p["allocations"][0]["amount"] = "60"
    for role, kind in [("statement", "transactions"), ("allocations", "bank-clearances")]:
        imported = await source(c, h, eid, p[role], "SYNTHETIC August " + role, table_type=kind, totals={currency: "60" if role == "allocations" else "-60"})
        response = await decision(c, reviewer[0], eid, imported)
        assert response.status_code == 201, response.text
        next_selected[role] = response.json()["id"]
    next_payload = {**payload, "source_ids": next_selected, "as_of": "2026-07-31", "review_through": "2026-08-31"}
    await execute(c, h, eid, "country-workflow", next_payload, failed="Independently review carried bank residuals")
    response = await decision(c, reviewer[0], eid, carried)
    assert response.status_code == 201, response.text
    carried = response.json()
    next_payload["source_ids"]["outstanding"] = carried["id"]
    next_result = await execute(c, h, eid, "country-workflow", next_payload)
    assert next_result["body"]["exception_count"] == 0
    assert next_result["body"]["rows"][0]["age_at_reporting_days"] == 41
    assert next_result["body"]["rows"][0]["reporting_date_amount"] == "-60"
    response = await decision(c, reviewer[0], eid, next_result)
    assert response.status_code == 201, response.text
    nil_parent = response.json()
    nil = await c.post(prefix + nil_parent["id"] + "/bank-carryforward-source", headers=h, json={**controls, "expected_rows": 0, "negative_total": "0"})
    assert nil.status_code == 201, nil.text
    assert nil.json()["body"]["rows"] == [] and nil.json()["body"]["nil_reason"]
    withdrawn = await decision(c, reviewer[0], eid, result, "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    for event in (carried, next_result, nil.json()):
        current = await c.get(prefix + event["id"], headers=h)
        assert current.status_code == 200 and current.json()["freshness"] == "STALE"
    stale = await c.post(path, headers=h, json=controls)
    assert stale.status_code == 409, stale.text

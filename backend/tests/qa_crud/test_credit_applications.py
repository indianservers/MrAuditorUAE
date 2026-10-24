import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_credit_applications import population

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


@pytest.mark.parametrize("credit_id", ["CN1", "C" * 120])
async def test_reviewed_credit_application_export_residual_source_and_staleness(
    environment, monkeypatch, credit_id
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "credit-source-reviewer")
    final_reviewer = await actor(h, "Firm Administrator", "credit-result-reviewer")
    for person in (reviewer, final_reviewer):
        await grant(c, h, base, person)
    tables = {}
    populations = population()
    populations["items"][1]["id"] = credit_id
    populations["applications"][0]["credit_item_id"] = credit_id
    for role, rows in populations.items():
        kind = {
            "items": "audit-open-items",
            "controls": "balance-controls",
            "applications": "credit-applications",
        }[role]
        amount = {"items": "60", "controls": "60", "applications": "25"}[role]
        created = await source(c, h, eid, rows, "Synthetic credit " + role, kind, {"AED": amount})
        reviewed = await decision(c, reviewer[0], eid, created)
        assert reviewed.status_code == 201, reviewed.text
        tables[role] = reviewed.json()
    payload = {
        "workflow": "credit-note-applications",
        "allocation_basis": "pre_application_balances",
        "source_ids": {role: obj["id"] for role, obj in tables.items()},
        "as_of": "2026-06-30",
        "title": "Synthetic reviewed credit application",
        "rationale": "Reviewed explicit credit application against independent GL controls",
    }
    result = await execute(c, h, eid, "country-workflow", payload)
    assert [r["amount"] for r in result["body"]["remaining_open_items"]] == ["75", "-15"]
    assert result["body"]["exception_count"] == 1 and not result["body"]["blocked"]
    prefix = f"/api/v1/intelligence/engagements/{eid}/events"
    denied = await c.post(f"{prefix}/{result['id']}/remaining-open-items", headers=h, json={})
    assert denied.status_code == 409
    assert (await decision(c, h, eid, result)).status_code == 403
    undocumented = await decision(c, final_reviewer[0], eid, result)
    assert undocumented.status_code == 409
    disposition = await decision(c, h, eid, result, "accept", item_id="item:" + credit_id)
    assert disposition.status_code == 201, disposition.text
    approved = await decision(c, final_reviewer[0], eid, disposition.json())
    assert approved.status_code == 201, approved.text
    identifier = approved.json()["id"]
    exported = await c.get(f"{prefix}/{identifier}/export?format=xlsx", headers=h)
    assert exported.status_code == 200 and exported.content.startswith(b"PK")
    remaining = await c.post(f"{prefix}/{identifier}/remaining-open-items", headers=h, json={})
    assert remaining.status_code == 201, remaining.text
    body = remaining.json()["body"]
    assert body["table_type"] == "audit-open-items" and body["control_totals"] == {"AED": "60"}
    assert body["review_status"] == "UNVERIFIED"
    assert [r["amount"] for r in body["rows"]] == ["75", "-15"]
    # A new review version of a parent invalidates every derived result and source.
    changed = await decision(c, final_reviewer[0], eid, tables["applications"])
    assert changed.status_code == 201, changed.text
    for event_id in (identifier, remaining.json()["id"]):
        detail = await c.get(f"{prefix}/{event_id}", headers=h)
        assert detail.status_code == 200 and detail.json()["freshness"] == "STALE"

"""Reviewed multi-registration books, recursive independence and stale lineage."""

import os
from copy import deepcopy

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_turnover_bridge import populations

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_composed_books_cannot_hide_authorship_shared_evidence_or_staleness(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "composition-reviewer")
    composer = await actor(h, "Firm Administrator", "composition-preparer")
    await grant(c, h, base, reviewer)
    await grant(c, h, base, composer)
    currency = "AED" if country == "AE" else "INR"
    book_rows = [populations(country)["books"][0]]
    book_rows.append(
        dict(
            book_rows[0],
            registration="100000000000002" if country == "AE" else "27ABCDE1234F1Z5",
            amount="-5",
        )
    )
    components, reviewed_ids = [], []
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    for index, row in enumerate(book_rows):
        component = await source(
            c,
            h,
            eid,
            [row],
            f"SYNTHETIC book component {index}",
            "turnover-amounts",
            {currency: row["amount"]},
        )
        components.append(component)
    controls = dict(
        source_ids=[r["id"] for r in components],
        expected_rows=2,
        expected_amount="95.00000001",
        currency=currency,
        label="SYNTHETIC combined books",
        assessment="Two disjoint reviewed registration schedules and exact controls",
    )
    response = await c.post(
        prefix + "/turnover-books-composition", headers=composer[0], json=controls
    )
    assert response.status_code == 409, response.text
    for component in components:
        reviewed = await decision(c, reviewer[0], eid, component)
        assert reviewed.status_code == 201, reviewed.text
        reviewed_ids.append(reviewed.json()["id"])
    controls["source_ids"] = reviewed_ids
    response = await c.post(
        prefix + "/turnover-books-composition",
        headers=composer[0],
        json={**controls, "expected_rows": 3},
    )
    assert response.status_code == 422 and "controls" in response.text
    response = await c.post(
        prefix + "/turnover-books-composition", headers=composer[0], json=controls
    )
    assert response.status_code == 201, response.text
    combined = response.json()
    assert combined["body"]["allowed_source_roles"] == ["books"]
    assert len({row["id"] for row in combined["body"]["rows"]}) == 2
    assert {row["source_component_row_id"] for row in combined["body"]["rows"]} == {"book"}
    assert (await decision(c, h, eid, combined)).status_code == 403
    assert (await decision(c, composer[0], eid, combined)).status_code == 403
    checked = await decision(c, reviewer[0], eid, combined)
    assert checked.status_code == 201, checked.text
    from app.modules.country_workflows.turnover import ROLES

    ids = {"books": checked.json()["id"]}
    for role in ("scope", "return", "adjustments"):
        records = []
        for index, book in enumerate(book_rows):
            row = dict(
                populations(country)[role][0],
                registration=book["registration"],
                id=f"{role}{index}",
            )
            if role == "return":
                row["amount"] = book["amount"]
            elif role == "adjustments":
                row.update(amount="0", reason="assessed-nil")
            records.append(row)
        prepared = await source(
            c,
            h,
            eid,
            records,
            "SYNTHETIC composition " + role,
            ROLES[role],
            {} if role == "scope" else {currency: "95.00000001" if role == "return" else "0"},
        )
        reviewed = await decision(c, reviewer[0], eid, prepared)
        assert reviewed.status_code == 201, reviewed.text
        ids[role] = reviewed.json()["id"]
    payload = dict(
        workflow="tax-turnover-bridge",
        source_ids=ids,
        currency=currency,
        as_of="2026-06-30",
        title="SYNTHETIC multiple registration bridge",
        rationale="Independent scope returns and explicit nil adjustments",
    )
    bridge = await execute(c, composer[0], eid, "country-workflow", payload)
    assert not bridge["body"]["blocked"] and len(bridge["body"]["rows"]) == 2
    await execute(
        c,
        composer[0],
        eid,
        "country-workflow",
        {**payload, "source_ids": {**ids, "return": reviewed_ids[0]}},
        failed="share underlying source evidence",
    )
    historical = deepcopy(bridge["body"])
    component = (await c.get(prefix + "/events/" + reviewed_ids[0], headers=h)).json()
    assert (await decision(c, reviewer[0], eid, component, "reject")).status_code == 201
    stale = await c.get(prefix + "/events/" + ids["books"], headers=h)
    assert stale.json()["freshness"] == "STALE"
    stale_bridge = await c.get(prefix + "/events/" + bridge["id"], headers=h)
    assert stale_bridge.json()["freshness"] == "STALE" and stale_bridge.json()["body"] == historical

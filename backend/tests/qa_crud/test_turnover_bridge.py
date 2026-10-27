"""Retained synthetic UAE/India turnover scope, review, paging and stale history."""

import io
import os
from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_turnover_bridge import populations

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_turnover_review_scope_full_adjustments_and_source_rejection(
    environment, monkeypatch, country
):
    from app.modules.country_workflows.turnover import ROLES

    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "turnover-reviewer")
    await grant(c, h, base, reviewer)
    rows = populations(country)
    # All 101 signed adjustment reasons must remain available beyond first page.
    rows["adjustments"] = [
        dict(
            rows["adjustments"][0],
            id=f"adjustment-{i}",
            reference=f"ADJ-{i}",
            amount="-0.05" if i < 100 else "0",
        )
        for i in range(101)
    ]
    ids, originals = {}, {}
    currency = "AED" if country == "AE" else "INR"
    for role, records in rows.items():
        totals = (
            {currency: str(sum((Decimal(row["amount"]) for row in records), Decimal(0)))}
            if role != "scope"
            else {}
        )
        prepared = await source(
            c, h, eid, records, "SYNTHETIC turnover " + role, ROLES[role], totals
        )
        originals[role] = prepared
        checked = await decision(c, reviewer[0], eid, prepared)
        assert checked.status_code == 201, checked.text
        ids[role] = checked.json()["id"]
    payload = dict(
        workflow="tax-turnover-bridge",
        source_ids=ids,
        currency=currency,
        as_of="2026-06-30",
        title="SYNTHETIC retained turnover bridge",
        rationale="Independently assessed book revenue, return and signed adjustments",
    )
    pending_scope = await source(
        c,
        h,
        eid,
        [dict(rows["scope"][0], id="pending-scope")],
        "SYNTHETIC pending scope",
        "turnover-scope",
        {},
    )
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**ids, "scope": pending_scope["id"]}},
        failed="Independently review every turnover",
    )
    result = await execute(c, h, eid, "country-workflow", payload)
    assert result["body"]["rows"][0]["state"] == "MATCHED" and not result["body"]["blocked"]
    assert result["collection_totals"]["turnover_adjustment_rows"] == 101
    assert len(result["body"]["turnover_adjustment_rows"]) == 100
    path = f"/api/v1/intelligence/engagements/{eid}/events/"
    page = await c.get(path + result["id"] + "?turnover_offset=100&turnover_limit=100", headers=h)
    assert (
        page.status_code == 200
        and page.json()["body"]["turnover_adjustment_rows"][0]["id"] == "adjustment-100"
    )
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    result = approved.json()
    exported = await c.get(path + result["id"] + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    book = load_workbook(io.BytesIO(exported.content))
    adjustment_rows = list(book["Turnover adjustments"].values)
    assert len(adjustment_rows) == 102 and "assessment" in adjustment_rows[0]
    assert any("adjustment-100" in row for row in adjustment_rows)
    historical = deepcopy((await c.get(path + result["id"], headers=h)).json()["body"])
    expanded = [
        *rows["scope"],
        dict(
            rows["scope"][0],
            id="missing-registration",
            registration="100000000000002" if country == "AE" else "27ABCDE1234F1Z5",
        ),
    ]
    scope = await source(c, h, eid, expanded, "SYNTHETIC wider scope", "turnover-scope", {})
    checked = await decision(c, reviewer[0], eid, scope)
    assert checked.status_code == 201, checked.text
    incomplete = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**ids, "scope": checked.json()["id"]}},
    )
    assert incomplete["body"]["blocked"] and any(
        row["state"] == "MISSING_POPULATION" for row in incomplete["body"]["rows"]
    )
    assert incomplete["body"]["turnover_quantification"]["complete_for_declared_scope"] is False
    assert (await decision(c, reviewer[0], eid, incomplete)).status_code == 409
    old_scope = await source(
        c,
        h,
        eid,
        [
            dict(
                rows["scope"][0],
                id="outside-engagement",
                period_start="2020-01-01",
                period_end="2020-03-31",
            )
        ],
        "SYNTHETIC outside engagement scope",
        "turnover-scope",
        {},
    )
    checked = await decision(c, reviewer[0], eid, old_scope)
    assert checked.status_code == 201, checked.text
    await execute(
        c,
        h,
        eid,
        "country-workflow",
        {**payload, "source_ids": {**ids, "scope": checked.json()["id"]}},
        failed="within the engagement financial period",
    )
    source_detail = await c.get(path + ids["adjustments"], headers=h)
    assert (await decision(c, reviewer[0], eid, source_detail.json(), "reject")).status_code == 201
    stale = await c.get(path + result["id"], headers=h)
    assert stale.json()["freshness"] == "STALE" and stale.json()["body"] == historical

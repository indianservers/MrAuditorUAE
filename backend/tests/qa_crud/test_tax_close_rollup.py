"""Synthetic shared UAE/India tax-close identity and current-source controls."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_shared_rollup_deduplicates_reviewed_findings_and_preserves_history(
    environment, country, currency
):
    c = environment
    h, opts, _, _ = await setup(c)
    if country == "IN":
        entity = await c.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": opts["client_id"],
                "name": "SYNTHETIC India tax close",
                "country": "IN",
                "jurisdiction": "India",
                "functional_currency": "INR",
                "presentation_currency": "INR",
            },
        )
        assert entity.status_code == 201, entity.text
        period = await c.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": entity.json()["id"],
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
            },
        )
        assert period.status_code == 201, period.text
        opts = {"entity_id": entity.json()["id"], "period_id": period.json()["id"]}
    engagement = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": opts["entity_id"],
            "period_id": opts["period_id"],
            "name": "SYNTHETIC tax close scope",
            "engagement_type": "External Audit",
        },
    )
    assert engagement.status_code == 201, engagement.text
    eid = engagement.json()["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    manager = await actor(h, "Audit Manager", "rollup-manager")
    partner = await actor(h, "Audit Partner", "rollup-partner")
    await grant(c, h, base, manager)
    await grant(c, h, base, partner)
    if country == "IN":
        proposed = await c.post(
            f"/api/v1/jurisdictions/engagements/{eid}/context",
            headers=h,
            json={
                "country": "IN",
                "framework": "Ind AS",
                "entity_type": "company",
                "as_of": "2027-03-31",
                "base_version": 0,
                "reason": "Synthetic country context",
            },
        )
        assert proposed.status_code == 201, proposed.text
        response = await c.post(
            f"/api/v1/jurisdictions/engagements/{eid}/context/decision",
            headers=partner[0],
            json={
                "request_id": proposed.json()["id"],
                "approve": True,
                "comments": "Synthetic independent country review",
            },
        )
        assert response.status_code == 201, response.text
    finding = await create(
        c,
        h,
        base,
        "findings",
        dict(
            finding_type="compliance",
            severity="medium",
            financial_impact="125.00000001",
            financial_impact_currency=currency,
            area="SYNTHETIC tax finding",
            condition="Synthetic tax source issue",
        ),
    )
    finding = await action(c, h, base, finding, "UNDER_REVIEW")
    finding = await action(c, manager[0], base, finding, "ACCEPTED_UNRESOLVED")

    async def paper(label, source):
        return await create(
            c,
            h,
            base,
            "working-papers",
            dict(
                folder="SYNTHETIC tax close",
                sections=[
                    dict(heading=label, text="Synthetic work linking one retained audit finding")
                ],
                sources=[dict(kind="record", id=source["id"])],
                conclusion="Synthetic assessed tax-close population",
            ),
        )

    async def approve(p):
        p = await action(c, h, base, p, "submit")
        p = await action(c, manager[0], base, p, "approve")
        return await action(c, partner[0], base, p, "approve")

    p1 = await paper("GST or VAT", finding)
    p2 = await paper("Tax audit or CT", finding)
    endpoint = f"/api/v1/regulatory/engagements/{eid}/tax-close-rollups"
    request = dict(
        workpaper_ids=[p1["id"], p2["id"]],
        title="SYNTHETIC tax close findings",
        rationale="Synthetic explicitly selected current workpaper population",
    )
    assert (await c.post(endpoint, headers=h, json=request)).status_code == 409
    p1 = await approve(p1)
    p2 = await approve(p2)
    result = await c.post(endpoint, headers=h, json=request)
    assert result.status_code == 201, result.text
    saved = result.json()
    body = saved["body"]
    assert (
        body["unique_findings"] == 1
        and body["workpaper_reference_count"] == 2
        and body["duplicate_references_eliminated"] == 1
    )
    assert body["totals_by_currency"][currency]["positive_impact"] == "125.00000001"
    assert not body["blocked"]
    repeated = await c.post(endpoint, headers=h, json=request)
    assert repeated.status_code == 201 and repeated.json()["sha256"] == saved["sha256"]
    assert (await decision(c, h, eid, saved)).status_code == 403
    reviewed = await decision(c, partner[0], eid, saved)
    assert reviewed.status_code == 201, reviewed.text
    saved = reviewed.json()
    event = f"/api/v1/intelligence/engagements/{eid}/events/{saved['id']}"
    xlsx = await c.get(event + "/export?format=xlsx", headers=h)
    assert xlsx.status_code == 200
    book = load_workbook(io.BytesIO(xlsx.content), read_only=True)
    assert any(
        "125.00000001" in str(cell) for sheet in book for row in sheet.values for cell in row
    )
    book.close()
    unknown = await create(
        c,
        h,
        base,
        "findings",
        dict(
            finding_type="compliance", severity="medium", area="Synthetic unquantified tax finding"
        ),
    )
    p3 = await approve(await paper("Unquantified scope", unknown))
    pending = await c.post(endpoint, headers=h, json={**request, "workpaper_ids": [p3["id"]]})
    assert pending.status_code == 201, pending.text
    assert pending.json()["body"]["blocked"] and pending.json()["body"]["totals_by_currency"] == {}
    assert {"FINDING_REVIEW_REQUIRED", "IMPACT_UNQUANTIFIED", "IMPACT_CURRENCY_UNASSESSED"} <= set(
        pending.json()["body"]["rows"][0]["issues"]
    )
    assert (await decision(c, partner[0], eid, pending.json())).status_code == 409
    other = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": opts["entity_id"],
            "period_id": opts["period_id"],
            "name": "SYNTHETIC separate tax scope",
            "engagement_type": "External Audit",
        },
    )
    assert other.status_code == 201, other.text
    foreign = await c.post(
        f"/api/v1/regulatory/engagements/{other.json()['id']}/tax-close-rollups",
        headers=h,
        json=request,
    )
    assert foreign.status_code == 404
    for impact_currency, amount in [(currency, "20"), ("USD", "5")]:
        await create(
            c,
            h,
            base,
            "findings",
            dict(
                finding_type="misstatement",
                severity="medium",
                financial_impact=amount,
                financial_impact_currency=impact_currency,
            ),
        )
    completion = await c.get(base + "/completion-checks", headers=h)
    assert completion.status_code == 200, completion.text
    register = completion.json()["misstatement_register"]
    assert register["uncorrected_gross"] is None and register["summary_currency"] is None
    assert register["totals_by_currency"][currency]["uncorrected_gross"] == "20"
    assert register["totals_by_currency"]["USD"]["uncorrected_gross"] == "5"
    historical = deepcopy(saved["body"])
    await action(c, partner[0], base, p1, "reopen")
    old = await c.get(event, headers=h)
    assert (
        old.status_code == 200
        and old.json()["freshness"] == "STALE"
        and old.json()["body"] == historical
    )
    assert (await decision(c, manager[0], eid, saved)).status_code == 409

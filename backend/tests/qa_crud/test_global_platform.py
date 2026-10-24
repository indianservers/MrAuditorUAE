"""Country isolation and immutable working-paper receipts against real PostgreSQL."""

import os
import uuid

import pytest
from sqlalchemy import select

from app.db.session import Session, tenant_context
from app.modules.jurisdictions.models import EngagementJurisdiction
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import PAPER, action, actor, create, grant, setup

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database")


async def test_country_preference_preserves_engagement_package(environment):
    c = environment
    h, _, eid, base = await setup(c)
    paper = await create(c, h, base, "working-papers", PAPER)
    manager = await actor(h, "Audit Manager", "country-manager")
    partner = await actor(h, "Audit Partner", "country-partner")
    for reviewer in [manager, partner]:
        await grant(c, h, base, reviewer)
    paper = await action(c, h, base, paper, "submit")
    paper = await action(c, manager[0], base, paper, "approve")
    paper = await action(c, partner[0], base, paper, "approve")
    assert paper["status"] == "APPROVED"
    history = (await c.get(base + f"/records/{paper['id']}/history", headers=h)).json()
    path = "/api/v1/jurisdictions/settings"
    before = (await c.get(path, headers=h)).json()
    assert before["country"] == "AE"
    changed = await c.patch(path, headers=h, json={"country": "IN", "version": before["version"]})
    assert changed.status_code == 200, changed.text
    assert (await c.get(path, headers=h)).json()["package"]["status"] == "CORE_ONLY"
    assert (await c.patch(path, headers=h, json={"country": "US", "version": 0})).status_code == 409
    assert (await c.patch(path, headers=h, json={"country": "ZZ", "version": 1})).status_code == 422
    other = await actor(h, "Auditor", "country-other")
    assert (await c.get(path, headers=other[0])).json()["country"] == "AE"
    assert (await c.get("/api/v1/engagements?country=IN", headers=h)).json()["items"] == []
    graph = (await c.get(base + "/graph", headers=h)).json()
    assert graph["package"]["country"] == "AE"
    assert (await c.get(base + f"/records/{paper['id']}/history", headers=h)).json() == history
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        pin = await db.scalar(
            select(EngagementJurisdiction).where(
                EngagementJurisdiction.engagement_id == uuid.UUID(eid)
            )
        )
        assert pin.country == "AE" and pin.manifest["version"] == pin.package_version
        pin.country = "IN"
        with pytest.raises(Exception, match="append only"):
            await db.flush()
        await db.rollback()


async def test_working_paper_graph_propagates_source_changes(environment):
    c = environment
    h, _, _, base = await setup(c)
    source = await create(c, h, base, "working-papers", PAPER)
    dependent = await create(
        c, h, base, "working-papers", {**PAPER, "sources": [{"kind": "record", "id": source["id"]}]}
    )
    downstream = await create(
        c,
        h,
        base,
        "working-papers",
        {**PAPER, "sources": [{"kind": "record", "id": dependent["id"]}]},
    )
    before = (await c.get(base + f"/records/{dependent['id']}/history", headers=h)).json()
    initial = (await c.get(base + "/graph", headers=h)).json()
    assert len(initial["edges"]) == 2
    assert all(n["freshness"] == "CURRENT" for n in initial["nodes"])
    updated = await c.patch(
        base + f"/records/{source['id']}",
        headers=h,
        json={
            "version": source["version"],
            "reference": source["reference"],
            "title": source["title"],
            "body": {**PAPER, "conclusion": "Reassessed source conclusion"},
        },
    )
    assert updated.status_code == 200, updated.text
    result = (await c.get(base + "/graph", headers=h)).json()
    states = {n["id"]: n["freshness"] for n in result["nodes"]}
    assert states[source["id"]] == "CURRENT"
    assert states[dependent["id"]] == states[downstream["id"]] == "STALE"
    assert (await c.get(base + f"/records/{dependent['id']}/history", headers=h)).json() == before
    reviewer = await actor(h, "Audit Manager", "graph-reviewer")
    await grant(c, h, base, reviewer)
    submitted = await action(c, h, base, dependent, "submit")
    await action(c, reviewer[0], base, submitted, "approve", 409)


async def test_non_uae_engagement_uses_global_core_but_blocks_uae_tax(environment):
    c = environment
    h, options, _, _ = await setup(c)
    entity = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": options["client_id"],
            "name": "Synthetic India entity",
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
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )
    engagement = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": entity.json()["id"],
            "period_id": period.json()["id"],
            "name": "Synthetic global audit",
            "engagement_type": "External Audit",
        },
    )
    assert engagement.status_code == 201, engagement.text
    eid = engagement.json()["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    await create(c, h, base, "working-papers", PAPER)
    graph = (await c.get(base + "/graph", headers=h)).json()
    assert graph["package"]["country"] == "IN"
    for kind in ["tax-profile", "vat-einvoicing"]:
        result = await c.post(
            base + "/" + kind,
            headers=h,
            json={"reference": "REG-1", "title": "Unsupported", "body": {}},
        )
        assert result.status_code == 409, result.text

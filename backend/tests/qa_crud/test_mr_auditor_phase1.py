"""Real database controls for global Phase 1; fixtures are explicitly synthetic."""

import asyncio
import os
import uuid

import pytest

from app.db.models.platform import Membership, Tenant
from app.db.session import Session, tenant_context
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import PAPER, actor, create, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database"
)


async def test_org_defaults_roles_concurrency_tenants_and_revocation(environment):
    c = environment
    h, _, _, _ = await setup(c)
    admin = await actor(h, "Firm Administrator", "new-admin")
    organization = "/api/v1/jurisdictions/organization"
    for role in ["Audit Partner", "Audit Manager", "Auditor", "Quality Reviewer", "Client Viewer"]:
        user = await actor(h, role, role.replace(" ", "-").lower())
        result = await c.patch(organization, headers=user[0], json={"country": "IN", "version": 0})
        assert result.status_code == 403, (role, result.text)
    results = await asyncio.gather(
        *[
            c.patch(organization, headers=h, json={"country": country, "version": 0})
            for country in ["IN", "AE"]
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    organization_data = (await c.get(organization, headers=admin[0])).json()
    assert (await c.get("/api/v1/jurisdictions/settings", headers=admin[0])).json()[
        "country"
    ] == organization_data["country"]
    async with Session() as db, db.begin():
        tenant = Tenant(name="Synthetic separate tenant")
        db.add(tenant)
        await db.flush()
        foreign = str(tenant.id)
        await tenant_context(db, h["X-Tenant-ID"])
        membership = await db.get(Membership, uuid.UUID(admin[1]))
        membership.status = "inactive"
    assert (await c.get(organization, headers={**h, "X-Tenant-ID": foreign})).status_code == 403
    assert (await c.get(organization, headers=admin[0])).status_code == 403


async def test_context_independent_review_preserves_versions_and_country_tax(environment):
    c = environment
    h, options, eid, base = await setup(c)
    manager = await actor(h, "Audit Manager", "context-manager")
    await grant(c, h, base, manager)
    paper = await create(c, h, base, "working-papers", PAPER)
    history = (await c.get(base + f"/records/{paper['id']}/history", headers=h)).json()
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    payload = {
        "country": "IN",
        "framework": "Ind AS",
        "entity_type": "company",
        "as_of": "2026-12-31",
        "base_version": 0,
        "reason": "Synthetic Indian reporting engagement with explicit professional assessment",
    }
    requested = await c.post(path, headers=h, json=payload)
    assert requested.status_code == 201, requested.text
    decision = {
        "request_id": requested.json()["id"],
        "approve": True,
        "comments": "Independent synthetic applicability assessment documented",
    }
    assert (await c.post(path + "/decision", headers=h, json=decision)).status_code == 403
    approved = await c.post(path + "/decision", headers=manager[0], json=decision)
    assert approved.status_code == 201, approved.text
    assert (await c.get(path, headers=h)).json()["current"]["version"] == 1
    graph = (await c.get(base + "/graph", headers=h)).json()
    assert next(n for n in graph["nodes"] if n["id"] == paper["id"])["freshness"] == "STALE"
    assert (await c.post(path + "/decision", headers=manager[0], json=decision)).status_code == 409
    assert (await c.post(path, headers=h, json=payload)).status_code == 409
    assert (await c.get(base + f"/records/{paper['id']}/history", headers=h)).json() == history
    assert (await c.get("/api/v1/entities/" + options["entity_id"], headers=h)).json()[
        "country"
    ] == "AE"
    tax = await c.post(
        base + "/tax-profile",
        headers=h,
        json={"reference": "CT", "title": "Unsupported India tax", "body": {}},
    )
    assert tax.status_code == 409
    catalogue = (await c.get(f"/api/v1/jurisdictions/modules?eid={eid}", headers=h)).json()
    assert len(catalogue["items"]) == 165 and len(catalogue["categories"]) == 13
    assert next(m for m in catalogue["items"] if m["name"] == "GST")["availability"] == "PLANNED"
    assert next(m for m in catalogue["items"] if m["name"] == "Corporate Tax")["url"] is None


async def test_lifecycle_real_edges_layout_conflicts_access_and_search(environment):
    c = environment
    h, _, eid, base = await setup(c)
    source = await create(c, h, base, "working-papers", PAPER)
    paper = await create(
        c, h, base, "working-papers", {**PAPER, "sources": [{"kind": "record", "id": source["id"]}]}
    )
    path = f"/api/v1/jurisdictions/engagements/{eid}"
    graph = (await c.get(path + "/lifecycle", headers=h)).json()
    assert len([n for n in graph["nodes"] if n["type"] == "category"]) == 9
    assert any(
        e["source"] == source["id"]
        and e["target"] == paper["id"]
        and e["edge_type"] == "SOURCE_REFERENCE"
        for e in graph["edges"]
    )
    node = (await c.get(path + "/node", headers=h, params={"node_id": paper["id"]})).json()
    assert any(e["source"] == source["id"] for e in node["upstream"])
    payload = {
        "version": 0,
        "graph_version": graph["graph_version"],
        "positions": {paper["id"]: {"x": 125, "y": 42}},
    }
    assert (await c.patch(path + "/layout", headers=h, json=payload)).status_code == 200
    assert (await c.get(path + "/layout", headers=h)).json()["positions"] == payload["positions"]
    colleague = await actor(h, "Audit Manager", "layout-colleague")
    await grant(c, h, base, colleague)
    assert (await c.get(path + "/layout", headers=colleague[0])).json()["positions"] == {}
    assert (await c.patch(path + "/layout", headers=h, json=payload)).status_code == 409
    bad = {**payload, "version": 1, "positions": {str(uuid.uuid4()): {"x": 1, "y": 2}}}
    assert (await c.patch(path + "/layout", headers=h, json=bad)).status_code == 422
    outsider = await actor(h, "Auditor", "graph-outsider")
    assert (await c.get(path + "/lifecycle", headers=outsider[0])).status_code == 403
    assert (await c.get(path + "/layout", headers=outsider[0])).status_code == 403
    search = (
        await c.get("/api/v1/jurisdictions/search", headers=outsider[0], params={"q": "SYNTHETIC"})
    ).json()
    assert not any(r["id"] == paper["id"] for r in search["items"])
    workspace = (await c.get(path + "/workspace", headers=h)).json()
    assert workspace["record_statuses"]["IN_PROGRESS"] == 2
    assert workspace["mapping"]["total"] == 0


async def test_cross_country_groups_review_and_isolation(environment):
    c = environment
    h, options, _, _ = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "group-reviewer")
    foreign = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": options["client_id"],
            "name": "Synthetic Indian subsidiary",
            "country": "IN",
            "jurisdiction": "India",
            "functional_currency": "INR",
            "presentation_currency": "INR",
        },
    )
    assert foreign.status_code == 201, foreign.text
    payload = {
        "parent_id": options["entity_id"],
        "child_id": foreign.json()["id"],
        "ownership_percent": "80",
        "effective_from": "2026-01-01",
        "reason": "Synthetic documented corporate ownership",
    }
    created = await c.post("/api/v1/jurisdictions/groups", headers=h, json=payload)
    assert created.status_code == 201, created.text
    path = "/api/v1/jurisdictions/groups/" + created.json()["id"]
    decision = {
        "version": 1,
        "action": "approve",
        "reason": "Independent administrator reviewed ownership evidence",
    }
    assert (await c.patch(path, headers=h, json=decision)).status_code == 403
    approved = await c.patch(path, headers=reviewer[0], json=decision)
    assert approved.status_code == 200, approved.text
    data = (await c.get("/api/v1/jurisdictions/groups", headers=h)).json()
    assert data["relationships"][0]["status"] == "APPROVED"
    assert {e["country"] for e in data["entities"]} == {"AE", "IN"}
    outsider = await actor(h, "Auditor", "group-outsider")
    hidden = await c.get("/api/v1/jurisdictions/groups", headers=outsider[0])
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["relationships"] == [] and hidden.json()["entities"] == []


async def test_profiles_are_typed_and_registry_routes_are_real(environment):
    c = environment
    h, _, _, _ = await setup(c)
    from app.modules.audit_execution.schemas import BODIES
    from app.modules.jurisdictions.workspace import MODULES

    assert all(m.kind is None or m.kind in BODIES for m in MODULES)
    for country in ["AE", "IN", "GB", "US", "SG", "SA", "AU"]:
        result = await c.get("/api/v1/jurisdictions/profiles/" + country, headers=h)
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["currencies"] and data["version"].startswith(country)
        if country in {"AE", "IN"}:
            assert data["status"] == "CONFIGURED_PROFILE" and data["sources"]
    assert (await c.get("/api/v1/jurisdictions/profiles/ZZ", headers=h)).status_code == 422


async def test_reviewed_context_invalidates_current_outputs_without_rewriting_history(environment):
    from tests.phase5.test_reporting import prepared

    c = environment
    h, eid, base, reviewer, _, profile, *_ = await prepared(c)
    calculation = f"/api/v1/ifrs/engagements/{eid}/financial-statements/{profile['id']}"
    result = await c.post(calculation, headers=h)
    assert result.status_code == 201, result.text
    before = result.json()
    path = f"/api/v1/jurisdictions/engagements/{eid}/context"
    requested = await c.post(
        path,
        headers=h,
        json={
            "country": "AE",
            "framework": "IFRS",
            "entity_type": "company",
            "as_of": "2026-12-31",
            "base_version": 0,
            "reason": "Synthetic formalized reporting context requires input reassessment",
        },
    )
    approved = await c.post(
        path + "/decision",
        headers=reviewer[0],
        json={
            "request_id": requested.json()["id"],
            "approve": True,
            "comments": "Independent reporting context review documented",
        },
    )
    assert approved.status_code == 201, approved.text
    graph = (await c.get(base + "/graph", headers=h)).json()
    assert next(n for n in graph["nodes"] if n["id"] == before["id"])["freshness"] == "STALE"
    old = await c.get(f"/api/v1/ifrs/engagements/{eid}/runs/{before['id']}", headers=h)
    assert old.status_code == 200, old.text
    assert old.json()["sha256"] == before["sha256"]
    blocked = await c.post(calculation, headers=h)
    assert blocked.status_code == 409, blocked.text


async def test_large_projection_reports_its_boundary(environment):
    from app.core.security import decode_token
    from app.modules.audit_execution.models import AuditRecord

    c = environment
    h, _, eid, base = await setup(c)
    uid = decode_token(h["Authorization"].split()[1])
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        db.add_all(
            [
                AuditRecord(
                    tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                    created_by=uid,
                    prepared_by=uid,
                    engagement_id=uuid.UUID(eid),
                    kind="working-papers",
                    reference=f"SYNTHETIC-LARGE-{i:04}",
                    title="Synthetic boundary fixture",
                    body=PAPER,
                    status="IN_PROGRESS",
                )
                for i in range(301)
            ]
        )
    bounded = await c.get(base + "/graph?limit=20", headers=h)
    assert bounded.status_code == 200, bounded.text
    assert bounded.json()["truncated"] is True and len(bounded.json()["nodes"]) == 20
    complete = await c.get(base + "/graph?limit=1000", headers=h)
    assert complete.status_code == 200, complete.text
    assert complete.json()["truncated"] is False and len(complete.json()["nodes"]) == 301

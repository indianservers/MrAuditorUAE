"""Persistent HTTP/job/review/export checks on the explicitly disposable test database."""

import os
import uuid

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_practice_audit_workflows import rate
from tests.unit.test_shared_audit_workflows import control, item, settlement
from tests.unit.test_diligence_audit_workflows import subject

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated test database required"
)


async def prepare(c, h, reviewer, eid, populations):
    sources = {}
    for role, kind, rows, totals in populations:
        event = await source(c, h, eid, rows, "SYNTHETIC " + role, kind, totals)
        reviewed = await decision(c, reviewer[0], eid, event)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()["id"]
    return sources


async def test_real_shared_audit_approval_export_and_staleness(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "shared-audit-reviewer")
    await grant(c, h, base, reviewer)
    sources = await prepare(c, h, reviewer, eid, [
        ("items", "audit-open-items", [item()], {"AED": "100"}),
        ("controls", "balance-controls", [control()], {"AED": "100"}),
        ("settlements", "settlements", [settlement(amount="100")], {"AED": "100"}),
    ])
    payload = {"workflow": "subsequent-settlements", "source_ids": sources,
               "as_of": "2026-06-30", "review_through": "2026-08-31",
               "title": "SYNTHETIC subsequent settlement",
               "rationale": "Independent reporting-date balance and bank allocation evidence"}
    output = await execute(c, h, eid, "country-workflow", payload)
    assert output["body"]["rows"][-1]["remaining_balance"] == "0"
    assert (await decision(c, h, eid, output)).status_code == 403
    approved = await decision(c, reviewer[0], eid, output)
    assert approved.status_code == 201, approved.text
    approved = approved.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{approved['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    paper = await c.post(path + "/working-paper", headers=h, json={
        "reference": "AR-SUBSEQ-TEST", "title": "SYNTHETIC AR subsequent settlements",
        "objective": "Record reviewed receipts against reporting-date open items",
        "assertions": ["existence"],
    })
    assert paper.status_code == 201, paper.text
    original = (await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{sources['items']}", headers=h
    )).json()
    changed = await decision(c, reviewer[0], eid, original, "reject")
    assert changed.status_code == 201
    assert (await c.get(path, headers=h)).json()["freshness"] == "STALE"


async def test_control_failure_cannot_be_overridden_and_ecl_reuses_engine(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "shared-ecl-reviewer")
    await grant(c, h, base, reviewer)
    sources = await prepare(c, h, reviewer, eid, [
        ("items", "audit-open-items", [item()], {"AED": "100"}),
        ("controls", "balance-controls", [control(amount="99")], {"AED": "99"}),
        ("rates", "ecl-loss-rates", [rate()], {}),
    ])
    output = await execute(c, h, eid, "country-workflow", {
        "workflow": "receivables-ecl", "source_ids": sources, "as_of": "2026-06-30",
        "title": "SYNTHETIC ECL reconciliation",
        "rationale": "Deliberate independent GL control difference blocks approval",
    })
    assert output["body"]["blocked"]
    assert output["body"]["total_ecl_by_currency"]["AED"] == "10.00000000"
    accepted = await decision(c, h, eid, output, "accept", item_id="control-1")
    assert accepted.status_code == 201, accepted.text
    assert (await decision(c, reviewer[0], eid, accepted.json())).status_code == 409


async def test_diligence_sources_require_professional_evidence_permission(environment, monkeypatch):
    from app.core.security import decode_token
    from app.db.session import Session, tenant_context
    from app.modules.audit_execution.models import RolePolicy

    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    ordinary = await actor(h, "Auditor", "limited-diligence-reader")
    await grant(c, h, base, ordinary)
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        db.add(RolePolicy(tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                          created_by=decode_token(h["Authorization"].split()[1]),
                          role_id=uuid.UUID(ordinary[2]),
                          permissions=["audit.read", "accounting.read", "workingpaper.create"]))
    obj = await source(c, h, eid, [subject()], "SYNTHETIC diligence source", "diligence-subjects", {})
    path = f"/api/v1/intelligence/engagements/{eid}/events/{obj['id']}"
    assert (await c.get(path, headers=h)).status_code == 200
    assert (await c.get(path, headers=ordinary[0])).status_code == 403
    listing = await c.get(f"/api/v1/intelligence/engagements/{eid}/events", headers=ordinary[0])
    assert listing.status_code == 200
    assert obj["id"] not in [r["id"] for r in listing.json()["items"]]

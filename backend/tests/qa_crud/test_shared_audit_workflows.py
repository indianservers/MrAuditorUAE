"""Persistent HTTP/job/review/export checks on the explicitly disposable test database."""

import os
import uuid

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.test_diligence_audit_workflows import subject
from tests.unit.test_practice_audit_workflows import rate
from tests.unit.test_shared_audit_workflows import control, item, settlement

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated test database required"
)


async def prepare(c, h, reviewer, eid, populations):
    from tests.unit.purchase_fixtures import quantity_controls

    sources = {}
    for role, kind, rows, totals in populations:
        event = await source(
            c,
            h,
            eid,
            rows,
            "SYNTHETIC " + role,
            kind,
            totals,
            **(
                {"purchase_quantity_controls": quantity_controls(rows)}
                if kind == "purchase-lines"
                else {}
            ),
        )
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
    sources = await prepare(
        c,
        h,
        reviewer,
        eid,
        [
            ("items", "audit-open-items", [item()], {"AED": "100"}),
            ("controls", "balance-controls", [control()], {"AED": "100"}),
            ("settlements", "settlements", [settlement(amount="100")], {"AED": "100"}),
        ],
    )
    payload = {
        "workflow": "subsequent-settlements",
        "source_ids": sources,
        "as_of": "2026-06-30",
        "review_through": "2026-08-31",
        "title": "SYNTHETIC subsequent settlement",
        "rationale": "Independent reporting-date balance and bank allocation evidence",
    }
    output = await execute(c, h, eid, "country-workflow", payload)
    assert output["body"]["rows"][-1]["remaining_balance"] == "0"
    assert (await decision(c, h, eid, output)).status_code == 403
    approved = await decision(c, reviewer[0], eid, output)
    assert approved.status_code == 201, approved.text
    approved = approved.json()
    from app.core.dependencies import Context
    from app.core.security import decode_token
    from app.db.session import Session, tenant_context
    from app.modules.enterprise_ai.schemas import ToolInput
    from app.modules.enterprise_ai.security import validate_dependencies
    from app.modules.enterprise_ai.tools import invoke

    ctx = Context(
        decode_token(h["Authorization"].split()[1]), uuid.UUID(h["X-Tenant-ID"]), frozenset()
    )
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        facts = await invoke(db, ctx, uuid.UUID(eid), "audit.get_shared_workflows", ToolInput())
        assert facts.status == "COMPLETED"
        assert facts.data["items"][0]["execution_mode"] == "deterministic_engine"
        assert facts.data["items"][0]["rows_preview"][-1]["remaining_balance"] == "0"
        await validate_dependencies(db, ctx, uuid.UUID(eid), facts.sources)
    path = f"/api/v1/intelligence/engagements/{eid}/events/{approved['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    paper = await c.post(
        path + "/working-paper",
        headers=h,
        json={
            "reference": "AR-SUBSEQ-TEST",
            "title": "SYNTHETIC AR subsequent settlements",
            "objective": "Record reviewed receipts against reporting-date open items",
            "assertions": ["existence"],
        },
    )
    assert paper.status_code == 201, paper.text
    original = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/events/{sources['items']}", headers=h)
    ).json()
    changed = await decision(c, reviewer[0], eid, original, "reject")
    assert changed.status_code == 201
    assert (await c.get(path, headers=h)).json()["freshness"] == "STALE"


async def test_control_failure_cannot_be_overridden_and_ecl_reuses_engine(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "shared-ecl-reviewer")
    await grant(c, h, base, reviewer)
    sources = await prepare(
        c,
        h,
        reviewer,
        eid,
        [
            ("items", "audit-open-items", [item()], {"AED": "100"}),
            ("controls", "balance-controls", [control(amount="99")], {"AED": "99"}),
            ("rates", "ecl-loss-rates", [rate()], {}),
        ],
    )
    output = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "receivables-ecl",
            "source_ids": sources,
            "as_of": "2026-06-30",
            "title": "SYNTHETIC ECL reconciliation",
            "rationale": "Deliberate independent GL control difference blocks approval",
        },
    )
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
        db.add(
            RolePolicy(
                tenant_id=uuid.UUID(h["X-Tenant-ID"]),
                created_by=decode_token(h["Authorization"].split()[1]),
                role_id=uuid.UUID(ordinary[2]),
                permissions=["audit.read", "accounting.read", "workingpaper.create"],
            )
        )
    obj = await source(
        c, h, eid, [subject()], "SYNTHETIC diligence source", "diligence-subjects", {}
    )
    path = f"/api/v1/intelligence/engagements/{eid}/events/{obj['id']}"
    assert (await c.get(path, headers=h)).status_code == 200
    assert (await c.get(path, headers=ordinary[0])).status_code == 403
    listing = await c.get(f"/api/v1/intelligence/engagements/{eid}/events", headers=ordinary[0])
    assert listing.status_code == 200
    assert obj["id"] not in [r["id"] for r in listing.json()["items"]]
    admin_jobs = await c.get(f"/api/v1/intelligence/engagements/{eid}/jobs", headers=h)
    restricted_job = next(j for j in admin_jobs.json()["items"] if j["result_id"] == obj["id"])
    denied_job = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/jobs/{restricted_job['id']}", headers=ordinary[0]
    )
    assert denied_job.status_code == 403
    limited_jobs = await c.get(f"/api/v1/intelligence/engagements/{eid}/jobs", headers=ordinary[0])
    assert restricted_job["id"] not in [j["id"] for j in limited_jobs.json()["items"]]
    assert (await c.get(path + "/export?format=xlsx", headers=ordinary[0])).status_code == 403
    reviewer = await actor(h, "Firm Administrator", "diligence-reviewer")
    await grant(c, h, base, reviewer)
    reviewed = await decision(c, reviewer[0], eid, obj)
    assert reviewed.status_code == 201
    paper = await c.post(
        f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}/working-paper",
        headers=h,
        json={
            "reference": "KYC-TEST",
            "title": "SYNTHETIC KYC paper",
            "objective": "Verify restricted source cannot leak into a generic paper",
        },
    )
    assert paper.status_code == 409 and "restricted" in paper.text


async def test_gl_control_comes_from_committed_account_and_explicit_sign(environment, monkeypatch):
    from decimal import Decimal

    from tests.phase2.test_pipeline import committed

    c = environment
    double_boundaries(monkeypatch)
    h, options, eid, _ = await setup(c)
    _, snapshot = await committed(c, h, options)
    choices = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/accounts?snapshot_id={snapshot}", headers=h
    )
    assert choices.status_code == 200
    cash = next(a for a in choices.json()["items"] if a["code"] == "100")
    payload = {
        "source_kind": "balance-controls",
        "balance_side": "receivable",
        "snapshot_id": snapshot,
        "account_ids": [cash["id"]],
        "bank_account": "SYNTHETIC-CONTROL",
        "currency": "AED",
        "label": "SYNTHETIC committed GL control",
        "as_of": "2026-12-31",
    }
    output = await execute(c, h, eid, "workflow-ledger", payload)
    assert output["kind"] == "workflow-source"
    assert Decimal(output["body"]["rows"][0]["amount"]) == Decimal("-90.10")
    assert output["body"]["source_snapshot_id"] == snapshot
    flipped = await execute(c, h, eid, "workflow-ledger", {**payload, "balance_side": "payable"})
    assert Decimal(flipped["body"]["rows"][0]["amount"]) == Decimal("90.10")
    await execute(
        c, h, eid, "workflow-ledger", {**payload, "as_of": "2026-06-30"}, failed="period end"
    )

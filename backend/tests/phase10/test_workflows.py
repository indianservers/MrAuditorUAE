import os
import uuid

import pytest
from sqlalchemy import text

from app.db.session import Session, tenant_context
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Migrated disposable PostgreSQL required"
)


async def test_grc_independent_approval_owner_isolation_and_immutable_snapshots(environment):
    c = environment
    h, options, eid, audit_base = await setup(c)
    base = f"/api/v1/grc/engagements/{eid}"
    reviewer = await actor(h, "Chief Audit Executive", "p10-reviewer")
    owner = await actor(h, "Risk Owner", "p10-owner")
    board = await actor(h, "Board Viewer", "p10-board")
    for user in [reviewer, owner, board]:
        await grant(c, h, audit_base, user)
    # A firm-level professional role without this engagement's grant must not
    # widen an owner's resource visibility inside the engagement.
    from sqlalchemy import select

    from app.db.models.platform import MembershipRole, Role

    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        ungranted_role = await db.scalar(select(Role).where(Role.name == "Internal Auditor"))
        db.add(MembershipRole(membership_id=uuid.UUID(owner[1]), role_id=ungranted_role.id))
    body = {"version_number": 1, "appetite": "9", "criteria_weights": {"risk": "1"}}
    r = await c.post(
        base + "/records/scoring",
        headers=h,
        json={"reference": "SYNTHETIC-SCORE", "title": "Synthetic scoring", "body": body},
    )
    assert r.status_code == 201, r.text
    paper = await action(c, h, base, r.json(), "submit")
    await action(c, h, base, paper, "approve", expected=403)
    paper = await action(c, reviewer[0], base, paper, "approve")
    r = await c.patch(
        base + "/records/" + paper["id"],
        headers=h,
        json={
            "version": paper["version"],
            "reference": paper["reference"],
            "title": "Changed",
            "body": body,
        },
    )
    assert r.status_code == 409, r.text
    assert (await c.get(base + "/records/scoring", headers=board[0])).status_code == 403
    assert (await c.get(audit_base + "/grc-scoring", headers=h)).status_code == 403
    assert (await c.get(base + "/records/scoring", headers=owner[0])).status_code == 200
    assert (await c.get(base + "/runs", headers=owner[0])).status_code == 403
    draft_policy = await c.post(
        base + "/records/policy",
        headers=h,
        json={
            "reference": "SYNTHETIC-PRIVATE-DRAFT",
            "title": "Synthetic restricted policy draft",
            "body": {
                "owner_id": reviewer[3],
                "version_number": 1,
                "effective_from": "2026-01-01",
                "review_date": "2026-12-31",
                "policy_text": "Synthetic unapproved draft policy must not be visible to unrelated owners.",
            },
        },
    )
    assert draft_policy.status_code == 201, draft_policy.text
    policies = await c.get(base + "/records/policy", headers=owner[0])
    assert policies.status_code == 200 and policies.json()["total"] == 0
    inaccessible = await c.get(
        base + f"/records/{draft_policy.json()['id']}/history", headers=owner[0]
    )
    assert inaccessible.status_code == 403
    from app.modules.grc.catalogue import AI_TASKS

    for task in AI_TASKS:
        response = await c.post(
            base + "/ai", headers=h, json={"task": task, "record_ids": [paper["id"]]}
        )
        assert response.status_code == 201, response.text
        output = response.json()["results"]
        assert output["diagnostic"] is True
        assert output["professional_conclusion"] is False
        assert output["output"]["citations"] == [paper["id"]]
    response = await c.post(
        base + "/ai", headers=board[0], json={"task": AI_TASKS[0], "record_ids": [paper["id"]]}
    )
    assert response.status_code == 403
    from app.core.security import decode_token

    user_id = str(decode_token(h["Authorization"].split()[1]))

    async def approved(kind, body):
        response = await c.post(
            base + "/records/" + kind,
            headers=h,
            json={"reference": "SYNTHETIC-" + kind, "title": "Synthetic " + kind, "body": body},
        )
        assert response.status_code == 201, response.text
        obj = await action(c, h, base, response.json(), "submit")
        return await action(c, reviewer[0], base, obj, "approve")

    universe = await approved(
        "universe",
        {
            "owner_id": user_id,
            "entity_id": options["entity_id"],
            "unit_type": "process",
            "objective": "Synthetic authorization process",
            "exposure": "100",
            "inherent_rating": 10,
            "maturity": 2,
            "frequency_months": 12,
            "assigned_auditor_id": user_id,
        },
    )
    risk = await approved(
        "risk",
        {
            "owner_id": user_id,
            "universe_id": universe["id"],
            "category": "financial",
            "objective": "Authorized transactions",
            "description": "Synthetic authorization risk",
            "cause": "Missing reviewer",
            "consequence": "Potential unreviewed transaction",
            "treatment": "reduce",
            "review_date": "2026-12-31",
            "evidence_ids": [paper["id"]],
        },
    )
    assessment = await approved(
        "assessment",
        {
            "owner_id": user_id,
            "risk_id": risk["id"],
            "scoring_id": paper["id"],
            "as_of": "2026-10-18",
            "inherent_likelihood": 5,
            "inherent_impact": 5,
            "residual_likelihood": 2,
            "residual_impact": 2,
            "velocity": "moderate",
            "rationale": "Synthetic ordinal assessment",
            "evidence_ids": [paper["id"]],
        },
    )
    original = (await c.get(base + "/dashboard", headers=h)).json()["heatmap"][0]
    assert original["residual"] == "4" and original["appetite_breach"] is False
    scoring = await action(c, reviewer[0], base, paper, "reopen")
    response = await c.patch(
        base + "/records/" + paper["id"],
        headers=h,
        json={
            "reference": paper["reference"],
            "title": paper["title"],
            "version": scoring["version"],
            "body": {**body, "appetite": "0"},
        },
    )
    assert response.status_code == 200, response.text
    scoring = await action(c, h, base, response.json(), "submit")
    await action(c, reviewer[0], base, scoring, "approve")
    frozen = (await c.get(base + "/dashboard", headers=h)).json()["heatmap"][0]
    assert frozen["residual"] == "4" and frozen["appetite_breach"] is False
    assert frozen["stale_source"] is True
    response = await c.post(base + f"/records/{assessment['id']}/calculate", headers=h)
    assert response.status_code == 409, response.text
    owned = await c.get(base + "/records/risk", headers=owner[0])
    assert owned.status_code == 200 and owned.json()["total"] == 0
    from sqlalchemy import select

    from app.db.models.platform import BackgroundJob
    from app.modules.grc.models import GRCRun
    from app.workers.accounting import process
    from tests.phase2.test_pipeline import CSV, committed

    batch_id, snapshot_id = await committed(c, h, options)
    monitor = await approved(
        "monitor-rule",
        {
            "owner_id": user_id,
            "rule_key": "SYNTHETIC-import-trigger",
            "version_number": 1,
            "input_kind": "ledger",
            "snapshot_id": snapshot_id,
            "rule_code": "weekend_postings",
            "decision_rationale": "Run on a newly committed same-period population",
            "trigger_on_import": True,
        },
    )
    new_csv = (
        CSV
        + b"500,Expense,2,2026-12-27,100.20,0,L5,false,true,Adjustment\n100,Cash,2,2026-12-27,0,100.20,L6,false,true,Adjustment\n"
    )
    _, replacement_id = await committed(
        c,
        h,
        {
            **options,
            "supersedes_id": batch_id,
            "expected_rows": 6,
            "expected_debit": "210.50",
            "expected_credit": "210.50",
        },
        data=new_csv,
    )
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        job = await db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.tenant_id == uuid.UUID(h["X-Tenant-ID"]),
                BackgroundJob.job_type == "grc.monitor",
                BackgroundJob.payload["snapshot_override_id"].astext == replacement_id,
            )
        )
        assert job and job.status == "pending" and job.payload["rule_id"] == monitor["id"]
        job_id = str(job.id)
    await process(job_id, h["X-Tenant-ID"], user_id)
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        job = await db.get(BackgroundJob, uuid.UUID(job_id))
        assert job.status == "completed", job.error_category
        execution = await db.get(GRCRun, uuid.UUID(job.result["resource_id"]))
        assert execution.inputs["snapshot_id"] == replacement_id
        assert execution.results["population"] == 4
    response = await c.post(
        base + f"/monitoring/{monitor['id']}/execute",
        headers=h,
        json={"snapshot_override_id": replacement_id},
    )
    assert response.status_code == 422
    # Immutable database protections and FORCE RLS exist independently of HTTP checks.
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        rows = (
            await db.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('grc_execution_snapshots','grc_monitor_alerts','grc_monitor_schedules')"
                )
            )
        ).all()
        assert len(rows) == 3 and all(x[1] and x[2] for x in rows)
        identifier = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO grc_execution_snapshots(id,tenant_id,engagement_id,kind,inputs,dependencies,results,sha256) VALUES (:id,:tenant,:eid,'test','{}','[]','{}','test')"
            ),
            {"id": identifier, "tenant": uuid.UUID(h["X-Tenant-ID"]), "eid": uuid.UUID(eid)},
        )
    with pytest.raises(Exception, match="immutable|append|mutation"):
        async with Session() as db, db.begin():
            await tenant_context(db, h["X-Tenant-ID"])
            await db.execute(
                text("UPDATE grc_execution_snapshots SET sha256='changed' WHERE id=:id"),
                {"id": identifier},
            )

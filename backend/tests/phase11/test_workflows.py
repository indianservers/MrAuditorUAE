import os
import uuid

import pytest
from sqlalchemy import select, text

from app.db.session import Session, tenant_context
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, create, grant, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Migrated disposable PostgreSQL required"
)


async def test_investigation_permissions_resume_proposal_and_stale_approval(environment):
    c = environment
    h, options, eid, audit_base = await setup(c)
    reviewer = await actor(h, "Audit Partner", "p11-reviewer")
    client = await actor(h, "Client Viewer", "p11-client")
    await grant(c, h, audit_base, reviewer)
    manager = await actor(h, "Audit Manager", "p11-manager")
    await grant(c, h, audit_base, manager)
    paper = await create(
        c,
        h,
        audit_base,
        "working-papers",
        {
            "folder": "Synthetic",
            "sections": [{"heading": "Synthetic evidence", "text": "SYNTHETIC reference only"}],
            "conclusion": "Synthetic fixture; no professional assurance",
        },
    )
    paper = await action(c, h, audit_base, paper, "submit")
    paper = await action(c, manager[0], audit_base, paper, "approve")
    paper = await action(c, reviewer[0], audit_base, paper, "approve")
    base = f"/api/v1/ai/engagements/{eid}"
    indexed = await c.post(
        base + "/documents", headers=h, json={"record_id": paper["id"], "classification": "other"}
    )
    assert indexed.status_code == 201, indexed.text
    assert indexed.json()["body"]["source_kind"] == "working-papers"
    payload = {
        "engagement_id": eid,
        "task": "workpaper-review",
        "prompt": "Review synthetic papers",
        "idempotency_key": "p11-synthetic-idempotency",
        "inputs": {},
    }
    command = await c.post("/api/v1/ai/command", headers=h, json=payload)
    assert command.status_code == 201, command.text
    run = command.json()
    same = await c.post("/api/v1/ai/command", headers=h, json=payload)
    assert same.status_code == 201 and same.json()["id"] == run["id"]
    conflict = await c.post("/api/v1/ai/command", headers=h, json={**payload, "prompt": "changed"})
    assert conflict.status_code == 409
    url = base + "/investigations/" + run["id"]
    paused = await c.post(
        url + "/control", headers=h, json={"version": run["version"], "action": "pause"}
    )
    assert paused.status_code == 200
    assert (await c.post(url + "/step", headers=h)).json()["state"] == "PAUSED"
    resumed = await c.post(
        url + "/control", headers=h, json={"version": paused.json()["version"], "action": "resume"}
    )
    assert resumed.status_code == 200
    for _ in range(4):
        r = await c.post(url + "/step", headers=h)
        assert r.status_code == 200, r.text
    detail = await c.get(url, headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json()["state"] == "PARTIALLY_COMPLETED"
    receipts = [x for x in detail.json()["events"] if x["kind"] == "step"]
    assert len(receipts) == 3
    assert receipts[0]["body"]["result"]["sources"][0]["id"] == paper["id"]
    assert (await c.get(url, headers=client[0])).status_code == 403
    assert (await c.post("/api/v1/ai/command", headers=client[0], json=payload)).status_code == 403
    other = str(uuid.uuid4())
    assert (await c.get(url.replace(eid, other), headers=reviewer[0])).status_code in {403, 404}
    drafted = await c.post(url + "/draft", headers=h)
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["body"]["diagnostic"] is True
    assert drafted.json()["body"]["output"]["citations"] == [paper["id"]]
    proposal_payload = {
        "run_id": run["id"],
        "title": "SYNTHETIC evidence review",
        "narrative": "Review the original synthetic evidence; do not infer an audit conclusion.",
        "record_ids": [paper["id"]],
    }
    proposed = await c.post(base + "/approvals", headers=h, json=proposal_payload)
    assert proposed.status_code == 201, proposed.text
    p = proposed.json()
    decision = {
        "version": p["version"],
        "payload_hash": p["payload_hash"],
        "decision": "approve",
        "comments": "Independent synthetic approval of draft creation only",
    }
    assert (await c.post(base + f"/approvals/{p['id']}/execute", headers=h)).status_code == 409
    assert (
        await c.post(base + f"/approvals/{p['id']}/decision", headers=h, json=decision)
    ).status_code == 403
    assert (
        await c.post(
            base + f"/approvals/{p['id']}/decision",
            headers=reviewer[0],
            json={**decision, "payload_hash": "0" * 64},
        )
    ).status_code == 409
    approved = await c.post(
        base + f"/approvals/{p['id']}/decision", headers=reviewer[0], json=decision
    )
    assert approved.status_code == 200, approved.text
    executed = await c.post(base + f"/approvals/{p['id']}/execute", headers=h)
    assert executed.status_code == 200, executed.text
    assert executed.json()["state"] == "RECORDED"
    second = await c.post(base + f"/approvals/{p['id']}/execute", headers=h)
    assert second.json()["result"]["record_id"] == executed.json()["result"]["record_id"]
    assert executed.json()["result"]["status"] == "IN_PROGRESS"
    await action(c, reviewer[0], audit_base, paper, "reopen")
    assert (await c.get(url, headers=h)).status_code == 409
    assert (await c.post(base + f"/approvals/{p['id']}/execute", headers=h)).status_code == 409
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        from app.modules.enterprise_ai.models import Event

        identifier = await db.scalar(select(Event.id).limit(1))
        with pytest.raises(Exception):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE ai_workflow_events SET kind='tampered' WHERE id=:id"),
                    {"id": identifier},
                )


async def test_all_reviewed_recipes_deny_unassigned_identity_and_bound_tool_calls(environment):
    c = environment
    h, options, eid, audit_base = await setup(c)
    from app.modules.enterprise_ai.catalogue import RECIPES

    for task in RECIPES:
        r = await c.post(
            "/api/v1/ai/command",
            headers=h,
            json={
                "engagement_id": eid,
                "task": task,
                "prompt": "Synthetic source collection only",
                "idempotency_key": "p11-recipe-" + task,
                "inputs": {},
            },
        )
        assert r.status_code == 201, r.text
        run = r.json()
        for _ in run["plan"]:
            r = await c.post(
                f"/api/v1/ai/engagements/{eid}/investigations/{run['id']}/step", headers=h
            )
            assert r.status_code == 200, r.text
        assert r.json()["state"] in {"COMPLETED", "PARTIALLY_COMPLETED"}, r.text
        detail = await c.get(f"/api/v1/ai/engagements/{eid}/investigations/{run['id']}", headers=h)
        assert detail.status_code == 200, detail.text
        assert len([e for e in detail.json()["events"] if e["kind"] == "step"]) == len(run["plan"])

"""Synthetic database/API tests, with immutable production review controls."""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.dependencies import Context
from app.db.session import Session, tenant_context
from app.modules.intelligence import service
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database")


async def test_versioned_corrections_independent_review_graph_and_immutability(environment):
    c = environment
    h, _, eid, base = await setup(c)
    manager = await actor(h, "Audit Manager", "intelligence-reviewer")
    await grant(c, h, base, manager)
    from app.core.security import decode_claims

    # Use the authenticated subject, never a synthetic unbound contributor.
    claims = decode_claims(h["Authorization"].split()[1])
    ctx = Context(uuid.UUID(claims["sub"]), uuid.UUID(h["X-Tenant-ID"]), frozenset())
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        eng = await service.scope(db, ctx, uuid.UUID(eid), "ocr")
        obj = await service.append(
            db,
            ctx,
            eng,
            "ocr",
            {
                "fields": {"invoice_number": "SYNTHETIC-1", "gross_amount": "100.00"},
                "contributors": [str(ctx.user_id)],
                "review_status": "UNVERIFIED",
            },
            [],
            "synthetic-test",
        )
        identifier, original_hash = str(obj.id), obj.sha256
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/"
    decision = dict(
        expected_version=1, action="approve", comments="Independent synthetic document review"
    )
    assert (
        await c.post(prefix + identifier + "/review", headers=h, json=decision)
    ).status_code == 403
    corrected = await c.post(
        prefix + identifier + "/corrections",
        headers=h,
        json={
            "expected_version": 1,
            "fields": {"gross_amount": "105.00"},
            "reason": "Synthetic correction against the retained original document",
        },
    )
    assert corrected.status_code == 201, corrected.text
    new_id = corrected.json()["id"]
    old = (await c.get(prefix + identifier, headers=h)).json()
    assert old["sha256"] == original_hash and old["freshness"] == "STALE"
    assert old["body"]["fields"]["gross_amount"] == "100.00"
    decision["expected_version"] = 2
    reviewed = await c.post(prefix + new_id + "/review", headers=manager[0], json=decision)
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["body"]["review_status"] == "REVIEWED"
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        with pytest.raises(DBAPIError):
            await db.execute(
                text("UPDATE audit_intelligence_events SET version=9 WHERE id=:id"),
                {"id": uuid.UUID(identifier)},
            )
        await db.rollback()


async def test_real_ledger_jobs_idempotency_publication_and_cancellation(environment, monkeypatch):
    from app.modules.intelligence.jobs import process
    from app.workers.intelligence import run
    from tests.phase2.test_pipeline import committed

    c = environment
    h, options, eid, _ = await setup(c)
    _, snapshot = await committed(c, h, options)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    monkeypatch.setattr(run, "apply_async", lambda **kwargs: None)
    source = await c.get(prefix + "/inputs", headers=h)
    assert source.status_code == 200, source.text
    assert source.json()["snapshots"][0]["id"] == snapshot
    accounts = (
        await c.get("/api/v1/accounting/trial-balance", headers=h, params={"snapshot_id": snapshot})
    ).json()["items"]
    for operation, payload in [
        ("flow", {"snapshot_id": snapshot}),
        ("mapping", {"snapshot_id": snapshot}),
        (
            "lead",
            {
                "snapshot_id": snapshot,
                "account_ids": [r["id"] for r in accounts],
                "section": "Cash & Bank",
                "rationale": "Synthetic test of actual committed account balances",
            },
        ),
    ]:
        data = dict(operation=operation, payload=payload)
        headers = {**h, "Idempotency-Key": operation}
        response = await c.post(prefix + "/jobs", headers=headers, json=data)
        assert response.status_code == 202, response.text
        job = response.json()
        repeat = await c.post(prefix + "/jobs", headers=headers, json=data)
        assert repeat.json()["id"] == job["id"]
        conflict = await c.post(
            prefix + "/jobs",
            headers=headers,
            json={"operation": "flow", "payload": {"snapshot_id": str(uuid.uuid4())}},
        )
        assert conflict.status_code == 409
        await process(job["id"], h["X-Tenant-ID"])
        final = (await c.get(prefix + "/jobs/" + job["id"], headers=h)).json()
        assert final["status"] == "completed", final
        result = (await c.get(prefix + "/events/" + final["result_id"], headers=h)).json()
        assert result["freshness"] == "CURRENT"
        assert result["body"]["review_status"] == "UNVERIFIED"
        if operation == "flow":
            assert len(result["body"]["edges"]) == 4
            assert all(e["source_record_id"] for e in result["body"]["edges"])
        else:
            assert result["body"].get("suggestions") or result["body"].get("rows")
        if operation == "mapping":
            mapping_id = result["id"]
            mapping_hash = result["sha256"]
    manager = await actor(h, "Firm Administrator", "mapping-independent-reviewer")
    await grant(c, h, f"/api/v1/engagements/{eid}/audit", manager)
    proposed = await c.post(
        prefix + "/events/" + mapping_id + "/mapping-decisions",
        headers=h,
        json={
            "expected_version": 1,
            "assignments": {accounts[0]["code"]: {"classification": "Assets"}},
            "reason": "Synthetic explicit human classification against the actual source account",
        },
    )
    assert proposed.status_code == 201, proposed.text
    reviewed = await c.post(
        prefix + "/events/" + proposed.json()["id"] + "/review",
        headers=manager[0],
        json={
            "expected_version": 2,
            "action": "approve",
            "comments": "Synthetic independent review of the human mapping decision",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    applied = await c.post(
        prefix + "/events/" + reviewed.json()["id"] + "/apply-mapping", headers=h
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["approved"]
    original = (await c.get(prefix + "/events/" + mapping_id, headers=h)).json()
    assert original["sha256"] == mapping_hash and original["freshness"] == "STALE"
    graph = await c.get(f"/api/v1/engagements/{eid}/audit/graph", headers=h)
    assert graph.status_code == 200, graph.text
    assert any(n["kind"] == "mapping-receipt" for n in graph.json()["nodes"])
    assert any(n["kind"] == "intelligence:lead" for n in graph.json()["nodes"])
    response = await c.post(
        prefix + "/jobs",
        headers={**h, "Idempotency-Key": "cancel"},
        json={"operation": "flow", "payload": {"snapshot_id": snapshot}},
    )
    job = response.json()
    canceled = await c.post(
        prefix + "/jobs/" + job["id"] + "/actions",
        headers=h,
        json={"version": job["version"], "action": "cancel"},
    )
    assert canceled.status_code == 200, canceled.text
    await process(job["id"], h["X-Tenant-ID"])
    final = (await c.get(prefix + "/jobs/" + job["id"], headers=h)).json()
    assert final["status"] == "canceled" and final["result_id"] is None


async def test_reconciliation_source_rows_and_recorded_auditor_decisions(environment, monkeypatch):
    """Manual table insertion is an explicit fixture, not a malware/extraction integration claim."""
    from app.core.security import decode_claims
    from app.modules.intelligence.jobs import process
    from app.workers.intelligence import run
    from tests.phase2.test_pipeline import committed

    c = environment
    h, options, eid, base = await setup(c)
    _, snapshot = await committed(c, h, options)
    monkeypatch.setattr(run, "apply_async", lambda **kwargs: None)
    ctx = Context(
        uuid.UUID(decode_claims(h["Authorization"].split()[1])["sub"]),
        uuid.UUID(h["X-Tenant-ID"]),
        frozenset(),
    )
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        eng = await service.scope(db, ctx, uuid.UUID(eid), "source-table")
        source = await service.append(
            db,
            ctx,
            eng,
            "source-table",
            {
                "table_kind": "bank",
                "source_filename": "SYNTHETIC workflow fixture only",
                "review_status": "UNVERIFIED",
                "contributors": [str(ctx.user_id)],
                "rows": [
                    {
                        "id": "statement-1",
                        "currency": "AED",
                        "amount": "100.20",
                        "date": "2026-12-26",
                        "reference": "1",
                    }
                ],
            },
            [],
            "synthetic-reconciliation",
        )
        source_id = str(source.id)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    accounts = (
        await c.get(prefix + "/accounts", headers=h, params={"snapshot_id": snapshot})
    ).json()["items"]
    job = await c.post(
        prefix + "/jobs",
        headers={**h, "Idempotency-Key": "reconcile"},
        json={
            "operation": "reconciliation",
            "payload": {
                "snapshot_id": snapshot,
                "account_ids": [a["id"] for a in accounts],
                "statement_source_id": source_id,
            },
        },
    )
    assert job.status_code == 202, job.text
    await process(job.json()["id"], h["X-Tenant-ID"])
    final = (await c.get(prefix + "/jobs/" + job.json()["id"], headers=h)).json()
    assert final["status"] == "completed", final
    result = (await c.get(prefix + "/events/" + final["result_id"], headers=h)).json()
    assert len(result["body"]["matches"]) == 1 and len(result["body"]["unmatched_left"]) == 1
    reviewer = await actor(h, "Firm Administrator", "reconciliation-independent-reviewer")
    await grant(c, h, base, reviewer)
    blocked = await c.post(
        prefix + "/events/" + result["id"] + "/review",
        headers=reviewer[0],
        json={
            "expected_version": 1,
            "action": "approve",
            "comments": "Synthetic supporting-table review must be enforced first",
        },
    )
    assert blocked.status_code == 409, blocked.text
    accepted = await c.post(
        prefix + "/events/" + result["id"] + "/review",
        headers=h,
        json={
            "expected_version": 1,
            "action": "accept",
            "item_id": result["body"]["matches"][0]["left_ids"][0],
            "comments": "Synthetic documented auditor acceptance of the proposed actual source match",
        },
    )
    assert accepted.status_code == 201, accepted.text
    exception = await c.post(
        prefix + "/events/" + accepted.json()["id"] + "/review",
        headers=h,
        json={
            "expected_version": 2,
            "action": "finding",
            "item_id": result["body"]["unmatched_left"][0]["id"],
            "comments": "Synthetic unresolved source posting retained as a reconciliation exception",
        },
    )
    assert exception.status_code == 201, exception.text
    assert exception.json()["body"]["exceptions"][0]["record_id"]

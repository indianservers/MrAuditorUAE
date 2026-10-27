import os
import uuid

import pytest
from sqlalchemy import select, text

from app.core.dependencies import Context
from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.ml import service
from app.modules.ml.models import MLEvent
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import action, actor, create, grant
from tests.phase6.test_workflows import prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated PostgreSQL required"
)


def test_actual_node_child_cancellation_signal():
    from redis import Redis

    from app.core.config import settings

    identifier = uuid.uuid4()
    with Redis.from_url(settings().redis_url) as redis:
        redis.setex("ml-cancel:" + str(identifier), 60, "1")
        try:
            with pytest.raises(service.TrainingCancelled):
                service.node(
                    "train",
                    config={
                        "family": "autoencoder",
                        "epochs": 100,
                        "batch_size": 32,
                        "learning_rate": 0.003,
                        "seed": 1,
                        "patience": 3,
                    },
                    job_id=identifier,
                )
        finally:
            redis.delete("ml-cancel:" + str(identifier))


async def test_dmtt_actual_ifrs_approval_computation_and_ai(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    eng = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    reviewer = await actor(h, "Pillar Two Reviewer", "p9-dmtt-review")
    await grant(c, h, base, reviewer)
    body = {
        "fiscal_start": "2026-01-01",
        "fiscal_end": "2026-12-31",
        "upe_name": "SYNTHETIC parent",
        "upe_jurisdiction": "GB",
        "multinational": True,
        "constituent_entity_ids": [eng["entity_id"]],
        "preceding_revenues": [
            {"year": y, "eur": "800000000", "evidence_id": note["id"]} for y in range(2022, 2026)
        ],
        "rule_version": "UAE-CD142-MD96/v2",
        "technical_evidence_id": note["id"],
        "synthetic": True,
    }
    group = await create(c, h, base, "dmtt-group", body)
    group = await action(c, h, base, group, "submit")
    await action(c, h, base, group, "approve", expected=403)
    group = await action(c, reviewer[0], base, group, "approve")
    e = {
        "group_id": group["id"],
        "entity_id": eng["entity_id"],
        "source_engagement_id": eid,
        "financial_run_id": financial["id"],
        "jurisdiction": "AE",
        "classification": "ordinary",
        "classification_evidence_id": note["id"],
        "fx_to_calculation": "1",
        "fx_evidence_id": note["id"],
        "current_tax": "108000",
        "covered_tax_evidence_id": note["id"],
        "substance_evidence_id": note["id"],
        "eligible_payroll": "100000",
        "eligible_tangible_assets": "200000",
    }
    obj = await create(c, h, base, "dmtt-entity", e)
    obj = await action(c, h, base, obj, "submit")
    await action(c, reviewer[0], base, obj, "approve")
    r = await c.post(f"/api/v1/dmtt/engagements/{eid}/groups/{group['id']}/calculate", headers=h)
    assert r.status_code == 201, r.text
    result = r.json()["body"]["results"]
    assert result["etr"] == "0.09"
    assert result["sbie"] == "24200.000"
    assert result["uae_dmtt"] == "70548.00"
    auditor = await actor(h, "Auditor", "p9-auditor")
    await grant(c, h, base, auditor)
    r = await c.get(f"/api/v1/dmtt/engagements/{eid}/calculations", headers=auditor[0])
    assert r.status_code == 403
    r = await c.get(f"{base}/dmtt-group", headers=auditor[0])
    assert r.status_code == 403
    from app.modules.dmtt.service import TASKS

    for task in TASKS:
        r = await c.post(
            f"/api/v1/dmtt/engagements/{eid}/ai",
            headers=h,
            json={"group_id": group["id"], "task": task},
        )
        assert r.status_code == 201, r.text
        assert r.json()["body"]["output"]["tax_position_approved"] is False
    r = await c.get("/api/v1/ml/events/" + r.json()["id"], headers=h)
    assert r.status_code == 404


async def test_real_tensorflow_artifacts_approval_inference_rls_and_feedback(environment):
    c = environment
    h, eid, base, manager, partner, p, adj, note, rules, ready, financial = await prepared(c)
    uid = decode_token(h["Authorization"].split()[1])
    tenant = uuid.UUID(h["X-Tenant-ID"])
    ctx = Context(uid, tenant, frozenset())
    rows = []
    split = []
    for name, n in [("train", 100), ("validation", 40), ("test", 40), ("ood", 20)]:
        for i in range(n):
            rows.append(
                {
                    "id": f"{name}-{i}",
                    "journal": f"{name}-{i}",
                    "client": name,
                    "date": "2025-01-01",
                    "debit": 100000 if i % 5 == 0 else 100 + i,
                    "credit": 0,
                    "currency": "AED",
                    "functional_currency": "AED",
                    "description": "Synthetic fixture",
                    "account": "expense",
                    "label": int(i % 5 == 0),
                    "label_kind": "synthetic_injected" if i % 5 == 0 else "synthetic_normal",
                    "category": i % 5,
                    "account_name": [
                        "Cash bank",
                        "Payable liability",
                        "Capital equity",
                        "Sales revenue",
                        "Payroll expense",
                    ][i % 5],
                }
            )
            split.append(name)
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        dataset = await service.event(
            db,
            ctx,
            uuid.UUID(eid),
            "dataset",
            {
                "object": service.put_json(
                    tenant, {"rows": rows, "split": split, "synthetic": True}
                ),
                "synthetic": True,
            },
        )
        dataset_id = dataset.id
        # This invokes genuine tfjs fitting and private artifact persistence in a dedicated child.
        out = await service.execute_job(
            db,
            ctx,
            {
                "operation": "train",
                "source_id": str(dataset_id),
                "config": {
                    "family": "journal-classifier",
                    "epochs": 3,
                    "batch_size": 32,
                    "learning_rate": 0.003,
                    "seed": 7,
                    "patience": 2,
                },
            },
        )
        model_id = out["id"]
    import asyncio

    from app.db.models.platform import BackgroundJob, Engagement

    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        pending = BackgroundJob(
            tenant_id=tenant,
            created_by=uid,
            idempotency_key=str(uuid.uuid4()),
            job_type="ml.train",
            status="running",
            payload={"source_id": str(dataset_id)},
        )
        db.add(pending)
        await db.flush()
        pending_id = pending.id
    # Progress/cancellation must not queue behind the engagement row locked by training.
    async with Session() as locked, locked.begin():
        await tenant_context(locked, str(tenant))
        await locked.scalar(
            select(Engagement).where(Engagement.id == uuid.UUID(eid)).with_for_update()
        )
        result = await asyncio.wait_for(c.get(f"/api/v1/ml/jobs/{pending_id}", headers=h), 2)
        assert result.status_code == 200, result.text
        result = await asyncio.wait_for(
            c.post(f"/api/v1/ml/jobs/{pending_id}/cancel", headers=h), 2
        )
        assert result.status_code == 200, result.text
    reviewer = await actor(h, "Model Risk Reviewer", "p9-model-review")
    await grant(c, h, base, reviewer)
    decision = {
        "rationale": "Synthetic independent review of held-out metrics and declared limitations",
        "experimental_use_acknowledged": True,
    }
    r = await c.post(f"/api/v1/ml/models/{model_id}/deployments", headers=h, json=decision)
    assert r.status_code == 409
    r = await c.post(f"/api/v1/ml/models/{model_id}/approval-requests", headers=h, json=decision)
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/ml/models/{model_id}/approvals", headers=h, json=decision)
    assert r.status_code == 403
    r = await c.post(f"/api/v1/ml/models/{model_id}/approvals", headers=reviewer[0], json=decision)
    assert r.status_code == 201, r.text
    r = await c.post(
        f"/api/v1/ml/models/{model_id}/deployments", headers=reviewer[0], json=decision
    )
    assert r.status_code == 201, r.text
    deployment = r.json()["id"]
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        result = await service.execute_job(
            db,
            ctx,
            {
                "operation": "infer",
                "source_id": deployment,
                "dataset_id": str(dataset_id),
                "offset": 140,
                "limit": 40,
            },
        )
        inference_id = result["id"]
        model = await db.get(MLEvent, uuid.UUID(model_id))
        assert model.body["metrics"]["reload_max_delta"] <= 1e-6
        assert len(model.body["metrics"]["history"]) > 0
        ledger_dataset = await service.execute_job(
            db, ctx, {"operation": "dataset", "engagement_id": eid}
        )
        ledger_scored = await service.execute_job(
            db,
            ctx,
            {
                "operation": "infer",
                "source_id": deployment,
                "dataset_id": ledger_dataset["id"],
                "offset": 0,
                "limit": 1000,
            },
        )
        ledger_result = await db.get(MLEvent, uuid.UUID(ledger_scored["id"]))
        assert ledger_result.body["execution_mode"] == "trained_model"
        assert ledger_result.body["backend"] == "cpu"
        assert ledger_result.body["source_snapshots"]
        assert ledger_result.body["language_model_dependency"] is False
    r = await c.get("/api/v1/ml/events/" + inference_id, headers=h)
    assert r.status_code == 200
    predictions = r.json()["body"]["predictions"]
    assert len(predictions) == 40
    assert predictions[0]["fraud_conclusion"] is False
    r = await c.post(
        f"/api/v1/ml/predictions/{inference_id}/feedback",
        headers=h,
        json={
            "transaction_id": "test-0",
            "label": "valid_exception",
            "evidence_id": note["id"],
            "rationale": "Synthetic evidence-backed reviewer outcome for controlled curation",
        },
    )
    assert r.status_code == 201, r.text
    assert not r.json()["body"]["eligible_for_training"]
    feedback_id = r.json()["id"]
    r = await c.post(
        f"/api/v1/ml/predictions/{inference_id}/explanation",
        headers=h,
        json={"transaction_id": "test-0", "model": "mock-diagnostic"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["body"]["score_changes"] is False
    assert r.json()["body"]["execution_mode"] == "diagnostic_mock"
    assert r.json()["body"]["prediction_execution_mode"] == "trained_model"

    r = await c.post(
        f"/api/v1/ml/datasets/{dataset_id}/curation",
        headers=h,
        json={
            "feedback_ids": [feedback_id],
            "rationale": "Independent evidence curation before controlled retraining",
        },
    )
    assert r.status_code == 403
    r = await c.post(
        f"/api/v1/ml/datasets/{dataset_id}/curation",
        headers=reviewer[0],
        json={
            "feedback_ids": [feedback_id],
            "rationale": "Independent evidence curation before controlled retraining",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["body"]["automatic_retraining"] is False
    async with Session() as db, db.begin():
        await tenant_context(db, str(uuid.uuid4()))
        assert await db.scalar(select(MLEvent.id).where(MLEvent.id == uuid.UUID(model_id))) is None
    async with Session() as db:
        await tenant_context(db, str(tenant))
        with pytest.raises(Exception):
            await db.execute(
                text("UPDATE ml_registry_events SET kind=kind WHERE id=:id"), {"id": model_id}
            )
        await db.rollback()

"""Mode provenance and real governed jobs, without an external language model."""

import os
import uuid

import pytest
from sqlalchemy import select

from app.core.dependencies import Context
from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.accounting.models import ImportBatch, ImportSnapshot
from app.modules.enterprise_ai.schemas import ToolInput
from app.modules.enterprise_ai.tools import invoke
from app.modules.ml import service
from app.modules.ml.models import MLEvent
from app.workers.accounting import process
from tests.integration.test_platform import environment as environment
from tests.phase6.test_workflows import prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated test database required"
)


async def test_explicit_baselines_real_jobs_tools_and_source_staleness(environment, monkeypatch):
    from app.workers.accounting import work

    monkeypatch.setattr(work, "apply_async", lambda **kwargs: None)
    monkeypatch.setenv("AI_API_KEY", "")
    c = environment
    h, eid, *_ = await prepared(c)
    uid = decode_token(h["Authorization"].split()[1])
    tenant = uuid.UUID(h["X-Tenant-ID"])
    ctx = Context(uid, tenant, frozenset())
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        built = await service.execute_job(db, ctx, {"operation": "dataset", "engagement_id": eid})
        dataset_id = built["id"]
    modes = []
    for mode in ["rules_baseline", "statistical_baseline", "diagnostic_mock"]:
        queued = await c.post(
            "/api/v1/ml/inference/baselines",
            headers=h,
            json={"dataset_id": dataset_id, "mode": mode},
        )
        assert queued.status_code == 202, queued.text
        await process(queued.json()["id"], str(tenant), str(uid))
        status = (await c.get("/api/v1/ml/jobs/" + queued.json()["id"], headers=h)).json()
        assert status["status"] == "completed", status
        assert status["execution_mode"] == mode
        prediction_id = status["result"]["resource_id"]
        details = (await c.get("/api/v1/ml/events/" + prediction_id, headers=h)).json()
        modes.append((prediction_id, details))
        assert details["body"]["language_model_dependency"] is False
        assert details["body"]["entity_id"] and details["body"]["period_id"]
        assert details["body"]["source_snapshots"]
        assert details["body"]["predictions"][0]["review_status"] == "UNREVIEWED"
        if mode == "diagnostic_mock":
            assert details["body"]["predictions"][0]["score"] is None
    invalid = await c.post(
        "/api/v1/ml/inference/baselines",
        headers=h,
        json={"dataset_id": dataset_id, "mode": "trained_model"},
    )
    assert invalid.status_code == 422
    denied = await c.get(
        "/api/v1/ml/events/" + modes[0][0], headers={**h, "X-Tenant-ID": str(uuid.uuid4())}
    )
    assert denied.status_code in {403, 404}
    capabilities = await c.get(f"/api/v1/ml/engagements/{eid}/capabilities", headers=h)
    assert capabilities.status_code == 200
    assert capabilities.json()["language_model_dependency"] is False
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        facts = await invoke(db, ctx, uuid.UUID(eid), "ml.get_predictions", ToolInput())
        assert facts.status == "COMPLETED"
        assert {item["facts"]["execution_mode"] for item in facts.data["items"]} == {
            "rules_baseline",
            "statistical_baseline",
            "diagnostic_mock",
        }
        dataset = await db.get(MLEvent, uuid.UUID(dataset_id))
        snap = await db.get(ImportSnapshot, uuid.UUID(dataset.body["source_snapshots"][0]["id"]))
        batch = await db.scalar(select(ImportBatch).where(ImportBatch.id == snap.batch_id))
        batch.status = "superseded"
    details = await c.get("/api/v1/ml/events/" + modes[0][0], headers=h)
    assert details.json()["freshness"]["status"] == "STALE"
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        facts = await invoke(db, ctx, uuid.UUID(eid), "ml.get_predictions", ToolInput())
        assert facts.status == "MISSING"

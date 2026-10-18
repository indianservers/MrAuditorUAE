import os
import uuid

import pytest
from sqlalchemy import update

from app.db.session import Session, tenant_context
from app.modules.accounting.models import ImportBatch
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed
from tests.phase4.test_workflows import setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Migrated disposable PostgreSQL required"
)


async def test_snapshot_receipt_is_invalidated_when_import_is_superseded(environment):
    c = environment
    h, options, eid, _ = await setup(c)
    batch, snapshot = await committed(c, h, options)
    created = await c.post(
        "/api/v1/ai/command",
        headers=h,
        json={
            "engagement_id": eid,
            "task": "audit-planning",
            "prompt": "Synthetic current population review",
            "idempotency_key": "p11-financial-lineage",
        },
    )
    assert created.status_code == 201, created.text
    url = f"/api/v1/ai/engagements/{eid}/investigations/{created.json()['id']}"
    step = await c.post(url + "/step", headers=h)
    assert step.status_code == 200, step.text
    detail = await c.get(url, headers=h)
    assert detail.status_code == 200, detail.text
    result = next(e["body"]["result"] for e in detail.json()["events"] if e["kind"] == "step")
    assert result["sources"][0]["type"] == "snapshot" and result["sources"][0]["id"] == snapshot
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        await db.execute(
            update(ImportBatch)
            .where(
                ImportBatch.tenant_id == uuid.UUID(h["X-Tenant-ID"]),
                ImportBatch.id == uuid.UUID(batch),
            )
            .values(status="superseded")
        )
    assert (await c.get(url, headers=h)).status_code == 409
    assert (await c.post(url + "/step", headers=h)).status_code == 409

import json
import os
import uuid

import pytest

from app.core.dependencies import Context
from app.core.security import decode_token
from app.db.session import Session, tenant_context
from app.modules.ml import service
from tests.integration.test_platform import environment as environment
from tests.phase6.test_workflows import prepared

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_reviewed_foundation_labels_require_evidence_and_preserve_scope(environment):
    c = environment
    h, eid, _, _, _, _, _, note, *_ = await prepared(c)
    tenant = uuid.UUID(h["X-Tenant-ID"])
    ctx = Context(decode_token(h["Authorization"].split()[1]), tenant, frozenset())
    async with Session() as db, db.begin():
        await tenant_context(db, str(tenant))
        built = await service.execute_job(db, ctx, {"operation": "dataset", "engagement_id": eid})
        source = await service.get(db, ctx, uuid.UUID(built["id"]), "dataset")
        original = json.loads(service.read_object(source.body["object"]))
    body = {
        "task": "journal-type",
        "labels": {r["journal"]: "sales" for r in original["rows"]},
        "train_end": "2026-03-31",
        "validation_end": "2026-09-30",
        "evidence_id": note["id"],
        "rationale": "Reviewed synthetic fixture to verify the governed label contract.",
    }
    route = f"/api/v1/ml/datasets/{built['id']}/foundation-labels"
    response = await c.post(route, headers=h, json=body)
    assert response.status_code == 201, response.text
    current = response.json()["body"]
    assert current["foundation_manifest"]["task"] == "journal-type"
    assert current["source_snapshots"]
    assert current["training_eligible"] is True
    denied = await c.post(route, headers={**h, "X-Tenant-ID": str(uuid.uuid4())}, json=body)
    assert denied.status_code in {403, 404}
    invalid = await c.post(route, headers=h, json={**body, "labels": {"absent": "suspicious"}})
    assert invalid.status_code == 422

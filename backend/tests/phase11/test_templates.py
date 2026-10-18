import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Migrated disposable PostgreSQL required"
)


async def test_configured_readonly_graph_activation_and_execution(environment):
    c = environment
    h, options, eid, base = await setup(c)
    path = f"/api/v1/ai/engagements/{eid}"
    payload = {
        "title": "Synthetic reviewed read-only workflow",
        "nodes": ["audit.get_evidence", "quality.validate_sources"],
        "edges": [[0, 1]],
        "idempotency_key": "phase11-custom-template",
    }
    r = await c.post(path + "/workflows", headers=h, json=payload)
    assert r.status_code == 201, r.text
    template = r.json()
    replay = await c.post(path + "/workflows", headers=h, json=payload)
    assert replay.json()["id"] == template["id"]
    assert (
        await c.post(path + f"/investigations/{template['id']}/step", headers=h)
    ).status_code == 409
    invalid = await c.post(
        path + "/workflows",
        headers=h,
        json={
            **payload,
            "nodes": ["shell.exec", "quality.validate_sources"],
            "idempotency_key": "phase11-invalid-template",
        },
    )
    assert invalid.status_code == 422
    command = await c.post(
        "/api/v1/ai/command",
        headers=h,
        json={
            "engagement_id": eid,
            "template_id": template["id"],
            "prompt": "Synthetic explicit custom workflow execution",
            "idempotency_key": "phase11-template-run",
        },
    )
    assert command.status_code == 201, command.text
    run = command.json()
    assert run["plan"] == payload["nodes"]
    for _ in payload["nodes"]:
        r = await c.post(path + f"/investigations/{run['id']}/step", headers=h)
        assert r.status_code == 200, r.text
    assert r.json()["state"] == "PARTIALLY_COMPLETED"

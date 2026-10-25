"""One implementation snapshot per request; all source freshness checks still run."""

import os

import pytest

from app.core import operations_contracts
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import setup
from tests.qa_crud.test_country_workflows import double_boundaries, source
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def test_history_rechecks_implementation_once_per_new_request(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, _ = await setup(c)
    for number in range(5):
        await source(c, h, eid, [transaction(id=f"S{number}")], f"SYNTHETIC source {number}")
    original = operations_contracts.country_workflow_hash
    calls = []
    changed = False

    def fingerprint():
        calls.append(1)
        return "SYNTHETIC-ROLLOUT" if changed else original()

    monkeypatch.setattr(operations_contracts, "country_workflow_hash", fingerprint)
    path = f"/api/v1/intelligence/engagements/{eid}/events?newest=true&limit=100"
    for expected_calls in (1, 2):
        listed = await c.get(path, headers=h)
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["items"]) == 5
        assert {item["freshness"] for item in listed.json()["items"]} == {"CURRENT"}
        assert len(calls) == expected_calls
    changed = True
    listed = await c.get(path, headers=h)
    assert listed.status_code == 200, listed.text
    assert {item["freshness"] for item in listed.json()["items"]} == {"STALE"}
    assert len(calls) == 3

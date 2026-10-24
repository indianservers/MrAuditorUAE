"""Country-neutral calendar choices persist with each real analytics run."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import committed, scope

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database required"
)


async def test_assessed_operating_calendar_is_preserved_and_changes_weekend_findings(environment):
    client = environment
    headers, options = await scope(client)
    _, snapshot = await committed(client, headers, options)
    for days, count, status in [([5], 2, "warning"), ([4], 0, "passed"), ([], 0, "not_testable")]:
        response = await client.post(
            "/api/v1/analytics/runs",
            headers=headers,
            json={
                "snapshot_id": snapshot,
                "weekend_days": days,
                "calendar_rationale": "Synthetic assessed calendar for this population"
                if days
                else "",
            },
        )
        assert response.status_code == 201, response.text
        run = response.json()
        weekend = next(row for row in run["result"]["rules"] if row["rule_id"] == "J01")
        assert weekend["flagged_count"] == count
        assert weekend["status"] == status
        assert weekend["parameters"]["weekend_days"] == days
        retained = await client.get(f"/api/v1/analytics/runs/{run['id']}", headers=headers)
        assert retained.status_code == 200, retained.text
        assert retained.json()["parameters"]["weekend_days"] == days
    rejected = await client.post(
        "/api/v1/analytics/runs",
        headers=headers,
        json={"snapshot_id": snapshot, "weekend_days": [5]},
    )
    assert rejected.status_code == 422, rejected.text

"""Protected original group inspection over real DB/API; scanner/broker are doubled."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import setup
from tests.qa_crud.test_country_workflows import bank_payload, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import transaction

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_brs_exact_original_rows_bounds_and_engagement_scope(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, _ = await setup(c)
    else:
        h, eid, _ = await india_context(c)
    book = await source(
        c,
        h,
        eid,
        [transaction(id="B1", currency=currency)],
        "SYNTHETIC books",
        totals={currency: "100"},
    )
    bank = await source(
        c,
        h,
        eid,
        [transaction(id="S1", currency=currency)],
        "SYNTHETIC bank",
        totals={currency: "100"},
    )
    result = await execute(
        c, h, eid, "country-workflow", bank_payload(book, bank, currency=currency)
    )
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}/bank-matched-proposal"
    response = await c.get(path, headers=h, params={"index": 0})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposal"]["left_ids"] == ["B1"]
    assert body["books"][0]["reference"] == transaction()["reference"]
    assert body["statement"][0]["id"] == "S1"
    assert body["statement"][0]["currency"] == currency
    assert body["total"] == 1 and body["index"] == 0
    assert (await c.get(path, headers=h, params={"index": -1})).status_code == 422
    assert (await c.get(path, headers=h, params={"index": 1})).status_code == 404
    wrong_kind = path.replace(result["id"], book["id"])
    assert (await c.get(wrong_kind, headers=h, params={"index": 0})).status_code == 422
    engagement = (await c.get("/api/v1/engagements/" + eid, headers=h)).json()
    created = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": engagement["entity_id"],
            "period_id": engagement["period_id"],
            "name": "SYNTHETIC other match scope",
            "engagement_type": "External Audit",
        },
    )
    assert created.status_code == 201, created.text
    wrong_scope = path.replace(eid, created.json()["id"])
    assert (await c.get(wrong_scope, headers=h, params={"index": 0})).status_code == 404

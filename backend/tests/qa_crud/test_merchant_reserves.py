"""Real API/DB/storage/processor; scanner and dispatch are explicit doubles."""

import io
import os
from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_merchant_reserves import ROLES, controls, fixture, payload

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable migrated database required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_reserve_independent_sources_review_export_and_ledger_withdrawal(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "reserve-independent-reviewer")
    await grant(c, h, base, reviewer)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    config = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert next(w for w in config["items"] if w["id"] == "merchant-reserve-rollforward")[
        "available"
    ]
    retained = {}
    for role, records in fixture(country).items():
        totals = (
            {currency: str(sum((Decimal(row["amount"]) for row in records), Decimal(0)))}
            if role in {"settlements", "ledger"}
            else {}
        )
        retained[role] = await source(
            c,
            h,
            eid,
            records,
            "SYNTHETIC reserve " + role,
            ROLES[role],
            totals,
            **controls(role, records, currency),
        )
    params = payload(
        currency=currency, source_ids={role: obj["id"] for role, obj in retained.items()}
    ).model_dump(mode="json")
    await execute(c, h, eid, "country-workflow", params, failed="Independently review all merchant")
    for role, obj in retained.items():
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        retained[role] = reviewed.json()
    params["source_ids"] = {role: obj["id"] for role, obj in retained.items()}
    result = await execute(c, h, eid, "country-workflow", params)
    assert not result["body"]["blocked"]
    assert result["body"]["rows"][0]["computed_closing"] == "145"
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    obj = approved.json()
    exported = await c.get(prefix + f"/events/{obj['id']}/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content))
    movements = list(workbook["Reserve movements"].values)
    assert len(movements) == 4
    assert movements[-1][movements[0].index("balance_after")] == "145"
    assert len(list(workbook["Reserve balance links"].values)) == 2
    before = deepcopy(obj["body"])
    withdrawn = await decision(c, reviewer[0], eid, retained["ledger"], "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    stale = (await c.get(prefix + f"/events/{obj['id']}", headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == before
    assert (await decision(c, reviewer[0], eid, obj)).status_code == 409

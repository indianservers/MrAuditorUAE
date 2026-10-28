"""Real API, DB, storage and job processing; scanner/broker are explicit doubles."""

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
from tests.unit.test_merchant_settlements import COMPONENTS, ROLES, payload, populations

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable migrated database required"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_merchant_sources_review_export_and_withdrawal(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "merchant-independent-reviewer")
    await grant(c, h, base, reviewer)
    prefix = f"/api/v1/intelligence/engagements/{eid}"
    config = (await c.get(prefix + "/country-workflows", headers=h)).json()
    assert next(w for w in config["items"] if w["id"] == "merchant-settlement-bridge")["available"]
    retained = {}
    for role, records in populations(country).items():
        controls = {currency: str(sum((Decimal(row["amount"]) for row in records), Decimal(0)))}
        options = {}
        if role == "processor":
            options["merchant_component_controls"] = {
                currency: {field: records[0][field] for field in COMPONENTS}
            }
        retained[role] = await source(
            c, h, eid, records, "SYNTHETIC merchant " + role, ROLES[role], controls, **options
        )
    params = payload(
        currency=currency, source_ids={role: obj["id"] for role, obj in retained.items()}
    )
    await execute(c, h, eid, "country-workflow", params, failed="Independently review all merchant")
    for role, obj in retained.items():
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        retained[role] = reviewed.json()
    params["source_ids"] = {role: obj["id"] for role, obj in retained.items()}
    result = await execute(c, h, eid, "country-workflow", params)
    assert result["body"]["rows"][0]["expected_net"] == "800"
    assert result["body"]["rows"][0]["bank_difference"] == "0"
    assert not result["body"]["blocked"]
    assert (await decision(c, h, eid, result)).status_code == 403
    approved = await decision(c, reviewer[0], eid, result)
    assert approved.status_code == 201, approved.text
    obj = approved.json()
    response = await c.get(prefix + f"/events/{obj['id']}/export?format=xlsx", headers=h)
    assert response.status_code == 200, response.text
    rows = list(load_workbook(io.BytesIO(response.content))["Rows"].values)
    assert rows[1][rows[0].index("expected_net")] == "800"
    assert rows[1][rows[0].index("fee_tax_kind")] == ("UAE_VAT" if country == "AE" else "INDIA_GST")
    before = deepcopy(obj["body"])
    withdrawn = await decision(c, reviewer[0], eid, retained["processor"], "reject")
    assert withdrawn.status_code == 201, withdrawn.text
    stale = (await c.get(prefix + f"/events/{obj['id']}", headers=h)).json()
    assert stale["freshness"] == "STALE" and stale["body"] == before
    assert (await decision(c, reviewer[0], eid, obj)).status_code == 409

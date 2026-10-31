"""Identified stock through existing approved-record calculation and revision APIs."""

import os
from decimal import Decimal

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import create, setup
from tests.phase5.test_reporting import prepared
from tests.qa_crud.test_accounting_strengthening import post, revise
from tests.unit.test_inventory_identified_units import body, issue, unit
from tests.unit.test_inventory_project_layers import project

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable database"
)


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
@pytest.mark.parametrize("basis", ["individual_unit", "segregated_project_lot"])
async def test_identified_inventory_review_calculation_and_revision(
    environment, country, currency, basis
):
    c = environment
    scope = await setup(c)
    if country == "IN":
        h, opts, _, _ = scope
        entity = await post(
            c,
            h,
            "/api/v1/entities",
            {
                "client_id": opts["client_id"],
                "name": "SYN identified India stock",
                "country": country,
                "jurisdiction": "Synthetic India financial accounting",
                "functional_currency": currency,
                "presentation_currency": currency,
            },
        )
        period = await post(
            c,
            h,
            "/api/v1/financial-periods",
            {
                "entity_id": entity["id"],
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
        engagement = await post(
            c,
            h,
            "/api/v1/engagements",
            {
                "entity_id": entity["id"],
                "period_id": period["id"],
                "name": "SYN India inventory accounting",
                "engagement_type": "External Audit",
            },
        )
        opts.update(entity_id=entity["id"], period_id=period["id"], currency=currency)
        scope = h, opts, engagement["id"], f"/api/v1/engagements/{engagement['id']}/audit"
    h, eid, base, reviewer, _, profile, _, _, ready = await prepared(
        c, scope_data=scope, suffix="identified" + country
    )
    api = f"/api/v1/ifrs/engagements/{eid}"
    expensive = unit("SYN-machine-B", "300")
    expensive.update(issues=[issue()], expected_closing_quantity="0")
    data = {**body(unit("SYN-machine-A", "100"), expensive), "profile_id": profile["id"]}
    if basis == "segregated_project_lot":
        data["items"] = [project()]
    workspace = await c.get(api + "/workspace", headers=h)
    assert workspace.status_code == 200
    assert (
        "segregated_project_lot"
        in workspace.json()["schemas"]["inventory"]["$defs"]["InventoryItem"]["properties"][
            "identification_basis"
        ]["enum"]
    )
    draft = await create(c, h, base, "ifrs-inventory", data)
    await post(c, h, api + "/calculate/" + draft["id"], status=409)
    source = await ready("inventory", data)
    first = await post(c, h, api + "/calculate/" + source["id"])
    expected = 203 if basis == "segregated_project_lot" else 100
    assert Decimal(first["results"]["closing_carrying"]) == expected
    assert first["results"]["movements"][0]["identification_reference"] == (
        "SYN-project-A" if basis == "segregated_project_lot" else "SYN-machine-B"
    )
    current = await c.get(api + "/runs/" + first["id"], headers=h)
    assert current.status_code == 200
    assert current.json()["dependencies_current"]
    if basis == "segregated_project_lot":
        assert len(first["results"]["identified_layers"]) == 3
        assert len(first["results"]["identified_allocations"]) == 2
        data["items"][0]["opening_layers"][0]["unit_cost"] = "20"
    else:
        data["items"][0]["opening_unit_cost"] = "120"
    source = await revise(c, h, reviewer[0], base, source, data)
    response = await c.get(api + "/runs/" + first["id"], headers=h)
    assert response.status_code == 200
    assert not response.json()["dependencies_current"]
    assert Decimal(response.json()["results"]["closing_carrying"]) == expected
    second = await post(c, h, api + "/calculate/" + source["id"])
    assert Decimal(second["results"]["closing_carrying"]) == expected + 20
    assert second["id"] != first["id"]

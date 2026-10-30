import os
import uuid

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import document

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


@pytest.mark.parametrize(
    "country,functional,presentation",
    [
        ("AE", "AED", "AED"),
        ("IN", "INR", "INR"),
        ("IN", "USD", "INR"),
        ("AE", "EUR", "AED"),
    ],
)
async def test_fresh_workflow_default_uses_authorized_entity_functional_currency(
    environment, country, functional, presentation
):
    c = environment
    h, options, _, _ = await setup(c)
    entity = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": options["client_id"],
            "name": "SYNTHETIC workflow currency entity",
            "country": country,
            "jurisdiction": "Synthetic country scope",
            "functional_currency": functional,
            "presentation_currency": presentation,
        },
    )
    assert entity.status_code == 201, entity.text
    period = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={
            "entity_id": entity.json()["id"],
            "start_date": "2026-04-01",
            "end_date": "2027-03-31",
        },
    )
    assert period.status_code == 201, period.text
    engagement = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": entity.json()["id"],
            "period_id": period.json()["id"],
            "name": "SYNTHETIC currency defaults",
            "engagement_type": "External Audit",
        },
    )
    assert engagement.status_code == 201, engagement.text
    response = await c.get(
        f"/api/v1/intelligence/engagements/{engagement.json()['id']}/country-workflows", headers=h
    )
    assert response.status_code == 200, response.text
    assert response.json()["country"] == country
    assert response.json()["default_currency"] == functional
    assert response.json()["default_currency_basis"] == "ENTITY_FUNCTIONAL_CURRENCY"


async def test_currency_metadata_is_not_visible_to_another_tenant(environment):
    c = environment
    h, _, eid, _ = await setup(c)
    other = {**h, "X-Tenant-ID": str(uuid.uuid4())}
    response = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=other
    )
    assert response.status_code == 403, response.text
    assert "default_currency" not in response.json()


async def test_original_foreign_invoice_currency_survives_the_real_job_and_review_path(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "original-currency-reviewer")
    await grant(c, h, base, reviewer)
    ids = {}
    for role in ["books", "invoices"]:
        prepared = await source(
            c,
            h,
            eid,
            [document(id=role, currency="USD", component="CGST")],
            "SYNTHETIC original USD " + role,
            "tax-documents",
            {"USD": "5"},
        )
        checked = await decision(c, reviewer[0], eid, prepared)
        assert checked.status_code == 201, checked.text
        ids[role] = checked.json()["id"]
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-invoice-register",
            "invoice_direction": "purchase",
            "source_ids": ids,
            "currency": "USD",
            "as_of": "2026-06-30",
            "title": "SYNTHETIC original USD comparison",
            "rationale": "Synthetic independently reviewed original amounts; no INR conversion or GST return claim",
        },
    )
    assert result["body"]["parameters"]["currency"] == "USD"
    assert (
        result["body"]["rows"][0]["currency"] == "USD"
        and result["body"]["rows"][0]["state"] == "MATCHED"
    )
    assert not result["body"]["statutory_calculation_qualified"]
    assert "gst_reporting_currency_contract" not in result["body"]
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text

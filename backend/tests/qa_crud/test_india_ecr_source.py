import os

import pytest

from app.modules.country_workflows.schemas import Obligation
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import scope
from tests.phase4.test_workflows import create
from tests.qa_crud.test_country_workflows import double_boundaries, execute, source
from tests.unit.test_india_ecr_source import ECR

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def india_context(c):
    h, existing = await scope(c)
    response = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": existing["client_id"],
            "name": "SYNTHETIC ECR India entity",
            "country": "IN",
            "jurisdiction": "Synthetic India",
            "functional_currency": "INR",
            "presentation_currency": "INR",
        },
    )
    assert response.status_code == 201, response.text
    entity = response.json()["id"]
    response = await c.post(
        "/api/v1/financial-periods",
        headers=h,
        json={"entity_id": entity, "start_date": "2026-04-01", "end_date": "2027-03-31"},
    )
    assert response.status_code == 201, response.text
    response = await c.post(
        "/api/v1/engagements",
        headers=h,
        json={
            "entity_id": entity,
            "period_id": response.json()["id"],
            "name": "SYNTHETIC ECR statutory audit",
            "engagement_type": "External Audit",
        },
    )
    assert response.status_code == 201, response.text
    eid = response.json()["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    return h, eid, base


async def test_ecr_original_source_and_three_way_statutory_reconciliation(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("synthetic-monthly-ecr.txt", ECR, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    native = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "india-epfo-ecr",
            "table_type": "obligations",
            "employer_registration": "SYNTHETIC-EPFO-001",
            "obligation_period": "2026-06",
            "obligation_due_date": "2026-07-15",
            "expected_members": 2,
            "expected_rows": 7,
            "control_totals": {"INR": "6100"},
            "label": "SYNTHETIC native monthly ECR",
        },
    )
    assert native["body"]["native_metadata"]["member_count"] == 2
    assert native["body"]["native_metadata"]["payment_execution"] == "NOT_EVIDENCED_BY_RETURN_TEXT"
    assert all(row["payment_date"] is None for row in native["body"]["rows"])
    assert native["body"]["review_status"] == "UNVERIFIED"
    original = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == ECR
    expected_rows = [
        {key: value for key, value in row.items() if key in Obligation.model_fields}
        for row in native["body"]["rows"]
    ]
    expected = await source(
        c,
        h,
        eid,
        expected_rows,
        "SYNTHETIC independently reviewed expected PF dues",
        "obligations",
        {"INR": "6100"},
    )
    payments = [{**row, "payment_date": "2026-07-10"} for row in expected_rows]
    payment = await source(
        c, h, eid, payments, "SYNTHETIC independent bank allocation", "obligations", {"INR": "6100"}
    )
    payload = {
        "workflow": "statutory-dues",
        "source_ids": {
            "expected": expected["id"],
            "return": native["id"],
            "payment": payment["id"],
        },
        "as_of": "2026-07-31",
        "currency": "INR",
        "title": "Synthetic three-way PF bridge",
        "rationale": "Explicit principal components compared with independent synthetic schedules",
    }
    reconciled = await execute(c, h, eid, "country-workflow", payload)
    assert reconciled["body"]["exception_count"] == 0
    assert not reconciled["body"]["statutory_calculation_qualified"]
    metadata = await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    assert next(
        item for item in metadata.json()["source_formats"] if item["id"] == "india-epfo-ecr"
    )["available"]

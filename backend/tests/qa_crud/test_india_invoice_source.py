import json
import os

import pytest

from app.modules.country_workflows.schemas import TaxDocument
from tests.integration.test_platform import environment as environment
from tests.phase2.test_pipeline import scope
from tests.phase4.test_workflows import create
from tests.qa_crud.test_country_workflows import double_boundaries, execute
from tests.qa_crud.test_country_workflows import source as csv_source
from tests.unit.test_india_invoice_source import BUYER, invoice

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required"
)


async def test_india_native_invoice_retained_evidence_job_and_country_gating(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, existing = await scope(c)
    response = await c.post(
        "/api/v1/entities",
        headers=h,
        json={
            "client_id": existing["client_id"],
            "name": "SYNTHETIC India invoice entity",
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
            "name": "SYNTHETIC India source audit",
            "engagement_type": "External Audit",
        },
    )
    assert response.status_code == 201, response.text
    eid = response.json()["id"]
    base = f"/api/v1/engagements/{eid}/audit"
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    content = json.dumps(invoice()).encode()
    uploaded = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("synthetic-inv01.json", content, "application/json")},
    )
    assert uploaded.status_code == 201, uploaded.text
    source = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": uploaded.json()["id"],
            "file_format": "india-inv01-json",
            "table_type": "tax-documents",
            "label": "SYNTHETIC INV-01 source",
            "expected_rows": 5,
            "control_totals": {"INR": "18"},
            "gst_registration": BUYER,
            "gst_direction": "purchase",
            "gst_period": "2026-06",
        },
    )
    assert source["kind"] == "workflow-source"
    assert source["body"]["native_controls_verified"]
    assert source["body"]["row_count"] == 5
    assert source["body"]["native_metadata"]["irp_authenticity"] == "NOT_VERIFIED"
    assert source["body"]["source_sha256"] == uploaded.json()["sha256"]
    choices = await c.get(f"/api/v1/intelligence/engagements/{eid}/events?newest=true", headers=h)
    assert (
        next(item for item in choices.json()["items"] if item["id"] == source["id"])["label"]
        == "SYNTHETIC INV-01 source"
    )
    original = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + uploaded.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == content
    metadata = await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    formats = {f["id"]: f for f in metadata.json()["source_formats"]}
    assert formats["india-inv01-json"]["available"]
    assert not formats["uae-wps-sif"]["available"]
    book_row = {
        key: value
        for key, value in source["body"]["rows"][0].items()
        if key in TaxDocument.model_fields
    }
    register = await csv_source(
        c,
        h,
        eid,
        [book_row],
        "SYNTHETIC independent sparse purchase register",
        "tax-documents",
        {"INR": "18"},
    )
    reconciled = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "india-gst",
            "source_ids": {"books": register["id"], "return": source["id"]},
            "as_of": "2026-06-30",
            "currency": "INR",
            "title": "Synthetic native invoice reconciliation",
            "rationale": "Independent sparse register compared to native invoice controls",
        },
    )
    assert reconciled["body"]["exception_count"] == 0
    assert (
        sum(
            row["comparison_basis"]
            == "EXPLICIT_NATIVE_ZERO_COMPONENT_WITH_OPPOSITE_DOCUMENT_PRESENT"
            for row in reconciled["body"]["rows"]
        )
        == 4
    )

"""Real persisted sources cannot label foreign amounts as India GST reporting totals."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import document

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


async def test_inr_reporting_comparison_export_and_foreign_source_rejection(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "gst-currency-reviewer")
    await grant(c, h, base, reviewer)
    sources = {}
    for role, currency in [("books", "INR"), ("return", "INR"), ("foreign", "AED")]:
        value = await source(
            c,
            h,
            eid,
            [document(id=role, currency=currency, component="CGST")],
            "SYNTHETIC currency " + role,
            "tax-documents",
            {currency: "5"},
        )
        reviewed = await decision(c, reviewer[0], eid, value)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()
    data = {
        "workflow": "india-gst",
        "source_ids": {role: sources[role]["id"] for role in ["books", "return"]},
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "SYNTHETIC INR GST reporting comparison",
        "rationale": "Synthetic explicit reported currency, no FX conversion inferred",
    }
    result = await execute(c, h, eid, "country-workflow", data)
    assert result["body"]["rows"][0]["state"] == "MATCHED"
    assert result["body"]["gst_reporting_currency"] == "INR"
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    endpoint = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}"
    exported = await c.get(endpoint + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    book = load_workbook(io.BytesIO(exported.content), read_only=True)
    metadata = dict(book["Source and review"].values)
    assert metadata["gst_reporting_currency"] == "INR"
    assert metadata["gst_reporting_currency_contract"] == "india-gst-inr-comparison/1"
    # The complete original result is also checked through the event endpoint.
    saved = await c.get(endpoint, headers=h)
    assert saved.json()["body"]["gst_reporting_currency_contract"] == "india-gst-inr-comparison/1"
    rows = list(book["Rows"].values)
    assert len(rows) == 2
    exported_row = dict(zip(rows[0], rows[1], strict=True))
    assert exported_row["currency"] == "INR" and exported_row["state"] == "MATCHED"
    historical = deepcopy(saved.json()["body"])
    book.close()
    for role in ["books", "return"]:
        wrong = deepcopy(data)
        wrong["source_ids"][role] = sources["foreign"]["id"]
        failed = await execute(c, h, eid, "country-workflow", wrong, failed="INR reporting amounts")
        assert "INR reporting amounts" in str(failed)

    wrong = deepcopy(data)
    wrong["currency"] = "AED"
    await execute(c, h, eid, "country-workflow", wrong, failed="INR reporting amounts")
    retained = await c.get(endpoint, headers=h)
    assert retained.json()["freshness"] == "CURRENT" and retained.json()["body"] == historical

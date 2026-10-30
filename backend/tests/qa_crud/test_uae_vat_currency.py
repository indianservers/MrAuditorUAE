"""Real persisted sources cannot label foreign amounts as UAE VAT reporting totals."""

import io
import os
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.unit.country_workflow_cases import document

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated test DB")


async def test_aed_reporting_comparison_export_and_foreign_source_rejection(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "vat-currency-reviewer")
    await grant(c, h, base, reviewer)
    sources = {}
    for role, currency in [("books", "AED"), ("return", "AED"), ("foreign", "USD")]:
        value = await source(
            c,
            h,
            eid,
            [document(id=role, currency=currency, component="VAT")],
            "SYNTHETIC currency " + role,
            "tax-documents",
            {currency: "5"},
        )
        reviewed = await decision(c, reviewer[0], eid, value)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()
    data = {
        "workflow": "uae-vat",
        "source_ids": {role: sources[role]["id"] for role in ["books", "return"]},
        "as_of": "2026-06-30",
        "currency": "AED",
        "title": "SYNTHETIC AED VAT reporting comparison",
        "rationale": "Synthetic explicit reported currency, no FX conversion inferred",
    }
    result = await execute(c, h, eid, "country-workflow", data)
    assert result["body"]["rows"][0]["state"] == "MATCHED"
    assert result["body"]["vat_reporting_currency"] == "AED"
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    endpoint = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}"
    exported = await c.get(endpoint + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200
    book = load_workbook(io.BytesIO(exported.content), read_only=True)
    metadata = dict(book["Source and review"].values)
    assert metadata["vat_reporting_currency"] == "AED"
    assert metadata["vat_reporting_currency_contract"] == "uae-vat-aed-comparison/1"
    # The complete original result is also checked through the event endpoint.
    saved = await c.get(endpoint, headers=h)
    assert saved.json()["body"]["vat_reporting_currency_contract"] == "uae-vat-aed-comparison/1"
    rows = list(book["Rows"].values)
    assert len(rows) == 2
    exported_row = dict(zip(rows[0], rows[1], strict=True))
    assert exported_row["currency"] == "AED" and exported_row["state"] == "MATCHED"
    historical = deepcopy(saved.json()["body"])
    book.close()
    for role in ["books", "return"]:
        wrong = deepcopy(data)
        wrong["source_ids"][role] = sources["foreign"]["id"]
        failed = await execute(c, h, eid, "country-workflow", wrong, failed="AED reporting amounts")
        assert "AED reporting amounts" in str(failed)

    wrong = deepcopy(data)
    wrong["currency"] = "USD"
    await execute(c, h, eid, "country-workflow", wrong, failed="AED reporting amounts")
    retained = await c.get(endpoint, headers=h)
    assert retained.json()["freshness"] == "CURRENT" and retained.json()["body"] == historical

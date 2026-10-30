"""Declared count quantities survive review, draft generation and full XLSX export."""

import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.country_workflow_cases import stock

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned DB required")


@pytest.mark.parametrize("country,currency", [("AE", "AED"), ("IN", "INR")])
async def test_quantity_coverage_review_paper_and_export(
    environment, monkeypatch, country, currency
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "stock-coverage-reviewer")
    await grant(c, h, base, reviewer)
    sources = {}
    for role, quantity in (("books", "10"), ("count", "4")):
        imported = await source(
            c,
            h,
            eid,
            [stock(currency=currency, quantity=quantity)],
            "SYNTHETIC declared stock " + role,
            "stock",
            {},
        )
        reviewed = await decision(c, reviewer[0], eid, imported)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()["id"]
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "stock-audit",
            "source_ids": sources,
            "as_of": "2026-06-30",
            "title": "SYNTHETIC partial count evidence",
            "rationale": "Declared selected book and count populations only",
        },
    )
    assert result["body"]["rows"][0]["quantity_coverage_percent"] == "40.0"
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 409, reviewed.text
    documented = await decision(
        c, h, eid, result, "accept", item_id=result["body"]["rows"][0]["id"]
    )
    assert documented.status_code == 201, documented.text
    result = documented.json()
    assert result["body"]["rows"][0]["quantity_coverage_percent"] == "40.0"
    reviewed = await decision(c, reviewer[0], eid, result)
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content))
    rows = list(workbook["Rows"].values)
    assert str(rows[1][rows[0].index("quantity_coverage_percent")]) == "40.0"
    assert str(rows[1][rows[0].index("count_supported_quantity")]) == "4"
    paper = await c.post(
        path + "/working-paper",
        headers=h,
        json={
            "reference": "COUNT-COVERAGE-SYNTHETIC",
            "title": "Synthetic count coverage draft",
            "objective": "Assess selected aligned declared count support and remaining quantity gap",
        },
    )
    assert paper.status_code == 201, paper.text
    tables = paper.json()["body"]["financial_tables"]
    assert (
        tables[0]["values"]["quantity_coverage_basis"] == result["body"]["quantity_coverage_basis"]
    )
    assert tables[0]["values"]["coverage"] == result["body"]["coverage"]
    assert tables[1]["rows"][0]["quantity_coverage_percent"] == "40.0"

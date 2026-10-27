"""Reviewed country sources flow into complete, explicitly draft reporting packs."""

import hashlib
import io
import json
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.modules.intelligence import xlsx_values
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant, setup
from tests.qa_crud.test_country_workflows import csv_bytes, decision, double_boundaries
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_lossless_exports import retained_allocations
from tests.unit.test_xlsx_values import originals

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable DB required"
)


@pytest.mark.parametrize("country,category", [("AE", "uae-ifrs"), ("IN", "india-statutory")])
async def test_statutory_current_and_historical_complete_sources(
    environment, monkeypatch, country, category
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "complete-statutory-reviewer")
    await grant(c, h, base, reviewer)
    result, retained, values = await retained_allocations(c, h, eid, reviewer, country)
    prefix = f"/api/v1/regulatory/engagements/{eid}"
    data = {
        "title": "SYNTHETIC complete source reporting pack",
        "category": category,
        "rationale": "Synthetic source-bound reporting output, not legal form qualification",
        "blocks": [
            {
                "key": "cash",
                "title": "Reviewed settlement source",
                "kind": "financial_table",
                "source_kind": "intelligence",
                "source_id": result["id"],
                "text": "Synthetic assessed source scope; no signing or filing",
            }
        ],
    }
    wrong = await c.post(
        prefix + "/report-templates",
        headers=h,
        json={**data, "category": "india-statutory" if country == "AE" else "uae-ifrs"},
    )
    assert wrong.status_code == 422
    template = await c.post(prefix + "/report-templates", headers=h, json=data)
    assert template.status_code == 201, template.text
    assert (
        await c.post(
            prefix + "/reports",
            headers=h,
            json={
                "template_id": template.json()["id"],
                "rationale": "Synthetic unreviewed template must be rejected",
            },
        )
    ).status_code == 409
    reviewed = await decision(c, reviewer[0], eid, template.json())
    assert reviewed.status_code == 201, reviewed.text
    report = await c.post(
        prefix + "/reports",
        headers=h,
        json={
            "template_id": reviewed.json()["id"],
            "rationale": "Synthetic independently reviewed source and template used for draft composition",
        },
    )
    assert report.status_code == 201, report.text
    output = report.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{output['id']}/export?format=xlsx"

    async def check(freshness):
        response = await c.get(path, headers=h)
        assert response.status_code == 200, (
            response.text[:200] if response.status_code != 200 else ""
        )
        assert response.headers["x-export-sha256"] == hashlib.sha256(response.content).hexdigest()
        book = load_workbook(io.BytesIO(response.content), read_only=True)
        metadata = dict(book["Report and review"].values)
        assert metadata["Source freshness at export"] == freshness
        assert metadata["Status"] == "DRAFT — NOT SIGNED OR FILED"
        assert metadata["Country"] == country
        complete = originals(book)
        pieces = []
        for number, row in enumerate(list(book["Complete source chunks"].values)[1:], 2):
            pieces.append(complete.get(("Complete source chunks", f"C{number}"), row[2]))
        original = json.loads("".join(pieces))
        assert original == output["body"]["blocks"][0]["data"]
        from app.modules.jurisdictions.packages import fingerprint

        assert (
            fingerprint({"body": original, "dependencies": result["dependencies"]})
            == output["body"]["blocks"][0]["source_receipt"]["sha256"]
        )
        assert len(original["bank_consumption_manifest"]["rows"]) == 500
        assert any(sheet == "Table 1" for sheet, cell in complete)
        assert all(
            cell.data_type != "f"
            for sheet in book
            for row in sheet
            for cell in row
            if cell.value is not None
        )
        if freshness == "CURRENT":
            target = (
                Path(__file__).resolve().parents[3]
                / ".local-runtime/country-workflows"
                / f"{country.lower()}-statutory-complete.xlsx"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)

    await check("CURRENT")
    with monkeypatch.context() as limited:
        limited.setattr(xlsx_values, "MAX_LONG_BYTES", 10)
        failed = await c.get(path, headers=h)
        assert failed.status_code == 422 and "content-disposition" not in failed.headers
    receipt = next(
        item for item in retained["expected"]["dependencies"] if item["type"] == "evidence"
    )
    changed = await c.post(
        base + "/evidence-files/" + receipt["record_id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC changed report source.csv",
                csv_bytes([{**values["expected"][0], "amount": "501"}]),
                "text/csv",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    await check("STALE")
    assert (
        await c.post(
            prefix + "/reports",
            headers=h,
            json={
                "template_id": reviewed.json()["id"],
                "rationale": "Synthetic stale template cannot create a new report",
            },
        )
    ).status_code == 409

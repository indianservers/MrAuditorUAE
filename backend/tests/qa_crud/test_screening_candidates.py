"""Complete uploaded-list candidate retention; synthetic names, not sanctions clearance."""

import io
import json
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import setup
from tests.qa_crud.test_country_workflows import double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_diligence_audit_workflows import screening_sources
from tests.unit.test_xlsx_values import originals

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required")


async def prepare(c, h, eid):
    populations = screening_sources(name="SYNTHETIC شركة الاختبار भारत", list_name="SYNTHETIC شركة الاختبار भारत")
    populations["list"] = [{**populations["list"][0], "id": f"ENTRY-{index:04d}", "list_subject_id": f"PERSON-{index:04d}", "evidence_reference": f"SYNTHETIC-LIST-PAGE-{index:04d}"} for index in reversed(range(201))]
    selected = {}
    for role, table in (("subjects", "screening-subjects"), ("list", "sanctions-entries"), ("policy", "screening-policies")):
        imported = await source(c, h, eid, populations[role], "SYNTHETIC complete screening " + role, table, {})
        selected[role] = imported["id"]
    return {"engagement": eid, "sources": selected, "payload": {"workflow": "sanctions-name-review", "source_ids": selected,
        "as_of": "2026-06-30", "title": "SYNTHETIC complete uploaded-list screening", "rationale": "Fictional name-list coverage and independent candidate adjudication required"}}


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_all_candidates_survive_http_and_complete_export(environment, monkeypatch, country):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, _ = await setup(c)
    else:
        h, eid, _ = await india_context(c)
    fixture = await prepare(c, h, eid)
    result = await execute(c, h, eid, "country-workflow", fixture["payload"])
    row = result["body"]["rows"][0]
    assert row["candidate_count"] == len(row["candidates"]) == 201
    assert row["candidates"][-1]["source_id"] == "ENTRY-0200"
    assert row["reviewer_disposition"] == "UNREVIEWED" and row["state"] == "POTENTIAL_NAME_MATCH"
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    read = await c.get(prefix + "?limit=1", headers=h)
    assert read.status_code == 200 and len(read.json()["body"]["rows"][0]["candidates"]) == 201
    export = await c.get(prefix + "/export?format=xlsx", headers=h)
    assert export.status_code == 200, export.text
    book = load_workbook(io.BytesIO(export.content), read_only=True)
    values = list(book["Screening candidates"].values)
    records = [dict(zip(values[0], value, strict=True)) for value in values[1:]]
    assert len(records) == 201
    assert records[-1]["source_id"] == "ENTRY-0200" and records[-1]["evidence_reference"] == "SYNTHETIC-LIST-PAGE-0200"
    assert all(record["candidate_retention"] == "complete-screening-candidates/1" for record in records)
    # The nested original must also survive Excel's 32,767-character cell limit.
    reconstructed = originals(book)
    assert any(json.loads(value) == row["candidates"] for value in reconstructed.values() if value.startswith("[{"))
    book.close()

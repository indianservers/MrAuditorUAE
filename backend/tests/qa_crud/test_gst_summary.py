"""Retained original, independent review, country guards, export and staleness."""

import io
import json
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_gst_summary import CONTROLS, canonical_rows, options, parsed, summary

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def test_gstr1_summary_original_controls_review_export_and_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    record = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    content = json.dumps(summary()).encode()
    response = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-gstr1-summary.json", content, "application/json")},
    )
    assert response.status_code == 201, response.text
    original = response.json()
    payload = options(evidence_version_id=original["id"]).model_dump(mode="json")
    native = await execute(c, h, eid, "workflow-source", payload)
    assert native["body"]["native_metadata"]["filing_status"] == "NOT_ESTABLISHED_BY_SUMMARY"
    assert native["body"]["metric_controls"] == CONTROLS
    rows = canonical_rows()
    books = await source(
        c,
        h,
        eid,
        rows,
        "SYNTHETIC independent section controls",
        "gst-summary-metrics",
        {},
        gst_summary_metric_controls=CONTROLS,
    )
    args = {
        "workflow": "india-gstr1-summary",
        "source_ids": {"books": books["id"], "return": native["id"]},
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "SYNTHETIC outward summary reconciliation",
        "rationale": "Independent section and component evidence; overlapping parents not netted",
    }
    await execute(c, h, eid, "country-workflow", args, failed="Independently review")
    reviewer = await actor(h, "Firm Administrator", "summary-independent-reviewer")
    await grant(c, h, base, reviewer)
    for role, item in (("books", books), ("return", native)):
        approved = await decision(c, reviewer[0], eid, item)
        assert approved.status_code == 201, approved.text
        args["source_ids"][role] = approved.json()["id"]
    result = await execute(c, h, eid, "country-workflow", args)
    assert result["body"]["exception_count"] == 2
    assert result["body"]["totals"] == {}
    assert {r["difference"] for r in result["body"]["rows"] if r["state"] == "VARIANCE"} == {
        "1",
        "-1",
    }
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text[:100]
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    exported_rows = list(workbook["Rows"].values)
    metrics = [dict(zip(exported_rows[0], row, strict=True)) for row in exported_rows[1:]]
    assert len(metrics) == 23
    assert {row["difference"] for row in metrics if row["state"] == "VARIANCE"} == {"1", "-1"}
    assert all(row["unit"] == "COUNT" for row in metrics if row["metric"] == "ttl_rec")
    assert next(row for row in metrics if row["metric"] == "ttl_ngsup_amt")["return_value"] == "0"
    workbook.close()

    downloaded = await c.get(
        base + "/evidence-files/" + record["id"] + "/" + original["id"] + "/download", headers=h
    )
    assert downloaded.content == content
    changed = summary()
    changed["sec_sum"][0]["ttl_rec"] = 2
    replaced = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-gstr1-summary-replacement.json",
                json.dumps(changed).encode(),
                "application/json",
            )
        },
    )
    assert replaced.status_code == 201, replaced.text
    assert (await c.get(path, headers=h)).json()["freshness"] == "STALE"


async def test_gstr1_summary_contract_and_sources_unavailable_in_uae(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    config = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    ).json()
    assert "gst-summary-metrics" not in config["source_contracts"]
    assert not next(f for f in config["source_formats"] if f["id"] == "india-gstr1-summary-json")[
        "available"
    ]
    await source(
        c,
        h,
        eid,
        parsed()["rows"],
        "SYNTHETIC wrong country summary",
        "gst-summary-metrics",
        {},
        gst_summary_metric_controls=CONTROLS,
        failed="India engagement",
    )

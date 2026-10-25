"""Retained synthetic outward summary and independent flat book metrics."""

import json


async def prepare(client, headers, engagement, reviewer, retain):
    from tests.qa_crud.test_country_workflows import decision, source
    from tests.unit.test_gst_summary import CONTROLS, GSTIN, canonical_rows, summary

    original = await retain(engagement, "SYNTHETIC-gstr1-summary.json", json.dumps(summary()).encode(), "application/json")
    books = await source(client, headers, engagement, canonical_rows(), "SYNTHETIC independent outward summary books", "gst-summary-metrics", {}, gst_summary_metric_controls=CONTROLS)
    reviewed = await decision(client, reviewer[0], engagement, books)
    assert reviewed.status_code == 201, reviewed.text
    return {"books": reviewed.json()["id"], "original": original, "controls": CONTROLS, "gstin": GSTIN, "expected_rows": 23}

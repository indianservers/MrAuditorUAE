"""Exact saved fictional UAE CSV files through HTTP/storage/review/job/export.

Scanner and dispatch are explicit test doubles. No external access or payments.
"""

import hashlib
import io
import json
import os
import runpy
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned test DB required"
)
ROOT = Path(__file__).resolve().parents[3]
API = runpy.run_path(str(ROOT / "scripts/uae_synthetic_pilot.py"))


@pytest.mark.parametrize(
    "case_id,rows", [("SYN-UAE-001", 2), ("SYN-UAE-006", 3), ("SYN-UAE-012", 2)]
)
async def test_saved_pilot_sources_through_http_review_calculation_and_full_export(
    environment, monkeypatch, case_id, rows
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    reviewer = await actor(h, "Firm Administrator", "synthetic-uae-pilot-reviewer")
    await grant(c, h, base, reviewer)
    path = API["retained"](ROOT, API["relative"]("redacted-inputs", "batch/manifest.json"))
    manifest = json.loads(path.read_bytes())
    assert manifest["dataset_kind"] == API["KIND"] and manifest["real_client_data"] is False
    case = next(item for item in manifest["cases"] if item["id"] == case_id)
    sources = {}
    for role, record in case["source_files"].items():
        raw = API["read_bound"](ROOT, record)
        evidence = await create(
            c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        uploaded = await c.post(
            base + "/evidence-files/" + evidence["id"],
            headers=h,
            files={"file": (f"SYNTHETIC-{case_id}-{role}.csv", raw, "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["sha256"] == hashlib.sha256(raw).hexdigest()
        prepared = await execute(
            c,
            h,
            eid,
            "workflow-source",
            {
                "evidence_version_id": uploaded.json()["id"],
                "label": f"SYNTHETIC {case_id} {role}",
                **record["controls"],
            },
        )
        reviewed = await decision(c, reviewer[0], eid, prepared)
        assert reviewed.status_code == 201, reviewed.text
        sources[role] = reviewed.json()["id"]
    output = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": case["workflow"],
            "title": case["title"],
            "as_of": case["as_of"],
            "source_ids": sources,
            "rationale": "SYNTHETIC saved UAE pilot; assessed input controls and authored expected figures",
            **case["parameters"],
        },
    )
    expected = json.loads(API["read_bound"](ROOT, case["expected_file"]))["expected"]
    assert API["compare"](output["body"], expected) == []
    assert len(output["body"]["rows"]) == rows
    if case["workflow"] == "stock-audit":
        seal = next(r for r in output["body"]["rows"] if r["sku"] == "SYN-SEAL")
        assert seal["count_condition"] == "damaged"
        assert (
            seal["state"] == "CONDITION_EXCEPTION" and seal["potential_nrv_writedown"] == "1800.00"
        )
    export = await c.get(
        f"/api/v1/intelligence/engagements/{eid}/events/{output['id']}/export?format=xlsx",
        headers=h,
    )
    assert export.status_code == 200, export.text
    workbook = load_workbook(io.BytesIO(export.content), read_only=True)
    values = list(workbook["Rows"].values)
    assert len(values) == rows + 1
    if case["workflow"] == "stock-audit":
        records = [dict(zip(values[0], row, strict=True)) for row in values[1:]]
        damaged = next(r for r in records if r["sku"] == "SYN-SEAL")
        assert (
            damaged["count_condition"] == "damaged"
            and damaged["potential_nrv_writedown"] == "1800.00"
        )

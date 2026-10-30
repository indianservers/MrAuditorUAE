"""Complete annual source, independent review/export and crosswalk freshness boundaries."""

import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute
from tests.qa_crud.test_india_ecr_source import india_context
from tests.qa_crud.test_india_withholding_native import upload
from tests.unit.test_india_salary_annual import options_q4, q4_fixture
from tests.unit.test_india_withholding_native import ROOT

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


@pytest.mark.parametrize(
    "scenario", ["original_sample", "self_crosswalk", "cloned_crosswalk", "quarantined_crosswalk"]
)
async def test_annual_source_requires_full_layout_and_separate_clean_crosswalk(
    environment, monkeypatch, scenario
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    raw, n, a = q4_fixture()
    content = (
        (ROOT / "protean-24Q-Q4-original-sample.txt").read_bytes()
        if scenario == "original_sample"
        else raw
    )
    _, file = await upload(c, h, base, "SYNTHETIC-or-unchanged-original-q4.txt", content)
    document = file
    if scenario != "self_crosswalk":
        if scenario == "quarantined_crosswalk":
            double_boundaries(monkeypatch, scan="QUARANTINED")
        _, document = await upload(
            c,
            h,
            base,
            "SYNTHETIC-annual-crosswalk.txt",
            content
            if scenario == "cloned_crosswalk"
            else b"SYNTHETIC independent quarterly and annual source control assessment",
        )
    n["crosswalk_document_version_id"] = document["id"]
    payload = options_q4(n, a, evidence_version_id=file["id"]).model_dump(mode="json")
    result = await execute(
        c,
        h,
        eid,
        "workflow-source",
        payload,
        failed="field count"
        if scenario == "original_sample"
        else "quarantined"
        if scenario == "quarantined_crosswalk"
        else "separate independent",
    )
    assert result["result_id"] is None


async def test_reviewed_q4_exports_every_annual_field_and_becomes_stale_with_crosswalk_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "annual-salary-reviewer")
    await grant(c, h, base, reviewer)
    raw, n, a = q4_fixture()
    _, file = await upload(c, h, base, "SYNTHETIC-complete-q4.txt", raw)
    crosswalk, document = await upload(
        c,
        h,
        base,
        "SYNTHETIC-annual-crosswalk.txt",
        b"SYNTHETIC independent full quarterly and six-type annual population and signed amount assessment",
    )
    n["crosswalk_document_version_id"] = document["id"]
    payload = options_q4(n, a, evidence_version_id=file["id"]).model_dump(mode="json")
    source = await execute(c, h, eid, "workflow-source", payload)
    annual = source["body"]["native_metadata"]["salary_annual"]
    assert len(annual["records"]) == 6 and source["body"]["row_count"] == 1
    assert annual["totals"]["salary_shortfall"] == "-1600.00"
    assert source["body"]["native_metadata"]["crosswalk_document_sha256"] == document["sha256"]
    assert (await decision(c, h, eid, source)).status_code == 403
    response = await decision(c, reviewer[0], eid, source)
    assert response.status_code == 201, response.text
    reviewed = response.json()
    path = f"/api/v1/intelligence/engagements/{eid}/events/{reviewed['id']}"
    exported = await c.get(path + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content), read_only=True)
    for tag, width in [("SD", 88), ("S16", 8), ("C6A", 10), ("94P", 28), ("P16", 8), ("P6A", 10)]:
        rows = list(workbook["Salary " + tag].values)
        assert len(rows) == 2 and len(rows[0]) == width + 5
        original = next(r for r in annual["records"] if r["record_type"] == tag)
        assert list(rows[1][5:]) == [v if v != "" else None for v in original["fields"]]
    assert list(workbook["Salary SD"].values)[1][5 + 17] == "-1000.00"
    assert list(workbook["Salary P6A"].values)[1][5 + 6] == "700.00"
    assert list(workbook["Salary P6A"].values)[1][5 + 8] == "500.00"
    controls = list(workbook["Salary annual controls"].values)
    assert next(row for row in controls if row[0] == "salary_shortfall")[1:] == (
        "-1600.00",
        "-1600",
    )
    workbook.close()
    replacement = await c.post(
        base + "/evidence-files/" + crosswalk["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-new-annual-controls.txt",
                b"SYNTHETIC revised annual controls require independent reassessment",
                "text/plain",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    saved = (await c.get(path, headers=h)).json()
    assert (
        saved["freshness"] == "STALE"
        and saved["body"] == reviewed["body"]
        and saved["version"] == reviewed["version"]
    )
    await execute(c, h, eid, "workflow-source", payload, failed="superseded")

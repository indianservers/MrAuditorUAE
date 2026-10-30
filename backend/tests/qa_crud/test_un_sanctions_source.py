"""Real uploaded evidence/jobs/review/export; scanner and broker are explicit doubles."""

import io
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_un_sanctions_source import XML, controls

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable DB required"
)


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_native_un_source_review_screening_export_and_withdrawal(
    environment, monkeypatch, country
):
    c = environment
    double_boundaries(monkeypatch)
    if country == "AE":
        h, _, eid, base = await setup(c)
    else:
        h, eid, base = await india_context(c)
    reviewer = await actor(h, "Firm Administrator", "un-source-reviewer-" + country)
    await grant(c, h, base, reviewer)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("synthetic-un.xml", XML, "application/xml")},
    )
    assert upload.status_code == 201, upload.text
    native = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": upload.json()["id"],
            "file_format": "un-sc-consolidated-xml",
            "table_type": "sanctions-entries",
            "label": "SYNTHETIC controlled UN XML",
            "expected_rows": 6,
            "un_sanctions_controls": controls(),
        },
    )
    assert native["body"]["row_count"] == 6
    assert native["body"]["native_metadata"]["identity_or_legal_clearance"] == "NOT_DETERMINED"
    assert (await decision(c, h, eid, native)).status_code == 403
    response = await decision(c, reviewer[0], eid, native)
    assert response.status_code == 201, response.text
    native = response.json()
    subjects = await source(
        c,
        h,
        eid,
        [{"id": "S1", "name": "Example Alias", "evidence_reference": "SYNTHETIC-ID"}],
        "SYNTHETIC screening subject",
        "screening-subjects",
        {},
    )
    policy = await source(
        c,
        h,
        eid,
        [
            {
                "id": "P1",
                "minimum_similarity": "1",
                "maximum_list_age_days": 7,
                "list_version": native["body"]["native_metadata"]["list_version"],
                "evidence_reference": "SYNTHETIC-POLICY",
            }
        ],
        "SYNTHETIC screening policy",
        "screening-policies",
        {},
    )
    selected = {"list": native["id"]}
    for role, obj in (("subjects", subjects), ("policy", policy)):
        reviewed = await decision(c, reviewer[0], eid, obj)
        assert reviewed.status_code == 201, reviewed.text
        selected[role] = reviewed.json()["id"]
    result = await execute(
        c,
        h,
        eid,
        "country-workflow",
        {
            "workflow": "sanctions-name-review",
            "source_ids": selected,
            "as_of": "2026-06-30",
            "title": "SYNTHETIC native UN name screening",
            "rationale": "Independent alias population with human adjudication required",
        },
    )
    row = result["body"]["rows"][0]
    assert row["state"] == "POTENTIAL_NAME_MATCH" and row["candidate_count"] == 2
    assert {v["native_alias_quality"] for v in row["candidates"]} == {"Good", "Low"}
    prefix = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    exported = await c.get(prefix + "/export?format=xlsx", headers=h)
    assert exported.status_code == 200, exported.text
    book = load_workbook(io.BytesIO(exported.content), read_only=True)
    values = list(book["Screening candidates"].values)
    records = [dict(zip(values[0], value, strict=True)) for value in values[1:]]
    assert {r["native_alias_quality"] for r in records} == {"Good", "Low"}
    assert all(r["native_reference_number"] == "ZZi.001" for r in records)
    book.close()
    original = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + upload.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == XML
    withdrawn = await decision(c, reviewer[0], eid, native, action="reject")
    assert withdrawn.status_code == 201, withdrawn.text
    stale = (await c.get(prefix, headers=h)).json()
    assert stale["freshness"] == "STALE"
    assert stale["body"] == result["body"] and stale["version"] == result["version"]

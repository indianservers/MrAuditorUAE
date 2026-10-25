"""Real retained originals/context, independent review and outward reconciliation."""

import io
import json
import os

import pytest
from openpyxl import load_workbook

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant, setup
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute, source
from tests.qa_crud.test_india_ecr_source import india_context
from tests.unit.test_india_gstr1_source import GSTIN, all_sections, books, controls, options

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Owned disposable database required"
)


async def retained(client, headers, eid, base, all=False):
    originals = []
    data = all_sections() if all else {"b2b": all_sections()["b2b"]}
    context = {
        "classification": "SYNTHETIC_ASSESSED_REQUEST_CONTEXT_NOT_GSTN_AUTHENTICATION",
        "gstin": GSTIN,
        "period": "2026-06",
        "sections": list(data),
        "scope": "Independently assessed retained section responses, filters and pagination; no filing or full-return completeness proof",
    }
    for name, value in (("response", data), ("context", context)):
        record = await create(
            client, headers, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
        )
        content = json.dumps(value).encode()
        response = await client.post(
            base + "/evidence-files/" + record["id"],
            headers=headers,
            files={"file": ("SYNTHETIC-gstr1-" + name + ".json", content, "application/json")},
        )
        assert response.status_code == 201, response.text
        originals.append((record, response.json(), content))
    args = options(
        all,
        evidence_version_id=originals[0][1]["id"],
        gstr1_context_evidence_version_id=originals[1][1]["id"],
    ).model_dump(mode="json")
    return args, originals


async def test_outward_originals_context_independent_review_export_and_context_replacement(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    payload, originals = await retained(c, h, eid, base)
    native = await execute(c, h, eid, "workflow-source", payload)
    assert native["body"]["row_count"] == 4
    assert native["body"]["native_metadata"]["context_sha256"] == originals[1][1]["sha256"]
    book = await source(
        c,
        h,
        eid,
        books()["rows"],
        "SYNTHETIC independent outward sales register",
        "tax-documents",
        {"INR": "18"},
    )
    args = {
        "workflow": "india-gstr1-documents",
        "source_ids": {"books": book["id"], "return": native["id"]},
        "as_of": "2026-06-30",
        "currency": "INR",
        "title": "SYNTHETIC outward document comparison",
        "rationale": "Independent source register and assessed original request context",
    }
    await execute(c, h, eid, "country-workflow", args, failed="Independently review")
    reviewer = await actor(h, "Firm Administrator", "outward-independent-reviewer")
    await grant(c, h, base, reviewer)
    for role, obj in (("books", book), ("return", native)):
        approved = await decision(c, reviewer[0], eid, obj)
        assert approved.status_code == 201, approved.text
        args["source_ids"][role] = approved.json()["id"]
    result = await execute(c, h, eid, "country-workflow", args)
    assert result["body"]["exception_count"] == 0
    assert result["body"]["outward_gst_scope"]["declared_section_controls"] == controls()
    assert (
        result["body"]["outward_gst_scope"]["filing_status"]
        == "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON"
    )
    path = f"/api/v1/intelligence/engagements/{eid}/events/{result['id']}"
    response = await c.get(path + "/export?format=xlsx", headers=h)
    assert response.status_code == 200, response.text[:100]
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    values = list(workbook["Rows"].values)
    records = [dict(zip(values[0], r, strict=True)) for r in values[1:]]
    assert len(records) == 4 and {r["return_tax"] for r in records} == {"0", "18"}
    assert any(row[0] == "outward_gst_scope" for row in workbook["Source and review"].values)
    workbook.close()
    for record, original, content in originals:
        downloaded = await c.get(
            base + "/evidence-files/" + record["id"] + "/" + original["id"] + "/download", headers=h
        )
        assert downloaded.content == content
    record, _, _ = originals[1]
    replacement = await c.post(
        base + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-gstr1-context-replacement.json",
                b'{"classification":"SYNTHETIC changed request scope"}',
                "application/json",
            )
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert (await c.get(path, headers=h)).json()["freshness"] == "STALE"


async def test_all_invoice_note_sections_preserve_sources_and_remain_unresolved_when_amended(
    environment, monkeypatch
):
    c = environment
    double_boundaries(monkeypatch)
    h, eid, base = await india_context(c)
    payload, _ = await retained(c, h, eid, base, True)
    native = await execute(c, h, eid, "workflow-source", payload)
    assert native["body"]["row_count"] == 40
    assert native["body"]["control_totals"] == {"INR": "97.2"}
    assert len(native["body"]["native_metadata"]["original_rate_records"]) == 10
    assert {row["source_section"] for row in native["body"]["rows"]} == set(all_sections())
    assert (
        next(
            r
            for r in native["body"]["rows"]
            if r["source_section"] == "cdnr" and r["component"] == "IGST"
        )["tax"]
        == "-9"
    )


async def test_outward_reader_is_country_scoped(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    payload, _ = await retained(c, h, eid, base)
    await execute(c, h, eid, "workflow-source", payload, failed="India engagement")

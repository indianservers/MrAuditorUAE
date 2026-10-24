"""Native uploads use real evidence storage/HTTP/jobs; the scanner/broker are explicit test doubles."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import create, setup
from tests.qa_crud.test_country_workflows import double_boundaries, execute
from tests.unit.native_source_examples import CAMT, MT940, SIF, SIF_FILENAME

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Dedicated disposable migrated DB required"
)


@pytest.mark.parametrize(
    "fmt,content,name,media,table,total",
    [
        ("camt053", CAMT, "synthetic-native.xml", "application/xml", "transactions", "95"),
        ("swift-mt940", MT940, "synthetic-native.mt940", "text/plain", "transactions", "95"),
        ("uae-wps-sif", SIF, SIF_FILENAME, "text/csv", "obligations", "1500"),
    ],
    ids=["camt053", "mt940", "wps-sif"],
)
async def test_native_upload_job_retains_original_and_embedded_controls(
    environment, monkeypatch, fmt, content, name, media, table, total
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, base = await setup(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": (name, content, media)},
    )
    assert upload.status_code == 201, upload.text
    result = await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": upload.json()["id"],
            "file_format": fmt,
            "table_type": table,
            "label": "SYNTHETIC native source",
            "expected_rows": 2,
            "control_totals": {"AED": total},
        },
    )
    assert result["kind"] == "workflow-source"
    assert result["body"]["native_controls_verified"] is True
    assert result["body"]["review_status"] == "UNVERIFIED"
    assert any(
        dep["type"] == "evidence" and dep["sha256"] == upload.json()["sha256"]
        for dep in result["dependencies"]
    )
    assert result["body"]["source_identity"] == "evidence:" + upload.json()["id"]
    if fmt == "uae-wps-sif":
        assert all(r["payment_date"] is None for r in result["body"]["rows"])
    original = await c.get(
        base + "/evidence-files/" + evidence["id"] + "/" + upload.json()["id"] + "/download",
        headers=h,
    )
    assert original.status_code == 200 and original.content == content
    formats = (
        await c.get(f"/api/v1/intelligence/engagements/{eid}/country-workflows", headers=h)
    ).json()["source_formats"]
    assert next(f for f in formats if f["id"] == fmt)["available"]


async def test_native_quarantine_and_hostile_xml_cannot_be_used(environment, monkeypatch):
    c = environment
    double_boundaries(monkeypatch, scan="QUARANTINED")
    h, _, eid, base = await setup(c)
    evidence = await create(
        c, h, base, "evidence", {"category": "Other", "retain_until": "2036-12-31"}
    )
    upload = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("native.xml", CAMT, "application/xml")},
    )
    assert upload.status_code == 201 and upload.json()["scan_status"] == "QUARANTINED"
    await execute(
        c,
        h,
        eid,
        "workflow-source",
        {
            "evidence_version_id": upload.json()["id"],
            "file_format": "camt053",
            "table_type": "transactions",
            "label": "SYNTHETIC quarantined native source",
            "expected_rows": 2,
            "control_totals": {"AED": "95"},
        },
        failed="quarantined",
    )
    hostile = (
        b'<!DOCTYPE Document [<!ENTITY x SYSTEM "file:///never-read">]><Document>&x;</Document>'
    )
    rejected = await c.post(
        base + "/evidence-files/" + evidence["id"],
        headers=h,
        files={"file": ("unsafe.xml", hostile, "application/xml")},
    )
    assert rejected.status_code == 422

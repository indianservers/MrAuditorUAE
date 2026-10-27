"""Actual local PDF/image/ZIP extraction; evidence scanner and broker are doubles."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create, grant
from tests.qa_crud.test_country_workflows import decision, double_boundaries, execute
from tests.qa_crud.test_generic_candidates import context

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned database")
FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "docs/country-workflows/sample-inputs/SYNTHETIC-document-worker"
)
MEDIA = {
    "digital.pdf": "application/pdf",
    "scan.png": "image/png",
    "documents.zip": "application/zip",
}


async def prepare(c, h, eid, audit, country, filename):
    original = FIXTURES / country / filename
    content = original.read_bytes()
    expected = json.loads((original.parent / "expected.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(content).hexdigest() == expected["sha256"][filename]
    record = await create(
        c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
    )
    uploaded = await c.post(
        audit + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": (f"SYNTHETIC-{country}-{filename}", content, MEDIA[filename])},
    )
    assert uploaded.status_code == 201, uploaded.text
    return dict(evidence_version_id=uploaded.json()["id"]), expected, record


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("kind", ["digital", "scan", "zip-selected", "zip-batch"])
async def test_actual_document_worker_hashes_fields_pages_review_and_source_replacement(
    environment, monkeypatch, country, kind
):
    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await context(c, country)
    filename = (
        "digital.pdf" if kind == "digital" else "scan.png" if kind == "scan" else "documents.zip"
    )
    payload, expected, record = await prepare(c, h, eid, audit, country, filename)
    if kind == "zip-selected":
        payload["zip_member"] = "invoice.pdf"
    obj = await execute(c, h, eid, "ocr", payload)
    body = obj["body"]
    assert body["local_worker_contract"] == "bounded-document-subprocess/1"
    assert body["original_sha256"] == expected["sha256"][filename]
    assert body["human_review_required"] and not body["network_document_transfer"]
    assert body["review_status"] == "UNVERIFIED"
    if kind == "zip-batch":
        assert all(value is None for value in body["fields"].values())
        assert {doc["fields"]["invoice_number"] for doc in body["documents"]} == set(
            expected["batch_invoice_numbers"]
        )
        assert len(body["pages"]) == 2
    else:
        for field, value in expected["fields"].items():
            assert body["fields"][field] == value
        assert len(body["pages"]) == 1
        assert body["pages"][0]["provider"] == (
            "rapidocr-local" if kind == "scan" else "pdfium-text"
        )
        if kind == "scan":
            assert body["pages"][0]["blocks"][0]["bbox"]
        if kind == "zip-selected":
            assert body["pages"][0]["source_file"] == "invoice.pdf"
    assert (await decision(c, h, eid, obj)).status_code == 403
    reviewer = await actor(h, "Firm Administrator", f"document-reviewer-{country}-{kind}")
    await grant(c, h, audit, reviewer)
    reviewed = await decision(c, reviewer[0], eid, obj)
    assert reviewed.status_code == 201, reviewed.text
    changed = await c.post(
        audit + "/evidence-files/" + record["id"],
        headers=h,
        files={
            "file": (
                "SYNTHETIC-replacement.txt",
                b"Synthetic replacement requires fresh extraction",
                "text/plain",
            )
        },
    )
    assert changed.status_code == 201, changed.text
    historical = (
        await c.get(
            f"/api/v1/intelligence/engagements/{eid}/events/{reviewed.json()['id']}", headers=h
        )
    ).json()
    assert historical["freshness"] == "STALE" and historical["body"]["review_status"] == "REVIEWED"
    assert historical["body"]["original_sha256"] == expected["sha256"][filename]


@pytest.mark.parametrize("failure", ["crash", "input-changed", "version-hash-mismatch"])
async def test_failed_native_worker_never_publishes_a_partial_extraction(
    environment, monkeypatch, failure
):
    from app.modules.intelligence import extraction_runtime

    c = environment
    double_boundaries(monkeypatch)
    h, _, eid, audit = await context(c, "AE")
    payload, _, _ = await prepare(c, h, eid, audit, "AE", "digital.pdf")
    if failure == "crash":
        monkeypatch.setattr(
            extraction_runtime,
            "run_worker",
            lambda *args, **kwargs: SimpleNamespace(returncode=17),
        )
        message = "exit code 17"
    elif failure == "input-changed":
        monkeypatch.setattr(extraction_runtime, "input_hash", lambda *args: "0" * 64)
        message = "Original extraction document changed"
    else:
        monkeypatch.setattr(
            "app.modules.intelligence.documents.extract_document",
            lambda *args, **kwargs: {"original_sha256": "0" * 64},
        )
        message = "differs from the retained evidence version"
    await execute(c, h, eid, "ocr", payload, failed=message)

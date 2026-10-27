"""Real upload/storage/download boundaries with explicit synthetic socket verdicts."""

import os

import pytest

from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import create
from tests.qa_crud.test_generic_candidates import context
from tests.unit.test_evidence_scanner_protocol import connection

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned database")


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("verdict", ["clean-fragments", "unterminated", "found"])
async def test_upload_consumption_requires_complete_clean_verdict(
    environment, monkeypatch, country, verdict
):
    c = environment
    h, _, _, audit = await context(c, country)
    record = await create(
        c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
    )
    replies = {
        "clean-fragments": [b"stream: ", b"OK", b"\0"],
        "unterminated": [b"stream: OK", b""],
        "found": [b"stream: Synthetic-Signature FOUND\0"],
    }
    connection(monkeypatch, replies[verdict])
    content = f"SYNTHETIC {country} scanner transport test".encode()
    response = await c.post(
        audit + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-scanner.txt", content, "text/plain")},
    )
    versions = await c.get(audit + "/evidence-files/" + record["id"], headers=h)
    assert versions.status_code == 200, versions.text
    if verdict == "found":
        assert response.status_code == 422, response.text
        assert versions.json()["items"] == []
        return
    assert response.status_code == 201, response.text
    expected = "CLEAN" if verdict == "clean-fragments" else "QUARANTINED"
    assert response.json()["scan_status"] == expected
    assert len(versions.json()["items"]) == 1
    downloaded = await c.get(
        audit + f"/evidence-files/{record['id']}/{response.json()['id']}/download",
        headers=h,
    )
    if verdict == "clean-fragments":
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == content
    else:
        assert downloaded.status_code == 409, downloaded.text

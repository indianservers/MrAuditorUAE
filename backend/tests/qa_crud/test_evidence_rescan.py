"""Immutable retained-original rescan with explicit synthetic scanner transport."""

import os
import uuid

import pytest

from app.db.session import Session, tenant_context
from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
from app.modules.lineage.storage import ObjectStore
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import actor, create
from tests.qa_crud.test_generic_candidates import context
from tests.unit.test_evidence_scanner_protocol import connection

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Owned database")


async def quarantined(c, monkeypatch, country):
    h, _, eid, audit = await context(c, country)
    record = await create(
        c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
    )
    connection(monkeypatch, [b"stream: OK", b""])
    content = f"SYNTHETIC {country} retained rescan original".encode()
    uploaded = await c.post(
        audit + "/evidence-files/" + record["id"],
        headers=h,
        files={"file": ("SYNTHETIC-rescan.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["scan_status"] == "QUARANTINED"
    return h, eid, audit, record, uploaded.json(), content


@pytest.mark.parametrize("country", ["AE", "IN"])
@pytest.mark.parametrize("verdict", ["CLEAN", "QUARANTINED", "REJECTED"])
async def test_rescan_appends_version_and_preserves_original(
    environment, monkeypatch, country, verdict
):
    c = environment
    h, _, audit, record, old, content = await quarantined(c, monkeypatch, country)
    replies = {
        "CLEAN": [b"stream: ", b"OK\0"],
        "QUARANTINED": [b""],
        "REJECTED": [b"stream: Synthetic-Signature FOUND\0"],
    }
    connection(monkeypatch, replies[verdict])
    path = audit + f"/evidence-files/{record['id']}"
    response = await c.post(path + f"/{old['id']}/rescan", headers=h)
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["number"] == 2 and new["scan_status"] == verdict
    assert new["sha256"] == old["sha256"] and new["size"] == old["size"]
    assert new["object_key"] == old["object_key"] and new["object_version"] == old["object_version"]
    versions = (await c.get(path, headers=h)).json()["items"]
    assert len(versions) == 2 and versions[1]["scan_status"] == "QUARANTINED"
    assert (await c.post(path + f"/{old['id']}/rescan", headers=h)).status_code == 409
    assert (await c.get(path + f"/{old['id']}/download", headers=h)).status_code == 409
    download = await c.get(path + f"/{new['id']}/download", headers=h)
    assert download.status_code == (200 if verdict == "CLEAN" else 409)
    if verdict == "CLEAN":
        assert download.content == content
    if verdict != "QUARANTINED":
        assert (await c.post(path + f"/{new['id']}/rescan", headers=h)).status_code == 409


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_changed_original_refused_before_scanning(environment, monkeypatch, country):
    c = environment
    h, _, audit, record, old, _ = await quarantined(c, monkeypatch, country)
    async with Session() as db:
        await tenant_context(db, h["X-Tenant-ID"])
        version = await db.get(EvidenceVersion, uuid.UUID(old["id"]))
        with ObjectStore().local(version.object_key, version.object_version) as path:
            path.write_bytes(b"SYNTHETIC changed retained original")
    client, _ = connection(monkeypatch, [b"stream: OK\0"])
    path = audit + f"/evidence-files/{record['id']}"
    response = await c.post(path + f"/{old['id']}/rescan", headers=h)
    assert response.status_code == 409, response.text
    assert "integrity" in response.text
    client.sendall.assert_not_called()
    assert len((await c.get(path, headers=h)).json()["items"]) == 1


@pytest.mark.parametrize("country", ["AE", "IN"])
async def test_unassigned_actor_cannot_rescan(environment, monkeypatch, country):
    c = environment
    h, _, audit, record, old, _ = await quarantined(c, monkeypatch, country)
    outsider = await actor(h, "Audit Partner", f"unassigned-rescan-{country}")
    client, _ = connection(monkeypatch, [b"stream: OK\0"])
    response = await c.post(
        audit + f"/evidence-files/{record['id']}/{old['id']}/rescan", headers=outsider[0]
    )
    assert response.status_code == 403, response.text
    client.sendall.assert_not_called()


@pytest.mark.parametrize("status", ["APPROVED", "LOCKED", "REVIEW_REQUIRED"])
async def test_protected_record_cannot_rescan(environment, monkeypatch, status):
    c = environment
    h, _, audit, record, old, _ = await quarantined(c, monkeypatch, "AE")
    async with Session() as db:
        await tenant_context(db, h["X-Tenant-ID"])
        obj = await db.get(AuditRecord, uuid.UUID(record["id"]))
        obj.status = status
        await db.commit()
    client, _ = connection(monkeypatch, [b"stream: OK\0"])
    response = await c.post(audit + f"/evidence-files/{record['id']}/{old['id']}/rescan", headers=h)
    assert response.status_code == 409, response.text
    client.sendall.assert_not_called()

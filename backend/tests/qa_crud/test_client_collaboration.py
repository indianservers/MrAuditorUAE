"""Anonymous capability boundaries and fail-closed evidence collection on synthetic requests."""

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models.platform import Membership
from app.db.session import Session, tenant_context
from app.modules.collaboration.models import SharedLink
from tests.integration.test_platform import environment as environment
from tests.phase4.test_workflows import create, setup

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database"
)


async def prepare(c):
    h, options, eid, base = await setup(c)
    request = await create(
        c,
        h,
        base,
        "requests",
        {
            "client_id": options["client_id"],
            "question": "SYNTHETIC provide the specific support requested",
        },
    )
    prefix = f"/api/v1/collaboration/engagements/{eid}"
    blocked = await c.post(
        prefix + "/links",
        headers=h,
        json={"request_id": request["id"], "retain_until": "2032-01-01"},
    )
    assert blocked.status_code == 403
    enabled = await c.post(
        base + "/policy",
        headers=h,
        json={
            "review_chain": ["Audit Manager", "Audit Partner"],
            "methodology": {"allow_account_free_portal": True},
        },
    )
    assert enabled.status_code == 200, enabled.text
    return h, eid, base, request, prefix


async def issue(c, h, prefix, rid, **limits):
    response = await c.post(
        prefix + "/links",
        headers=h,
        json={"request_id": rid, "retain_until": "2032-01-01", **limits},
    )
    assert response.status_code == 201
    value = response.json()
    secret = value["share_path"].split("#")[1]
    public = f"/api/v1/collaboration/public/{h['X-Tenant-ID']}/{value['id']}"
    return value["id"], public, {"X-Collaboration-Token": secret}


async def test_scoped_guest_upload_review_and_revocation(environment):
    c = environment
    h, eid, base, original, prefix = await prepare(c)
    lid, public, token = await issue(c, h, prefix, original["id"])
    assert (await c.get(public)).status_code == 404
    assert (await c.get(public, headers={"X-Collaboration-Token": "f" * 64})).status_code == 404
    assert (
        await c.get(public.replace(h["X-Tenant-ID"], str(uuid.uuid4())), headers=token)
    ).status_code == 404
    question = await c.get(public, headers=token)
    assert question.status_code == 200
    assert set(question.json()) == {
        "title",
        "question",
        "due_date",
        "expires_at",
        "max_file_bytes",
        "uploads_remaining",
        "identity_status",
    }
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        link = await db.get(SharedLink, uuid.UUID(lid))
        assert (
            link.token_hash == hashlib.sha256(token["X-Collaboration-Token"].encode()).hexdigest()
        )
        assert link.token_hash != token["X-Collaboration-Token"]
    # No malware service is configured. The real default must quarantine, never mark clean.
    uploaded = await c.post(
        public,
        headers=token,
        data={
            "response": "SYNTHETIC support provided for review",
            "claimed_name": "Unverified client fixture",
        },
        files={"file": ("synthetic.csv", b"reference,amount\nTEST,100\n", "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert (
        uploaded.json()["scan_status"] == "QUARANTINED" and not uploaded.json()["identity_verified"]
    )
    rows = (await c.get(prefix + f"/links/{lid}/submissions", headers=h)).json()["items"]
    body = rows[0]["body"]
    download = base + f"/evidence-files/{body['evidence_id']}/{body['file_version_id']}/download"
    assert (await c.get(download, headers=token)).status_code == 401
    assert (await c.get(download, headers=h)).status_code == 409
    accepted = await c.post(
        prefix + f"/links/{lid}/submissions/{uploaded.json()['id']}/accept",
        headers=h,
        json={
            "expected_request_version": original["version"],
            "comments": "Synthetic staff reviewed the communication, not the quarantined document",
        },
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["automatically_approved"] is False
    assert (
        await c.get(public, headers=token)
    ).status_code == 404  # request revision invalidates its former capability
    current = (await c.get(base + f"/records/{original['id']}", headers=h)).json()
    assert "identity unverified" in current["body"]["response"]
    assert current["status"] not in {"APPROVED", "LOCKED"}
    new_id, new_public, new_token = await issue(c, h, prefix, original["id"])
    assert (await c.get(new_public, headers=new_token)).status_code == 200
    assert (await c.post(prefix + f"/links/{new_id}/revoke", headers=h)).status_code == 200
    assert (await c.get(new_public, headers=new_token)).status_code == 404
    listing = (await c.get(prefix + "/links", headers=h)).json()
    assert all("token_hash" not in row for row in listing["items"])
    graph = await c.get(base + "/graph", headers=h)
    assert graph.status_code == 200, graph.text


async def test_expiry_issuer_revocation_and_upload_bounds(environment):
    c = environment
    h, _, _, original, prefix = await prepare(c)
    lid, public, token = await issue(c, h, prefix, original["id"], max_file_bytes=1)
    oversized = await c.post(
        public,
        headers=token,
        data={"response": "Synthetic oversized fixture"},
        files={"file": ("large.csv", b"12345", "text/csv")},
    )
    assert oversized.status_code == 413
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        link = await db.get(SharedLink, uuid.UUID(lid))
        link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await c.get(public, headers=token)).status_code == 404
    _, fresh, secret = await issue(c, h, prefix, original["id"])
    async with Session() as db, db.begin():
        await tenant_context(db, h["X-Tenant-ID"])
        link = (
            await db.scalars(
                select(SharedLink)
                .where(SharedLink.tenant_id == uuid.UUID(h["X-Tenant-ID"]))
                .order_by(SharedLink.created_at.desc())
            )
        ).first()
        membership = await db.scalar(
            select(Membership).where(
                Membership.tenant_id == uuid.UUID(h["X-Tenant-ID"]),
                Membership.user_id == link.created_by,
            )
        )
        membership.status = "inactive"
    assert (await c.get(fresh, headers=secret)).status_code == 404

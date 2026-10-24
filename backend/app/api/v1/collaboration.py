import hashlib
import hmac
import secrets
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.db.session import tenant_context
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.evidence import scan, validate_file
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.audit_execution.schemas import RecordInput, RecordPatch
from app.modules.audit_log.service import record
from app.modules.collaboration.models import SharedLink, SharedSubmission
from app.modules.intelligence.jobs import actor
from app.modules.jurisdictions.profiles import Strict
from app.modules.saas.storage import put_private

router = APIRouter(prefix="/collaboration", tags=["Request-scoped client collaboration"])


class Issue(Strict):
    request_id: uuid.UUID
    expires_minutes: int = Field(default=1440, ge=1, le=10080)
    retain_until: date
    max_uploads: int = Field(default=5, ge=0, le=10)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)


class Accept(Strict):
    expected_request_version: int = Field(ge=1)
    comments: str = Field(min_length=10, max_length=4000)


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


async def policy_enabled(db, ctx, eid):
    policy = await audit.policy(db, ctx, eid)
    if policy.methodology.get("allow_account_free_portal") is not True:
        raise HTTPException(
            403, "Firm engagement policy has not enabled account-free client collaboration"
        )


@router.post("/engagements/{eid}/links", status_code=201)
async def issue(eid: uuid.UUID, data: Issue, db: DB, ctx: Actor, request: Request):
    await audit.engagement(db, ctx, eid, "audit.evidence.upload", True)
    await policy_enabled(db, ctx, eid)
    original = await audit.get_record(db, ctx, eid, data.request_id, lock=False)
    if (
        original.kind != "requests"
        or original.status in {"CLOSED", "RESOLVED", "ARCHIVED"}
        or data.retain_until <= date.today()
    ):
        raise HTTPException(422, "An open client request and future retention date are required")
    secret = secrets.token_hex(32)
    link = SharedLink(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        engagement_id=eid,
        request_id=original.id,
        request_version=original.version,
        token_hash=digest(secret),
        expires_at=datetime.now(UTC) + timedelta(minutes=data.expires_minutes),
        retain_until=data.retain_until,
        limits={
            "max_uploads": data.max_uploads,
            "max_file_bytes": data.max_file_bytes,
            "max_responses": 10,
        },
    )
    db.add(link)
    await db.flush()
    record(
        db,
        ctx,
        "collaboration.link.issued",
        link.id,
        request.state.request_id,
        {"request_id": str(original.id), "expires_at": link.expires_at.isoformat()},
    )
    return {
        "id": str(link.id),
        "expires_at": link.expires_at,
        "share_path": f"/client-share/{ctx.tenant_id}/{link.id}#{secret}",
        "token_display": "Shown once; the database retains only its SHA-256 hash",
    }


async def owned(db, ctx, eid, lid, write=False):
    await audit.engagement(db, ctx, eid, "audit.evidence.upload" if write else "audit.read", write)
    link = await db.scalar(
        select(SharedLink)
        .where(
            SharedLink.tenant_id == ctx.tenant_id,
            SharedLink.engagement_id == eid,
            SharedLink.id == lid,
        )
        .with_for_update()
    )
    if not link:
        raise HTTPException(404, "Client link not found")
    return link


@router.post("/engagements/{eid}/links/{lid}/revoke")
async def revoke(eid: uuid.UUID, lid: uuid.UUID, db: DB, ctx: Actor, request: Request):
    link = await owned(db, ctx, eid, lid)
    await audit.engagement(db, ctx, eid, "audit.evidence.upload", lock=False)
    link.revoked = True
    record(db, ctx, "collaboration.link.revoked", link.id, request.state.request_id)
    return {"id": str(link.id), "revoked": True}


@router.get("/engagements/{eid}/links")
async def links(eid: uuid.UUID, db: DB, ctx: Actor):
    await audit.engagement(db, ctx, eid, "audit.read", lock=False)
    rows = (
        await db.scalars(
            select(SharedLink)
            .where(SharedLink.tenant_id == ctx.tenant_id, SharedLink.engagement_id == eid)
            .order_by(SharedLink.created_at.desc())
            .limit(100)
        )
    ).all()
    return {
        "items": [
            {k: v for k, v in audit.serialize(row).items() if k != "token_hash"} for row in rows
        ],
        "limit": 100,
    }


async def guest(db, tenant, lid, secret, write=False):
    await tenant_context(db, str(tenant))
    query = select(SharedLink).where(SharedLink.tenant_id == tenant, SharedLink.id == lid)
    link = await db.scalar(query.with_for_update() if write else query)
    if (
        not secret
        or len(secret) != 64
        or not link
        or not hmac.compare_digest(link.token_hash, digest(secret))
        or link.revoked
        or link.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(404, "Client link is unavailable")
    try:
        ctx = await actor(db, tenant, link.created_by)
        await audit.engagement(
            db, ctx, link.engagement_id, "audit.evidence.upload", True, lock=False
        )
        await policy_enabled(db, ctx, link.engagement_id)
        original = await audit.get_record(db, ctx, link.engagement_id, link.request_id, lock=False)
        if (
            original.kind != "requests"
            or original.version != link.request_version
            or original.status in {"CLOSED", "RESOLVED", "ARCHIVED"}
        ):
            raise HTTPException(404, "Client request changed")
    except HTTPException:
        raise HTTPException(404, "Client link is unavailable") from None
    return link, ctx, original


Token = Annotated[str | None, Header(alias="X-Collaboration-Token")]


@router.get("/public/{tenant}/{lid}")
async def question(
    tenant: uuid.UUID, lid: uuid.UUID, db: DB, request: Request, token: Token = None
):
    link, ctx, original = await guest(db, tenant, lid, token)
    record(
        db,
        ctx,
        "collaboration.client.viewed",
        link.id,
        request.state.request_id,
        {"actor_kind": "shared_link"},
    )
    return {
        "title": original.title,
        "question": original.body["question"],
        "due_date": original.body.get("due_date"),
        "expires_at": link.expires_at,
        "max_file_bytes": link.limits["max_file_bytes"],
        "uploads_remaining": max(0, link.limits["max_uploads"] - link.uploads),
        "identity_status": "Link possession only; claimed client identity is unverified",
    }


@router.post("/public/{tenant}/{lid}", status_code=201)
async def submit(
    tenant: uuid.UUID,
    lid: uuid.UUID,
    db: DB,
    request: Request,
    token: Token = None,
    response: Annotated[str, Form(min_length=1, max_length=10000)] = "",
    claimed_name: Annotated[str, Form(max_length=200)] = "",
    file: Annotated[UploadFile | None, File()] = None,
):
    if not response.strip():
        raise HTTPException(422, "A client response is required")
    link, ctx, original = await guest(db, tenant, lid, token, True)
    if link.responses >= link.limits["max_responses"]:
        raise HTTPException(409, "Client response limit reached")
    body = {
        "actor_kind": "shared_link",
        "identity_verified": False,
        "claimed_name": claimed_name,
        "response": response,
        "request_id": str(original.id),
        "request_version": original.version,
        "evidence_id": None,
    }
    if file:
        if (
            link.uploads >= link.limits["max_uploads"]
            or file.size is None
            or file.size > link.limits["max_file_bytes"]
        ):
            raise HTTPException(413, "Client upload exceeds the link limits")
        try:
            media = await run_in_threadpool(validate_file, file.file, file.filename or "")
            status = await run_in_threadpool(scan, file.file)
            if status == "REJECTED":
                raise HTTPException(422, "Document rejected by malware scanner")
            metadata = await put_private(db, ctx, file.file)
        except (ValueError, OSError, zipfile.BadZipFile):
            raise HTTPException(422, "Document validation or private storage failed") from None
        evidence = await audit.create(
            db,
            ctx,
            link.engagement_id,
            "evidence",
            RecordInput(
                reference="CLIENT-" + secrets.token_hex(6),
                title="Client-provided supporting document",
                body={
                    "category": "Client link submission",
                    "retain_until": link.retain_until.isoformat(),
                    "narrative": "Collected through a request-scoped client link. Claimed identity is unverified; the issuing auditor owns collection, not the client claim.",
                },
            ),
            request.state.request_id,
        )
        version = EvidenceVersion(
            tenant_id=tenant,
            created_by=None,
            record_id=uuid.UUID(evidence["id"]),
            number=1,
            filename=Path((file.filename or "evidence").replace("\\", "/")).name[:200],
            media_type=media,
            scan_status=status,
            **metadata,
        )
        db.add(version)
        await db.flush()
        body.update(
            evidence_id=evidence["id"],
            file_version_id=str(version.id),
            sha256=version.sha256,
            filename=version.filename,
            scan_status=status,
        )
        link.uploads += 1
    # Recheck live issuer permissions/policy after external scanning/storage work.
    await guest(db, tenant, lid, token)
    submission = SharedSubmission(
        tenant_id=tenant, created_by=None, link_id=link.id, kind="response", body=body
    )
    db.add(submission)
    link.responses += 1
    await db.flush()
    record(
        db,
        ctx,
        "collaboration.client.responded",
        submission.id,
        request.state.request_id,
        {"actor_kind": "shared_link", "link_id": str(link.id), "identity_verified": False},
    )
    return {
        "id": str(submission.id),
        "status": "RECEIVED_FOR_REVIEW",
        "scan_status": body.get("scan_status"),
        "identity_verified": False,
    }


@router.get("/engagements/{eid}/links/{lid}/submissions")
async def submissions(eid: uuid.UUID, lid: uuid.UUID, db: DB, ctx: Actor):
    await owned(db, ctx, eid, lid)
    rows = (
        await db.scalars(
            select(SharedSubmission)
            .where(SharedSubmission.tenant_id == ctx.tenant_id, SharedSubmission.link_id == lid)
            .order_by(SharedSubmission.created_at)
            .limit(100)
        )
    ).all()
    return {"items": [audit.serialize(row) for row in rows], "limit": 100}


@router.post("/engagements/{eid}/links/{lid}/submissions/{sid}/accept", status_code=201)
async def accept(
    eid: uuid.UUID,
    lid: uuid.UUID,
    sid: uuid.UUID,
    data: Accept,
    db: DB,
    ctx: Actor,
    request: Request,
):
    link = await owned(db, ctx, eid, lid, True)
    submission = await db.scalar(
        select(SharedSubmission).where(
            SharedSubmission.tenant_id == ctx.tenant_id,
            SharedSubmission.link_id == lid,
            SharedSubmission.id == sid,
            SharedSubmission.kind == "response",
        )
    )
    if not submission:
        raise HTTPException(404, "Client response not found")
    existing = await db.scalar(
        select(SharedSubmission.id).where(
            SharedSubmission.tenant_id == ctx.tenant_id,
            SharedSubmission.link_id == lid,
            SharedSubmission.kind == "accepted",
            SharedSubmission.body["submission_id"].astext == str(sid),
        )
    )
    if existing:
        raise HTTPException(409, "This client response has already been accepted")
    original = await audit.get_record(db, ctx, eid, link.request_id, mutable=True)
    if original.version != data.expected_request_version:
        raise HTTPException(409, "Client request version conflict")
    text = (
        original.body.get("response", "")
        + f"\n[Client link response {sid}; identity unverified]\n"
        + submission.body["response"]
    )
    if len(text) > 4000:
        raise HTTPException(
            422,
            "Response exceeds the request field limit; review the immutable submission separately",
        )
    updated = await audit.update(
        db,
        ctx,
        eid,
        original.id,
        RecordPatch(
            version=original.version,
            reference=original.reference,
            title=original.title,
            body={
                **original.body,
                "response": text,
                "evidence_ids": [
                    *original.body.get("evidence_ids", []),
                    *(
                        [submission.body["evidence_id"]]
                        if submission.body.get("evidence_id")
                        else []
                    ),
                ],
            },
        ),
        request.state.request_id,
    )
    receipt = SharedSubmission(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        link_id=lid,
        kind="accepted",
        body={
            "submission_id": str(sid),
            "request_version": updated["version"],
            "comments": data.comments,
        },
    )
    db.add(receipt)
    await db.flush()
    return {
        "id": str(receipt.id),
        "request_version": updated["version"],
        "status": "ACCEPTED_INTO_REQUEST_DRAFT",
        "automatically_approved": False,
    }

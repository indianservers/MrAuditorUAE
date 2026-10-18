import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import Field
from sqlalchemy import func, or_, select
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import DB, Context, require
from app.db.models.platform import Engagement, LegalEntity, Membership
from app.modules.audit_execution import service as s
from app.modules.audit_execution.evidence import scan, validate_file
from app.modules.audit_execution.models import AuditRecord, ClientAccess, EvidenceVersion
from app.modules.audit_execution.schemas import Strict
from app.modules.saas.storage import put_private

router = APIRouter(prefix="/client-portal", tags=["Restricted client portal"])
Read = Annotated[Context, Depends(require("portal.read"))]
Respond = Annotated[Context, Depends(require("portal.respond"))]


class Answer(Strict):
    version: int = Field(ge=1)
    response: str = Field(min_length=1, max_length=6000)


def permitted(ctx):
    return (
        select(ClientAccess.client_id)
        .join(Membership, Membership.id == ClientAccess.membership_id)
        .where(
            ClientAccess.tenant_id == ctx.tenant_id,
            Membership.user_id == ctx.user_id,
            Membership.status == "active",
            or_(ClientAccess.expires_at.is_(None), ClientAccess.expires_at > datetime.now(UTC)),
        )
    )


def public(obj):
    # Deliberately allowlisted: never serialize internal record bodies, sources or review history.
    return {
        "id": str(obj.id),
        "reference": obj.reference,
        "title": obj.title,
        "status": obj.status,
        "version": obj.version,
        "question": obj.body["question"],
        "response": obj.body.get("response", ""),
        "due_date": obj.body.get("due_date"),
        "evidence_ids": obj.body.get("evidence_ids", []),
    }


async def request_record(db, ctx, rid, mutable=False):
    obj = await db.scalar(
        select(AuditRecord)
        .join(Engagement, Engagement.id == AuditRecord.engagement_id)
        .join(LegalEntity, LegalEntity.id == Engagement.entity_id)
        .where(
            AuditRecord.id == rid,
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.kind == "requests",
            AuditRecord.status != "DRAFT",
            LegalEntity.client_id.in_(permitted(ctx)),
        )
        .with_for_update(of=AuditRecord)
    )
    if not obj:
        raise HTTPException(404, "Request not found")
    if mutable:
        eng = await db.get(Engagement, obj.engagement_id)
        if not eng or eng.status.upper() in {"COMPLETED", "ARCHIVED", "CANCELLED"}:
            raise HTTPException(409, "Engagement is read-only")
    if obj.body["client_id"] not in {str(i) for i in (await db.scalars(permitted(ctx))).all()}:
        raise HTTPException(404, "Request not found")
    return obj


@router.get("/requests")
async def listing(
    db: DB, ctx: Read, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    query = (
        select(AuditRecord)
        .join(Engagement, Engagement.id == AuditRecord.engagement_id)
        .join(LegalEntity, LegalEntity.id == Engagement.entity_id)
        .where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.kind == "requests",
            AuditRecord.status != "DRAFT",
            LegalEntity.client_id.in_(permitted(ctx)),
        )
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(query.order_by(AuditRecord.created_at.desc()).offset(offset).limit(limit))
    ).all()
    return {"items": [public(r) for r in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/requests/{rid}/view")
async def view(rid: uuid.UUID, db: DB, ctx: Read, request: Request):
    obj = await request_record(db, ctx, rid)
    eng = await db.get(Engagement, obj.engagement_id)
    if (
        obj.status == "SENT"
        and eng
        and eng.status.upper() not in {"COMPLETED", "ARCHIVED", "CANCELLED"}
    ):
        obj.status = "VIEWED"
        obj.version += 1
        await s.revision(db, ctx, obj, request.state.request_id, "request.viewed")
    return public(obj)


@router.post("/requests/{rid}/responses")
async def respond(rid: uuid.UUID, data: Answer, db: DB, ctx: Respond, request: Request):
    obj = await request_record(db, ctx, rid, True)
    if obj.version != data.version or obj.status not in {
        "SENT",
        "VIEWED",
        "MORE_INFORMATION_REQUIRED",
    }:
        raise HTTPException(409, "Request version or state changed")
    obj.body = {**obj.body, "response": data.response}
    obj.status = "RESPONDED"
    obj.version += 1
    await s.revision(db, ctx, obj, request.state.request_id, "request.responded")
    return public(obj)


@router.post("/requests/{rid}/upload", status_code=201)
async def upload(
    rid: uuid.UUID, db: DB, ctx: Respond, request: Request, file: Annotated[UploadFile, File()]
):
    obj = await request_record(db, ctx, rid, True)
    eng = await db.get(Engagement, obj.engagement_id)
    if not eng:
        raise HTTPException(404, "Engagement not found")
    if obj.status not in {"SENT", "VIEWED", "MORE_INFORMATION_REQUIRED"} or eng.status.upper() in {
        "COMPLETED",
        "ARCHIVED",
        "CANCELLED",
    }:
        raise HTTPException(409, "Request does not accept uploads")
    from app.core.config import settings

    if file.size is None or file.size > settings().max_upload_bytes:
        raise HTTPException(413, "Evidence exceeds upload limit")
    try:
        media_type = await run_in_threadpool(validate_file, file.file, file.filename or "")
        status = await run_in_threadpool(scan, file.file)
        if status == "REJECTED":
            raise ValueError("Evidence rejected by scanner")
        metadata = await put_private(db, ctx, file.file)
    except (ValueError, OSError, zipfile.BadZipFile):
        raise HTTPException(422, "Evidence failed file validation") from None
    evidence = AuditRecord(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        prepared_by=ctx.user_id,
        engagement_id=obj.engagement_id,
        kind="evidence",
        reference="PBC-" + str(uuid.uuid4())[:12],
        title=Path(file.filename or "Client evidence").name[:200],
        body={
            "category": "Client response",
            "request_id": str(obj.id),
            "retain_until": "2036-12-31",
        },
        status="IN_PROGRESS",
    )
    db.add(evidence)
    await s.revision(db, ctx, evidence, request.state.request_id, "portal.evidence.uploaded")
    db.add(
        EvidenceVersion(
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
            record_id=evidence.id,
            number=1,
            filename=evidence.title,
            media_type=media_type,
            scan_status=status,
            **metadata,
        )
    )
    obj.body = {**obj.body, "evidence_ids": [*obj.body.get("evidence_ids", []), str(evidence.id)]}
    obj.version += 1
    await s.revision(db, ctx, obj, request.state.request_id, "request.evidence.attached")
    return {"evidence_id": str(evidence.id), "scan_status": status, "sha256": metadata["sha256"]}

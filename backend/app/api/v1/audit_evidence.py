import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.v1.audit_execution import Actor
from app.core.dependencies import DB
from app.modules.audit_execution import service as s
from app.modules.audit_execution.evidence import scan, validate_file
from app.modules.audit_execution.models import EvidenceVersion
from app.modules.audit_log.service import record
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.saas.storage import put_private

router = APIRouter(
    prefix="/engagements/{eid}/audit/evidence-files", tags=["Private audit evidence"]
)


@router.post("/{rid}", status_code=201)
async def upload(
    eid: uuid.UUID,
    rid: uuid.UUID,
    db: DB,
    ctx: Actor,
    request: Request,
    file: Annotated[UploadFile, File()],
):
    obj = await s.get_record(db, ctx, eid, rid, "audit.evidence.upload", True)
    if obj.kind != "evidence" or obj.status in {"APPROVED", "LOCKED", "REVIEW_REQUIRED"}:
        raise HTTPException(409, "Editable evidence record required")
    from app.core.config import settings

    if file.size is None or file.size > settings().max_upload_bytes:
        raise HTTPException(413, "Evidence exceeds upload limit")
    try:
        media_type = await run_in_threadpool(validate_file, file.file, file.filename or "")
        status = await run_in_threadpool(scan, file.file)
        if status == "REJECTED":
            raise HTTPException(422, "Evidence rejected by malware scanner")
        metadata = await put_private(db, ctx, file.file)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(422, str(exc)) from None
    number = (
        await db.scalar(
            select(func.max(EvidenceVersion.number)).where(EvidenceVersion.record_id == rid)
        )
    ) or 0
    version = EvidenceVersion(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        record_id=rid,
        number=number + 1,
        filename=Path(file.filename or "evidence").name[:200],
        media_type=media_type,
        scan_status=status,
        **metadata,
    )
    db.add(version)
    obj.version += 1
    await s.revision(db, ctx, obj, request.state.request_id, "evidence.uploaded")
    return s.serialize(version)


@router.get("/{rid}")
async def versions(eid: uuid.UUID, rid: uuid.UUID, db: DB, ctx: Actor):
    await s.get_record(db, ctx, eid, rid)
    rows = (
        await db.scalars(
            select(EvidenceVersion)
            .where(EvidenceVersion.tenant_id == ctx.tenant_id, EvidenceVersion.record_id == rid)
            .order_by(EvidenceVersion.number.desc())
        )
    ).all()
    return {
        "items": [
            {k: v for k, v in s.serialize(r).items() if k not in {"object_key", "object_version"}}
            for r in rows
        ]
    }


@router.get("/{rid}/{vid}/download")
async def download(
    eid: uuid.UUID, rid: uuid.UUID, vid: uuid.UUID, db: DB, ctx: Actor, request: Request
):
    await s.get_record(db, ctx, eid, rid)
    version = await db.scalar(
        select(EvidenceVersion).where(
            EvidenceVersion.id == vid,
            EvidenceVersion.record_id == rid,
            EvidenceVersion.tenant_id == ctx.tenant_id,
        )
    )
    if not version:
        raise HTTPException(404, "Evidence version not found")
    if version.scan_status != "CLEAN":
        raise HTTPException(409, "Evidence is quarantined; scanner integration required")

    def read():
        with ObjectStore().local(version.object_key, version.object_version) as path:
            if hash_file(path) != version.sha256:
                raise ValueError("Evidence integrity verification failed")
            return path.read_bytes()

    try:
        data = await run_in_threadpool(read)
    except (ValueError, OSError):
        raise HTTPException(409, "Evidence integrity verification failed") from None
    record(
        db,
        ctx,
        "audit.evidence.downloaded",
        version.id,
        request.state.request_id,
        {"sha256": version.sha256},
    )
    from urllib.parse import quote

    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(version.filename),
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )

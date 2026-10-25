"""Immutable firm legal-reference copies; uploaded bytes do not authenticate a URL."""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.modules.audit_execution.evidence import scan, validate_file
from app.modules.audit_log.service import record
from app.modules.lineage.storage import ObjectStore, hash_file
from app.modules.regulatory.models import RuleSourceDocument
from app.modules.saas.storage import put_private

MAX_BYTES = 10 * 1024 * 1024


def info(document):
    return {
        key: getattr(document, key)
        for key in (
            "id",
            "title",
            "country",
            "source_url",
            "retrieved_on",
            "filename",
            "media_type",
            "sha256",
            "size",
            "scan_status",
            "created_by",
            "created_at",
        )
    }


async def get(db, ctx, identifier):
    document = await db.scalar(
        select(RuleSourceDocument).where(
            RuleSourceDocument.tenant_id == ctx.tenant_id,
            RuleSourceDocument.id == identifier,
        )
    )
    if document is None:
        raise HTTPException(404, "Retained regulatory source not found")
    return document


def read(document, *, download=False):
    if document.scan_status != "CLEAN":
        raise ValueError("Retained regulatory source is not malware-cleared")
    with ObjectStore().local(document.object_key, document.object_version) as path:
        size = path.stat().st_size
        if (
            size <= 0
            or size > MAX_BYTES
            or size != document.size
            or hash_file(path) != document.sha256
        ):
            raise ValueError("Retained regulatory source failed original-file integrity")
        return path.read_bytes() if download else None


async def upload(db, ctx, file, metadata, request_id):
    def inspect():
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if not 0 < size <= MAX_BYTES:
            raise HTTPException(
                413, "Regulatory reference copies must be nonempty and at most 10 MiB"
            )
        if Path(file.filename or "").suffix.lower() not in {".pdf", ".txt"}:
            raise ValueError("Regulatory reference copies support PDF and UTF-8 text only")
        media = validate_file(file.file, file.filename or "")
        if media not in {"application/pdf", "text/plain"}:
            raise ValueError("Regulatory reference copies support PDF and UTF-8 text only")
        status = scan(file.file)
        file.file.seek(0)
        return media, status

    try:
        media, status = await run_in_threadpool(inspect)
    except (ValueError, OSError):
        raise HTTPException(422, "Invalid regulatory reference document") from None
    if status != "CLEAN":
        raise HTTPException(
            422 if status == "REJECTED" else 409,
            "Regulatory source requires a successful malware scan; upload again after clearance",
        )
    stored = await put_private(db, ctx, file.file)
    document = RuleSourceDocument(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        **metadata.model_dump(exclude={"source_url"}),
        source_url=str(metadata.source_url),
        filename=Path(file.filename or "source").name[:200],
        media_type=media,
        scan_status=status,
        **stored,
    )
    db.add(document)
    await db.flush()
    record(
        db,
        ctx,
        "regulatory.source_retained",
        document.id,
        request_id,
        {"sha256": document.sha256, "source_url": document.source_url, "country": document.country},
    )
    return document


def verification_snapshot(db):
    session = getattr(db, "sync_session", None)
    transaction = session.get_transaction() if session is not None else None
    info = getattr(db, "info", None)
    if transaction is None or not isinstance(info, dict):
        return {"verified": set(), "bytes": 0}
    cached = info.get("_regulatory_source_integrity")
    if cached is not None and cached[0] is transaction:
        return cached[1]
    snapshot = {"verified": set(), "bytes": 0}
    info["_regulatory_source_integrity"] = (transaction, snapshot)
    return snapshot


async def verify_rule_sources(db, ctx, rule):
    documents = {}
    receipts = []
    for citation in rule.citations:
        if citation.source_document_id is None:
            raise HTTPException(
                409, "Every published citation requires a retained regulatory source copy"
            )
        identifier = citation.source_document_id
        if identifier not in documents:
            try:
                documents[identifier] = await get(db, ctx, identifier)
            except HTTPException as error:
                if error.status_code == 404:
                    raise HTTPException(
                        409, "Citation source copy is unavailable in this firm"
                    ) from None
                raise
        document = documents[identifier]
        if (
            document.country not in {rule.country, "GLOBAL"}
            or document.sha256 != citation.document_sha256
            or document.source_url != str(citation.url)
            or document.retrieved_on != citation.retrieved_on
        ):
            raise HTTPException(
                409,
                "Citation country, URL, retrieval date and hash must agree to its retained source copy",
            )
        receipts.append(
            {
                "id": str(identifier),
                "sha256": document.sha256,
                "country": document.country,
                "source_url": document.source_url,
                "retrieved_on": document.retrieved_on.isoformat(),
                "created_by": str(document.created_by) if document.created_by else None,
            }
        )
    try:
        snapshot = verification_snapshot(db)
        for document in documents.values():
            key = (
                str(ctx.tenant_id),
                str(document.id),
                document.object_key,
                document.object_version,
                document.sha256,
                document.size,
            )
            if key in snapshot["verified"]:
                continue
            if snapshot["bytes"] + document.size > 100 * 1024 * 1024:
                raise HTTPException(
                    422, "Regulatory source verification exceeds 100 MiB per transaction"
                )
            await run_in_threadpool(read, document)
            snapshot["verified"].add(key)
            snapshot["bytes"] += document.size
    except (ValueError, OSError):
        raise HTTPException(
            409, "Retained regulatory source failed original-file integrity"
        ) from None
    return receipts

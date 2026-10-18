import hashlib
import io
import math
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, BinaryIO, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.api.v1.accounting import page, serialize
from app.core.config import settings
from app.core.dependencies import DB, Context, require
from app.modules.accounting.models import Connection, UploadSession
from app.modules.accounting.schemas import ImportOptions, Input, ScopeInput
from app.modules.accounting.service import check_scope, scoped, upload
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.connectors.service import zoho_sync
from app.modules.connectors.zoho import REGIONS, ZohoConnector
from app.modules.lineage.storage import ObjectStore
from app.modules.saas.storage import put_private

router = APIRouter(tags=["Accounting connectors"])
Manage = Annotated[Context, Depends(require("connectors.manage"))]
Read = Annotated[Context, Depends(require("accounting.read"))]
Write = Annotated[Context, Depends(require("accounting.import"))]


class ConnectionCreate(ScopeInput):
    provider: Literal["zoho", "tally"]
    name: str = Field(min_length=1, max_length=100)
    region: str = "ae"
    organization_id: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict, max_length=10)


@router.post("/accounting/connections", response_model=dict, status_code=201)
async def create(data: ConnectionCreate, db: DB, ctx: Manage):
    await check_scope(db, ctx, data)
    if data.region not in REGIONS:
        raise HTTPException(422, "Unapproved regional domain")
    if data.provider == "zoho" and not {"client_id", "client_secret"} <= data.credentials.keys():
        raise HTTPException(422, "Zoho OAuth client credentials required")
    try:
        secret = encrypt(data.credentials) if data.credentials else None
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None
    connection = Connection(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        client_id=data.client_id,
        entity_id=data.entity_id,
        period_id=data.period_id,
        provider=data.provider,
        name=data.name,
        region=data.region,
        organization_id=data.organization_id,
        encrypted_credentials=secret,
    )
    db.add(connection)
    await db.flush()
    return serialize(connection)


@router.get("/accounting/connections", response_model=dict)
async def connections(
    db: DB, ctx: Manage, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    return await page(db, ctx, Connection, offset, limit)


class OAuthStart(Input):
    redirect_uri: str = Field(max_length=500)


@router.post("/connectors/zoho/{identifier}/authorize", response_model=dict)
async def authorize(identifier: uuid.UUID, data: OAuthStart, db: DB, ctx: Manage):
    import secrets

    connection = await scoped(db, ctx, Connection, identifier, True)
    if data.redirect_uri not in settings().zoho_redirect_uris:
        raise HTTPException(422, "OAuth redirect URI is not configured")
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region, credentials["client_id"], credentials["client_secret"]
    )
    state = secrets.token_urlsafe(32)
    credentials.update(
        oauth_state_hash=hashlib.sha256(state.encode()).hexdigest(),
        oauth_expires=(datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        redirect_uri=data.redirect_uri,
    )
    connection.encrypted_credentials = encrypt(credentials)
    return {"authorization_url": adapter.authorization_url(data.redirect_uri, state)}


class OAuthCallback(Input):
    code: str = Field(min_length=1, max_length=1000)
    state: str = Field(min_length=32, max_length=128)


@router.post("/connectors/zoho/{identifier}/callback", response_model=dict)
async def callback(identifier: uuid.UUID, data: OAuthCallback, db: DB, ctx: Manage):
    import hmac

    connection = await scoped(db, ctx, Connection, identifier, True)
    credentials = decrypt(connection.encrypted_credentials or "")
    if not hmac.compare_digest(
        credentials.get("oauth_state_hash", ""), hashlib.sha256(data.state.encode()).hexdigest()
    ) or datetime.fromisoformat(
        credentials.get("oauth_expires", "2000-01-01T00:00:00+00:00")
    ) < datetime.now(UTC):
        raise HTTPException(403, "OAuth state invalid or expired")
    adapter = ZohoConnector(
        connection.region, credentials["client_id"], credentials["client_secret"]
    )
    credentials.update(await adapter.token(data.code, credentials["redirect_uri"]))
    credentials.pop("oauth_state_hash", None)
    connection.encrypted_credentials = encrypt(credentials)
    connection.status = "authorized"
    return {"status": "authorized", "connectivity": "token_exchange_only"}


@router.get("/connectors/zoho/{identifier}/organizations", response_model=dict)
async def organizations(identifier: uuid.UUID, db: DB, ctx: Manage):
    connection = await scoped(db, ctx, Connection, identifier)
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region,
        credentials["client_id"],
        credentials["client_secret"],
        credentials.get("refresh_token", ""),
    )
    data = await adapter.get("organizations", {})
    return {"organizations": data.get("organizations", [])}


class Organization(Input):
    organization_id: str = Field(pattern=r"^[0-9]+$")


@router.post("/connectors/zoho/{identifier}/organization", response_model=dict)
async def choose_organization(identifier: uuid.UUID, data: Organization, db: DB, ctx: Manage):
    connection = await scoped(db, ctx, Connection, identifier, True)
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region,
        credentials["client_id"],
        credentials["client_secret"],
        credentials.get("refresh_token", ""),
    )
    organizations = await adapter.get("organizations", {})
    if data.organization_id not in {
        str(o["organization_id"]) for o in organizations.get("organizations", [])
    }:
        raise HTTPException(403, "Organization access not established")
    connection.organization_id = data.organization_id
    return {"status": "organization_selected"}


@router.post("/connectors/zoho/{identifier}/sync", response_model=dict)
async def sync(
    identifier: uuid.UUID, db: DB, ctx: Manage, request: Request, background: bool = True
):
    await scoped(db, ctx, Connection, identifier)
    if background:
        from app.workers.accounting import submit

        return await submit(
            db, ctx, "zoho.sync", {"connection_id": str(identifier)}, request.state.request_id
        )
    return await zoho_sync(db, ctx, identifier)


@router.get("/connectors/tally", response_model=dict)
async def tally(ctx: Read):
    return {
        "interface": "local HTTP/XML via authorized Windows agent",
        "package": "native XML, CSV or XLSX reports",
        "completeness": "Independent source controls required",
        "live_connection": "not_probed",
    }


class UploadCreate(Input):
    options: ImportOptions
    filename: str = Field(min_length=1, max_length=200)
    total_size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/accounting/uploads", response_model=dict, status_code=201)
async def create_upload(data: UploadCreate, db: DB, ctx: Write):
    await check_scope(db, ctx, data.options)
    if data.total_size > settings().max_upload_bytes:
        raise HTTPException(413, "Upload too large")
    session = UploadSession(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        client_id=data.options.client_id,
        entity_id=data.options.entity_id,
        period_id=data.options.period_id,
        filename=data.filename,
        total_size=data.total_size,
        sha256=data.sha256,
        options=data.options.model_dump(mode="json"),
    )
    db.add(session)
    await db.flush()
    return {"id": str(session.id), "chunk_size": settings().upload_chunk_bytes, "received": []}


@router.get("/accounting/uploads/{identifier}", response_model=dict)
async def get_upload(identifier: uuid.UUID, db: DB, ctx: Write):
    session = await scoped(db, ctx, UploadSession, identifier)
    return {
        "id": str(session.id),
        "status": session.status,
        "received": sorted(int(i) for i in session.chunks),
        "chunk_size": settings().upload_chunk_bytes,
        "batch_id": str(session.batch_id) if session.batch_id else None,
    }


@router.put("/accounting/uploads/{identifier}/chunks/{index}", response_model=dict)
async def chunk(identifier: uuid.UUID, index: int, db: DB, ctx: Write, request: Request):
    session = await scoped(db, ctx, UploadSession, identifier, True)
    if session.status != "pending":
        raise HTTPException(409, "Upload already finalized")
    chunk_size = settings().upload_chunk_bytes
    if index < 0 or index >= math.ceil(session.total_size / chunk_size):
        raise HTTPException(422, "Chunk index outside upload")
    data = await request.body()
    expected = min(chunk_size, session.total_size - index * chunk_size)
    if len(data) != expected:
        raise HTTPException(422, "Unexpected chunk length")
    sha = hashlib.sha256(data).hexdigest()
    existing = session.chunks.get(str(index))
    if existing:
        if existing["sha256"] != sha:
            raise HTTPException(409, "Chunk retry content differs")
    else:
        stored = await put_private(db, ctx, io.BytesIO(data))
        session.chunks = {**session.chunks, str(index): stored}
    return {"index": index, "sha256": sha, "status": "stored"}


@router.post("/accounting/uploads/{identifier}/complete", response_model=dict)
async def complete_upload(identifier: uuid.UUID, db: DB, ctx: Write, request: Request):
    session = await scoped(db, ctx, UploadSession, identifier, True)
    if session.batch_id:
        return {"batch_id": str(session.batch_id), "status": "completed"}
    if len(session.chunks) != math.ceil(session.total_size / settings().upload_chunk_bytes):
        raise HTTPException(409, "Upload is incomplete")
    sha = hashlib.sha256()
    size = 0
    with tempfile.TemporaryFile() as staged_file:
        file = staged_file.file if hasattr(staged_file, "file") else staged_file
        for index in range(len(session.chunks)):
            item = session.chunks[str(index)]
            with (
                ObjectStore().local(item["object_key"], item["object_version"]) as path,
                path.open("rb") as source,
            ):
                while data := source.read(1024 * 1024):
                    file.write(data)
                    sha.update(data)
                    size += len(data)
        if sha.hexdigest() != session.sha256 or size != session.total_size:
            raise HTTPException(422, "Final source integrity mismatch")
        file.seek(0)
        batch = await upload(
            db,
            ctx,
            ImportOptions.model_validate(session.options),
            session.filename,
            cast(BinaryIO, file),
            request.state.request_id,
        )
    session.batch_id = batch.id
    session.status = "completed"
    return {"batch_id": str(batch.id), "status": "completed"}


@router.get("/connectors/zoho/sync-runs/{identifier}", response_model=dict)
async def sync_status(identifier: uuid.UUID, db: DB, ctx: Manage):
    from app.modules.accounting.models import SyncRun

    run = await scoped(db, ctx, SyncRun, identifier)
    return serialize(run)

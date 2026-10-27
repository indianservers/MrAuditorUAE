import hashlib
import io
import math
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, BinaryIO, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.v1.accounting import page, serialize
from app.core.config import settings
from app.core.dependencies import DB, Context, require
from app.modules.accounting.models import Connection, UploadSession
from app.modules.accounting.schemas import ImportOptions, Input, ScopeInput, SourceSystem
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


def native_credentials(value: str | None) -> dict:
    try:
        return decrypt(value) if value else {}
    except ValueError:
        raise HTTPException(503, "Secure connector credential storage is unavailable") from None


def store_native_credentials(values: dict) -> str | None:
    try:
        return encrypt(values) if values else None
    except ValueError:
        raise HTTPException(503, "Configure a valid CONNECTOR_ENCRYPTION_KEY first") from None


@router.get("/connectors/catalogue")
async def catalogue(ctx: Read):
    from app.modules.connectors.catalogue import PROVIDERS

    return {
        "items": PROVIDERS,
        "live_provider_qualification": False,
        "file_contract": "Normalize exports to the import schema, preview, map, validate and explicitly commit",
    }


class ConnectionCreate(ScopeInput):
    provider: SourceSystem
    name: str = Field(min_length=1, max_length=100)
    region: str = "ae"
    organization_id: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict, max_length=10)
    config: dict = Field(default_factory=dict, max_length=100)


@router.post("/accounting/connections", response_model=dict, status_code=201)
async def create(data: ConnectionCreate, db: DB, ctx: Manage):
    await check_scope(db, ctx, data)
    if data.provider == "file":
        raise HTTPException(422, "File imports do not need a connection")
    if data.provider == "zoho" and data.region not in REGIONS:
        raise HTTPException(422, "Unapproved regional domain")
    if data.provider == "zoho" and not all(
        data.credentials.get(key, "").strip() for key in ("client_id", "client_secret")
    ):
        raise HTTPException(422, "Zoho OAuth client credentials required")
    from app.modules.connectors.native_config import CREDENTIAL_FIELDS, NATIVE_PROVIDERS, configure

    native_config = {}
    if data.provider in NATIVE_PROVIDERS:
        native_config = configure(data.provider, data.config).model_dump(mode="json")
        if set(data.credentials) - set(CREDENTIAL_FIELDS[data.provider]):
            raise HTTPException(422, "Unsupported credential field for this provider")
    elif data.provider != "zoho" and data.credentials:
        raise HTTPException(
            422, "This provider uses local-agent or report import; no API credentials accepted"
        )
    if data.provider == "zoho" and data.organization_id:
        raise HTTPException(422, "Select an accessible organization after OAuth authorization")
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
        config=native_config,
        status="configured"
        if data.credentials or data.provider == "tally"
        else "credentials_pending",
    )
    db.add(connection)
    await db.flush()
    return serialize(connection)


class DirectConfiguration(Input):
    config: dict | None = Field(default=None, max_length=100)
    credentials: dict[str, str] | None = Field(default=None, max_length=10)
    replace_credentials: bool = False


@router.patch("/connectors/native/{identifier}/configuration", response_model=dict)
async def direct_configuration(
    identifier: uuid.UUID, data: DirectConfiguration, db: DB, ctx: Manage
):
    from app.modules.audit_log.service import record
    from app.modules.connectors.native_config import CREDENTIAL_FIELDS, NATIVE_PROVIDERS, configure

    connection = await scoped(db, ctx, Connection, identifier, True)
    if connection.provider not in NATIVE_PROVIDERS:
        raise HTTPException(422, "A direct API connection is required")
    if data.config is not None:
        connection.config = configure(connection.provider, data.config).model_dump(mode="json")
    if data.credentials is not None and set(data.credentials) - set(
        CREDENTIAL_FIELDS[connection.provider]
    ):
        raise HTTPException(422, "Unsupported credential field for this provider")
    credentials = native_credentials(connection.encrypted_credentials)
    if data.replace_credentials:
        credentials = {}
    credentials.update(data.credentials or {})
    for key in ("oauth_state_hash", "oauth_expires", "redirect_uri"):
        credentials.pop(key, None)
    connection.encrypted_credentials = store_native_credentials(credentials)
    connection.status = "configured" if credentials else "credentials_pending"
    record(db, ctx, "connector.configuration_updated", connection.id, str(identifier))
    return serialize(connection)


@router.post("/connectors/native/{identifier}/sync", response_model=dict)
async def direct_sync(
    identifier: uuid.UUID,
    db: DB,
    ctx: Manage,
    request: Request,
    background: bool = True,
    resume_session: uuid.UUID | None = None,
):
    from app.modules.connectors.native_config import NATIVE_PROVIDERS, configure
    from app.modules.connectors.native_service import direct_sync as execute

    connection = await scoped(db, ctx, Connection, identifier)
    if connection.provider not in NATIVE_PROVIDERS:
        raise HTTPException(422, "A direct API connection is required")
    configure(connection.provider, connection.config, complete=True)
    if not connection.encrypted_credentials:
        raise HTTPException(422, "Secure API credentials are required before synchronization")
    if background:
        from app.workers.accounting import submit

        return await submit(
            db,
            ctx,
            "connector.sync",
            {
                "connection_id": str(identifier),
                "resume_session": str(resume_session) if resume_session else None,
                "request_key": request.headers.get("Idempotency-Key") or str(uuid.uuid4()),
            },
            request.state.request_id,
        )
    await db.commit()  # Release admission lock before independent checkpoint transactions.
    from app.db.session import Session, tenant_context

    async with Session() as execution, execution.begin():
        await tenant_context(execution, str(ctx.tenant_id))
        return await execute(
            execution, ctx, identifier, str(resume_session) if resume_session else None
        )


@router.get("/connectors/native/sync-runs/{identifier}", response_model=dict)
async def direct_sync_status(identifier: uuid.UUID, db: DB, ctx: Manage):
    from app.modules.accounting.models import SyncRun

    return serialize(await scoped(db, ctx, SyncRun, identifier))


@router.get("/connectors/{provider}/requirements", response_model=dict)
async def requirements(provider: SourceSystem, ctx: Read):
    from app.modules.connectors.catalogue import PROVIDERS, REQUIREMENTS
    from app.modules.connectors.reports import REPORT_COLUMNS

    result = {
        "provider": next(p for p in PROVIDERS if p["id"] == provider),
        "live_testing_requirements": REQUIREMENTS[provider],
        "report_columns": REPORT_COLUMNS,
        "report_package_endpoint": "/api/v1/connectors/report-packages",
        "instructions": "Use flat CSV/XLSX exports; map source headings; retain source IDs and independent totals",
    }
    from app.modules.connectors.native_config import (
        CREDENTIAL_FIELDS,
        EDITIONS,
        NATIVE_PROVIDERS,
        PARTNER_FIELDS,
        SETUP_FIELDS,
        SOURCE_DOCS,
    )

    if provider in NATIVE_PROVIDERS:
        result["direct_api"] = {
            "editions": EDITIONS[provider],
            "credential_fields": CREDENTIAL_FIELDS[provider],
            "config_fields": [
                "company_id",
                "functional_currency",
                *SETUP_FIELDS[provider],
                "control_reference",
                "expected_gl_rows",
                "expected_gl_debit",
                "expected_gl_credit",
            ],
            "partner_fields": PARTNER_FIELDS,
            "documentation": SOURCE_DOCS[provider],
            "oauth": provider in {"quickbooks", "xero"},
            "qualification": "not_live_tested",
        }
    return result


@router.post("/connectors/report-packages", response_model=dict, status_code=201)
async def report_package(
    db: DB,
    ctx: Write,
    request: Request,
    options: Annotated[str, Form()],
    gl: Annotated[UploadFile, File()],
    tb: Annotated[UploadFile, File()],
    coa: Annotated[UploadFile, File()],
):
    from pathlib import Path

    from app.modules.connectors.reports import ReportPackageOptions, inspect_report_set
    from app.modules.ingestion.parser import ImportProblem

    try:
        data = ReportPackageOptions.model_validate_json(options)
    except ValidationError:
        raise HTTPException(422, "Invalid report-package options") from None
    entity, period = await check_scope(db, ctx, data)
    sources = {"gl": gl, "tb": tb, "coa": coa}
    with tempfile.TemporaryDirectory(prefix="auditos-reports-") as directory:
        files = {}
        combined_size = 0
        for kind, source in sources.items():
            path = Path(directory) / kind
            size = 0
            with path.open("wb") as target:
                while block := await source.read(1024 * 1024):
                    size += len(block)
                    combined_size += len(block)
                    if combined_size > min(settings().max_upload_bytes, 64 * 1024 * 1024):
                        raise HTTPException(413, "Combined reports exceed upload limit")
                    target.write(block)
            files[kind] = (path, source.filename or "")
        try:
            result = await run_in_threadpool(
                inspect_report_set,
                files,
                data,
                period.start_date,
                period.end_date,
                entity.functional_currency,
            )
        except (ImportProblem, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        batches = {}
        for kind in ("coa", "tb", "gl"):
            path, filename = files[kind]
            with path.open("rb") as stream:
                batch = await upload(
                    db,
                    ctx,
                    data.import_options(kind).model_copy(update={"report_package": result}),
                    filename,
                    stream,
                    request.state.request_id,
                )
            batches[kind] = str(batch.id)
        return {**result, "batch_ids": batches, "source_system": data.source_system}


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
    if connection.provider != "zoho":
        raise HTTPException(422, "A Zoho connection is required")
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


class DirectOAuthCallback(OAuthCallback):
    realm_id: str | None = Field(default=None, pattern=r"^[0-9]+$")


@router.post("/connectors/native/{identifier}/authorize", response_model=dict)
async def direct_authorize(identifier: uuid.UUID, data: OAuthStart, db: DB, ctx: Manage):
    import secrets

    from app.modules.connectors.native_auth import authorization_url
    from app.modules.connectors.native_config import configure, partner_mode

    connection = await scoped(db, ctx, Connection, identifier, True)
    config = configure(connection.provider, connection.config)
    if partner_mode(config) or connection.provider not in {"quickbooks", "xero"}:
        raise HTTPException(422, "This provider uses secure API credentials")
    if data.redirect_uri not in settings().connector_redirect_uris:
        raise HTTPException(422, "Register this URL in CONNECTOR_REDIRECT_URIS first")
    credentials = native_credentials(connection.encrypted_credentials)
    state = secrets.token_urlsafe(32)
    url = authorization_url(connection.provider, credentials, data.redirect_uri, state)
    credentials.update(
        oauth_state_hash=hashlib.sha256(state.encode()).hexdigest(),
        oauth_expires=(datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        redirect_uri=data.redirect_uri,
    )
    connection.encrypted_credentials = store_native_credentials(credentials)
    return {"authorization_url": url}


@router.post("/connectors/native/{identifier}/callback", response_model=dict)
async def direct_callback(identifier: uuid.UUID, data: DirectOAuthCallback, db: DB, ctx: Manage):
    import hmac

    from app.modules.connectors.native_auth import token
    from app.modules.connectors.native_config import configure, partner_mode

    connection = await scoped(db, ctx, Connection, identifier, True)
    config = configure(connection.provider, connection.config)
    if connection.provider not in {"quickbooks", "xero"} or partner_mode(config):
        raise HTTPException(422, "This interface does not use browser authorization")
    credentials = native_credentials(connection.encrypted_credentials)
    if not hmac.compare_digest(
        credentials.get("oauth_state_hash", ""), hashlib.sha256(data.state.encode()).hexdigest()
    ) or datetime.fromisoformat(
        credentials.get("oauth_expires", "2000-01-01T00:00:00+00:00")
    ) < datetime.now(UTC):
        raise HTTPException(403, "OAuth state invalid or expired")
    if connection.provider == "quickbooks":
        if not data.realm_id or (config.company_id and config.company_id != data.realm_id):
            raise HTTPException(422, "QuickBooks callback realm differs from the selected company")
        config.company_id = data.realm_id
    credentials = await token(
        connection.provider, config, credentials, data.code, credentials["redirect_uri"]
    )
    for key in ("oauth_state_hash", "oauth_expires", "redirect_uri"):
        credentials.pop(key, None)
    connection.encrypted_credentials = store_native_credentials(credentials)
    connection.config = config.model_dump(mode="json")
    connection.status = "authorized"
    return {"status": "authorized", "connectivity": "token_exchange_only"}


@router.post("/connectors/zoho/{identifier}/callback", response_model=dict)
async def callback(identifier: uuid.UUID, data: OAuthCallback, db: DB, ctx: Manage):
    import hmac

    connection = await scoped(db, ctx, Connection, identifier, True)
    if connection.provider != "zoho":
        raise HTTPException(422, "A Zoho connection is required")
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
    if connection.provider != "zoho":
        raise HTTPException(422, "A Zoho connection is required")
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
    if connection.provider != "zoho":
        raise HTTPException(422, "A Zoho connection is required")
    credentials = decrypt(connection.encrypted_credentials or "")
    adapter = ZohoConnector(
        connection.region,
        credentials["client_id"],
        credentials["client_secret"],
        credentials.get("refresh_token", ""),
    )
    organizations = await adapter.get("organizations", {})
    organization = next(
        (
            o
            for o in organizations.get("organizations", [])
            if str(o["organization_id"]) == data.organization_id
        ),
        None,
    )
    if not organization:
        raise HTTPException(403, "Organization access not established")
    entity, _ = await check_scope(db, ctx, connection)
    if organization.get("currency_code") != entity.functional_currency:
        raise HTTPException(
            422, "Zoho organization base currency differs from the selected legal entity"
        )
    connection.organization_id = data.organization_id
    return {"status": "organization_selected"}


@router.post("/connectors/zoho/{identifier}/sync", response_model=dict)
async def sync(
    identifier: uuid.UUID,
    db: DB,
    ctx: Manage,
    request: Request,
    background: bool = True,
    resume_session: uuid.UUID | None = None,
):
    connection = await scoped(db, ctx, Connection, identifier)
    if connection.provider != "zoho" or not connection.organization_id:
        raise HTTPException(422, "An authorized Zoho connection and organization are required")
    if background:
        from app.workers.accounting import submit

        return await submit(
            db,
            ctx,
            "zoho.sync",
            {
                "connection_id": str(identifier),
                "resume_session": str(resume_session) if resume_session else None,
                "request_key": request.headers.get("Idempotency-Key") or str(uuid.uuid4()),
            },
            request.state.request_id,
        )
    await db.commit()  # Release admission lock before independent checkpoint transactions.
    from app.db.session import Session, tenant_context

    async with Session() as execution, execution.begin():
        await tenant_context(execution, str(ctx.tenant_id))
        return await zoho_sync(
            execution, ctx, identifier, str(resume_session) if resume_session else None
        )


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

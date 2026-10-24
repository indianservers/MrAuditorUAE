"""Operational connector APIs, source qualification, immutable vendor contracts and repair hints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.v1.accounting import serialize
from app.core.config import settings
from app.core.dependencies import DB, Context, require
from app.db.session import tenant_context
from app.modules.accounting.models import Connection, SyncRun
from app.modules.accounting.schemas import Input
from app.modules.accounting.service import scoped
from app.modules.connectors.controls import SourceControl, qualify, reconcile_balances
from app.modules.connectors.models import ConnectorState
from app.modules.connectors.profiles import PartnerProfile
from app.modules.connectors.runtime import digest
from app.modules.connectors.webhooks import verify_quickbooks
from app.modules.connectors.zoho import ConnectorError

router = APIRouter(tags=["Connector operations"])
Manage = Annotated[Context, Depends(require("connectors.manage"))]
Read = Annotated[Context, Depends(require("accounting.read"))]


class Qualification(Input):
    sync_run_id: uuid.UUID
    scenario: str = Field(pattern=r"^(baseline|refund|reversal|cancelled|tax|foreign_currency|opening|year_end|pagination|recovery|amendment|deletion)$")
    control: SourceControl


class Balance(Input):
    account_code: str = Field(min_length=1, max_length=100)
    balance: str = Field(pattern=r"^-?[0-9]+(?:\.[0-9]+)?$", max_length=50)


class BalanceControls(Input):
    sync_run_id: uuid.UUID
    opening_reference: str = Field(min_length=1, max_length=500)
    closing_reference: str = Field(min_length=1, max_length=500)
    opening: list[Balance] = Field(min_length=1, max_length=10000)
    closing: list[Balance] = Field(min_length=1, max_length=10000)


class ZohoPreferences(Input):
    include_documents: bool = False
    include_attachments: bool = False


@router.patch("/connectors/operations/{identifier}/preferences", response_model=dict)
async def preferences(identifier: uuid.UUID, data: ZohoPreferences, db: DB, ctx: Manage):
    connection = await scoped(db, ctx, Connection, identifier, True)
    if connection.provider != "zoho":
        raise HTTPException(422, "These preferences apply to Zoho Books")
    connection.config = {**connection.config, **data.model_dump()}
    return {"status": "preferences_saved", "preferences": data.model_dump()}


@router.post("/connectors/operations/{identifier}/balance-controls", response_model=dict)
async def balance_controls(identifier: uuid.UUID, data: BalanceControls, db: DB, ctx: Manage):
    from app.modules.accounting.models import ImportBatch, ImportFile
    from app.modules.accounting.schemas import ImportOptions
    from app.modules.accounting.service import check_scope
    from app.modules.lineage.storage import ObjectStore, hash_file
    from app.modules.ingestion.parser import normalize, rows

    connection = await scoped(db, ctx, Connection, identifier)
    entity, period = await check_scope(db, ctx, connection)
    run = await scoped(db, ctx, SyncRun, data.sync_run_id)
    if run.connection_id != identifier or run.status != "completed":
        raise HTTPException(422, "A completed extraction for this connection is required")
    batch_id = run.manifest.get("derived_import_batch_ids", {}).get("gl") or run.manifest.get("derived_import_batch_id")
    if not batch_id:
        raise HTTPException(422, "No extracted ledger is available for balance controls")
    batch = await scoped(db, ctx, ImportBatch, uuid.UUID(batch_id))
    source = await db.scalar(select(ImportFile).where(ImportFile.tenant_id == ctx.tenant_id, ImportFile.batch_id == batch.id))
    if not source:
        raise HTTPException(422, "Source ledger evidence is unavailable")
    options = ImportOptions.model_validate(batch.options)
    try:
        with ObjectStore().local(source.object_key, source.object_version) as path:
            if hash_file(path) != source.sha256:
                raise ValueError("Ledger evidence integrity mismatch")
            ledger = (normalize(row, options, period.start_date, period.end_date, entity.functional_currency, index)[0]
                      for index, row in rows(path, source.filename, options))
            result = reconcile_balances(ledger, [v.model_dump() for v in data.opening], [v.model_dump() for v in data.closing])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    state = ConnectorState(tenant_id=ctx.tenant_id, created_by=ctx.user_id, connection_id=identifier,
        namespace="qualification", key=str(uuid.uuid4()), payload={**result, "scenario": "opening_gl_closing",
        "sync_run_id": str(run.id), "opening_reference": data.opening_reference,
        "closing_reference": data.closing_reference, "source_sha256": source.sha256,
        "opening": [v.model_dump() for v in data.opening], "closing": [v.model_dump() for v in data.closing]}, expires_at=None)
    db.add(state)
    await db.flush()
    return serialize(state)


@router.get("/connectors/operations/{identifier}", response_model=dict)
async def health(identifier: uuid.UUID, db: DB, ctx: Manage):
    connection = await scoped(db, ctx, Connection, identifier)
    states = (await db.scalars(select(ConnectorState).where(
        ConnectorState.tenant_id == ctx.tenant_id, ConnectorState.connection_id == identifier,
        ConnectorState.namespace.in_(["session", "event", "qualification", "watermark", "source_revision"]),
    ).order_by(ConnectorState.created_at.desc()).limit(100))).all()
    return {"connection_id": str(identifier), "status": connection.status,
            "live_qualified": False, "records": [serialize(s) for s in states],
            "actions": ["resume_failed_session", "renew_consent", "run_source_controls", "verify_vendor_contract"],
            "credential_storage": "encrypted; never included in diagnostics"}


@router.post("/connectors/operations/{identifier}/qualifications", response_model=dict, status_code=201)
async def qualification(identifier: uuid.UUID, data: Qualification, db: DB, ctx: Manage):
    await scoped(db, ctx, Connection, identifier)
    run = await scoped(db, ctx, SyncRun, data.sync_run_id)
    if run.connection_id != identifier:
        raise HTTPException(422, "Qualification run belongs to another connection")
    result = qualify(serialize(run), data.control, data.scenario)
    state = ConnectorState(tenant_id=ctx.tenant_id, created_by=ctx.user_id,
        connection_id=identifier, namespace="qualification", key=str(uuid.uuid4()),
        payload={**result, "sync_run_id": str(run.id)}, expires_at=None)
    db.add(state)
    await db.flush()
    return serialize(state)


@router.post("/connectors/vendor-profiles", response_model=dict, status_code=201)
async def create_profile(data: PartnerProfile, db: DB, ctx: Manage):
    sealed = data.seal()
    state = ConnectorState(tenant_id=ctx.tenant_id, created_by=ctx.user_id, connection_id=None,
        namespace="profile", key=sealed["contract_hash"], payload=sealed, expires_at=None)
    existing = await db.scalar(select(ConnectorState).where(ConnectorState.tenant_id == ctx.tenant_id,
        ConnectorState.namespace == "profile", ConnectorState.key == state.key))
    if existing:
        return serialize(existing)
    db.add(state)
    await db.flush()
    return serialize(state)


@router.post("/connectors/operations/{identifier}/profile/{profile_id}", response_model=dict)
async def apply_profile(identifier: uuid.UUID, profile_id: uuid.UUID, db: DB, ctx: Manage):
    connection = await scoped(db, ctx, Connection, identifier, True)
    profile = await db.scalar(select(ConnectorState).where(ConnectorState.id == profile_id,
        ConnectorState.tenant_id == ctx.tenant_id, ConnectorState.namespace == "profile"))
    if not profile or profile.payload["provider"] != connection.provider:
        raise HTTPException(422, "A matching tenant-owned vendor profile is required")
    body = dict(profile.payload)
    expected = body.pop("contract_hash")
    if digest(body) != expected:
        raise HTTPException(409, "Vendor contract integrity check failed")
    connection.config = {**body["config"], "profile_id": str(profile_id)}
    connection.status = "profile_configured_pending_qualification"
    return {"status": connection.status, "contract_hash": expected}


@router.post("/connectors/webhooks/quickbooks/{tenant_id}", status_code=202)
async def quickbooks_webhook(tenant_id: uuid.UUID, request: Request, db: DB):
    try:
        events = verify_quickbooks(await request.body(), request.headers.get("intuit-signature", ""),
                                  settings().connector_quickbooks_webhook_token)
    except (ConnectorError, KeyError, TypeError, ValueError):
        raise HTTPException(403, "Webhook signature or envelope is invalid") from None
    await tenant_context(db, str(tenant_id))
    accepted = 0
    for event in events:
        connections = (await db.scalars(select(Connection).where(
            Connection.tenant_id == tenant_id, Connection.provider == "quickbooks",
            Connection.config["company_id"].astext == event["realm_id"],
        ))).all()
        for connection in connections:
            key = digest([str(connection.id), event["key"]])
            result = await db.execute(insert(ConnectorState).values(
                id=uuid.uuid4(), tenant_id=tenant_id, created_by=connection.created_by,
                connection_id=connection.id, namespace="event", key=key,
                payload={**event, "state": "repair_pending", "received_at": datetime.now(UTC).isoformat()},
                expires_at=None,
            ).on_conflict_do_nothing(constraint="uq_connector_state").returning(ConnectorState.id))
            accepted += int(result.scalar_one_or_none() is not None)
    # Processing requires an authorized repair invocation; the anonymous callback
    # cannot acquire arbitrary user permissions or start accounting activation.
    await db.flush()
    return {"accepted": accepted, "status": "repair_hints_recorded"}


@router.post("/connectors/operations/{identifier}/repair", response_model=dict)
async def repair(identifier: uuid.UUID, request: Request, db: DB, ctx: Manage):
    from app.workers.accounting import submit

    connection = await scoped(db, ctx, Connection, identifier)
    if connection.provider != "quickbooks" or connection.config.get("edition", "online") != "online":
        raise HTTPException(422, "CDC repair applies to QuickBooks Online")
    return await submit(db, ctx, "connector.repair", {"connection_id": str(identifier),
        "request_key": request.headers.get("Idempotency-Key") or str(uuid.uuid4())}, request.state.request_id)

"""Quota admission before writing an existing private-store object."""

from fastapi import HTTPException
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.modules.lineage.storage import ObjectStore
from app.modules.saas.models import Subscription, Usage
from app.modules.saas.service import writable


async def baseline(db, tenant):
    from app.modules.connectors.models import ConnectorState
    from app.modules.accounting.models import ImportFile, SyncRun, UploadSession
    from app.modules.audit_execution.models import AuditRecord, EvidenceVersion
    from app.modules.ml.models import MLEvent

    objects = {}

    def collect(value):
        if isinstance(value, dict):
            if {"object_key", "object_version", "size"} <= value.keys():
                objects[(value["object_key"], value["object_version"])] = int(value["size"])
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    for model in (ImportFile, EvidenceVersion):
        rows = (
            await db.execute(
                select(model.object_key, model.object_version, model.size).where(
                    model.tenant_id == tenant
                )
            )
        ).all()
        for key, version, size in rows:
            objects[(key, version)] = size
    from typing import Any

    sources: list[tuple[Any, Any]] = [
        (ConnectorState, ConnectorState.payload),
        (SyncRun, SyncRun.manifest),
        (UploadSession, UploadSession.chunks),
        (AuditRecord, AuditRecord.body),
        (MLEvent, MLEvent.body),
    ]
    for scoped_model, column in sources:
        for value in (
            await db.scalars(select(column).where(scoped_model.tenant_id == tenant))
        ).all():
            collect(value)
    return sum(objects.values())


async def put_private(db, ctx, stream):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"),
        {"key": str(ctx.tenant_id)},
    )
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == ctx.tenant_id))
    if not sub and settings().environment == "production":
        raise HTTPException(403, "Subscription provisioning required")
    if sub:
        if not writable(sub):
            raise HTTPException(403, "Subscription is read-only")
        position = stream.tell()
        stream.seek(0, 2)
        size = stream.tell() - position
        stream.seek(position)
        counter = await db.scalar(
            select(Usage).where(
                Usage.tenant_id == ctx.tenant_id,
                Usage.period == "lifetime",
                Usage.metric == "storage_bytes",
            )
        )
        if not counter:
            counter = Usage(
                tenant_id=ctx.tenant_id,
                created_by=None,
                period="lifetime",
                metric="storage_bytes",
                quantity=await baseline(db, ctx.tenant_id),
            )
            db.add(counter)
        if counter.quantity + size > sub.limits["storage_bytes"]:
            raise HTTPException(413, "Tenant storage allowance exhausted")
        counter.quantity += size
        await db.flush()
    return await run_in_threadpool(ObjectStore().put, str(ctx.tenant_id), stream)

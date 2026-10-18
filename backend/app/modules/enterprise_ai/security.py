import hashlib
import json
import uuid
from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.db.models.platform import Engagement, Tenant
from app.modules.audit_execution import service as audit
from app.modules.audit_execution.access import engagement_permissions


def serial(value):
    return jsonable_encoder(value, custom_encoder={Decimal: str})


def digest(value):
    return hashlib.sha256(
        json.dumps(serial(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def scope(db, ctx, eid, permission="ai.investigation.read"):
    # Authorization precedes the resource lookup, preventing existence probing.
    await engagement_permissions(db, ctx, eid, permission)
    if permission in {"ai.workflow.run", "ai.workflow.schedule", "ai.approval.execute"}:
        from app.modules.saas.service import background_allowed

        await background_allowed(db, ctx.tenant_id, "ai")
    tenant = await db.get(Tenant, ctx.tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(403, "Active tenant required")
    eng = await db.scalar(
        select(Engagement).where(Engagement.tenant_id == ctx.tenant_id, Engagement.id == eid)
    )
    if not eng:
        raise HTTPException(404, "Resource unavailable")
    return eng


async def source(db, ctx, eid, rid):
    from app.modules.audit_execution.models import AuditRecord

    await scope(db, ctx, eid)

    # Each specialist source is read through its existing resource service.
    obj = await db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant_id == ctx.tenant_id,
            AuditRecord.engagement_id == eid,
            AuditRecord.id == rid,
        )
    )
    if not obj:
        raise HTTPException(404, "Resource unavailable")
    prefix = obj.kind.split("-")[0]
    if prefix in {"ifrs", "tax", "vat", "tp", "grc"}:
        module = __import__(f"app.modules.{prefix}.service", fromlist=["record"])
        obj = await module.record(db, ctx, eid, rid, approved=True)
    elif prefix == "dmtt":
        from app.modules.dmtt.service import record

        obj = await record(db, ctx, eid, rid, obj.kind.removeprefix("dmtt-"))
    else:
        obj = await audit.get_record(db, ctx, eid, rid)
        if obj.status not in {"APPROVED", "LOCKED"}:
            raise HTTPException(409, "Approved source required")
    if obj.kind.startswith("tp-"):
        from app.modules.tp import service as tp

        pid = obj.id if obj.kind == "tp-profile" else uuid.UUID(obj.body["profile_id"])
        graph, _ = await tp.record_graph(db, ctx, eid, [(obj.id, None)], pid)
        for dependency in graph:
            if dependency.kind == "tp-dataset":
                await tp.licensed_dataset(db, ctx, eid, dependency.id, pid, ai=True)
    return obj


async def validate_dependencies(db, ctx, eid, deps):
    for item in deps:
        if item.get("type", "record") == "record":
            obj = await source(db, ctx, eid, uuid.UUID(item["id"]))
            if obj.version != item["version"]:
                raise HTTPException(409, "Source changed; create a fresh investigation")
        elif item["type"] == "chunk":
            from app.modules.enterprise_ai.documents import authorized_chunk

            await authorized_chunk(db, ctx, eid, uuid.UUID(item["id"]))
        elif item["type"] == "journal":
            from app.modules.enterprise_ai.tools import journal_source

            await journal_source(db, ctx, eid, uuid.UUID(item["id"]))
        elif item["type"] == "snapshot":
            from app.modules.enterprise_ai.tools import snapshot_source

            obj = await snapshot_source(db, ctx, eid, uuid.UUID(item["id"]))
            if item.get("sha256") != obj.sha256:
                raise HTTPException(409, "Financial source integrity differs")
        elif item["type"] == "ml":
            from app.modules.ml.service import get

            obj = await get(db, ctx, uuid.UUID(item["id"]))
            if obj.engagement_id != eid:
                raise HTTPException(404, "Resource unavailable")
        elif item["type"] == "run":
            from app.modules.enterprise_ai.tools import calculation_source

            await calculation_source(db, ctx, eid, item["module"], uuid.UUID(item["id"]))
        else:
            raise HTTPException(422, "Unsupported citation type")

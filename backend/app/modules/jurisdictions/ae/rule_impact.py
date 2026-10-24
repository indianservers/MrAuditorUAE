"""Authorized, bounded rule-reference impact graph; no rule is applied automatically."""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution.models import AuditRecord
from app.modules.enterprise_ai.security import digest
from app.modules.intelligence.models import IntelligenceEvent


def identifiers(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from identifiers(item)
    elif isinstance(value, list):
        for item in value:
            yield from identifiers(item)
    elif isinstance(value, str):
        try:
            yield str(uuid.UUID(value))
        except ValueError:
            pass


async def population(db, ctx, eid):
    from app.modules.audit_execution.service import get_record
    from app.modules.ifrs import service as ifrs
    from app.modules.ifrs.models import CalculationRun
    from app.modules.intelligence.service import event
    from app.modules.tax import service as tax
    from app.modules.tax.models import TaxRun
    from app.modules.tp import service as tp
    from app.modules.tp.models import TPRun
    from app.modules.vat import service as vat
    from app.modules.vat.models import VATRun

    nodes = []

    async def permitted(call):
        try:
            return await call
        except HTTPException as exc:
            if exc.status_code in {403, 404, 409}:
                return None
            raise

    records = (
        await db.scalars(
            select(AuditRecord)
            .where(AuditRecord.tenant_id == ctx.tenant_id, AuditRecord.engagement_id == eid)
            .order_by(AuditRecord.id)
            .limit(1001)
        )
    ).all()
    if len(records) > 1000:
        raise HTTPException(422, "Impact scan exceeds 1000 records; qualified queued scan required")
    for row in records:
        if not await permitted(get_record(db, ctx, eid, row.id, lock=False)):
            continue
        nodes.append(
            dict(
                id=str(row.id),
                type="record",
                version=row.version,
                label=row.reference,
                refs=set(identifiers(row.body)),
            )
        )
    events = (
        await db.scalars(
            select(IntelligenceEvent)
            .where(
                IntelligenceEvent.tenant_id == ctx.tenant_id, IntelligenceEvent.engagement_id == eid
            )
            .order_by(IntelligenceEvent.id)
            .limit(1001)
        )
    ).all()
    if len(events) > 1000:
        raise HTTPException(422, "Impact scan exceeds 1000 retained events")
    for row in events:
        if row.kind == "business-action" and row.body.get("action") == "rule-impact":
            continue
        if not await permitted(event(db, ctx, eid, row.id)):
            continue
        nodes.append(
            dict(
                id=str(row.id),
                type="event",
                version=row.version,
                label=row.kind,
                refs=set(identifiers(row.dependencies)),
            )
        )
    engines: list[tuple[Any, str, Any]] = [
        (CalculationRun, "ifrs", ifrs.run),
        (TaxRun, "tax", tax.run),
        (VATRun, "vat", vat.run),
        (TPRun, "tp", tp.get_run),
    ]
    for model, family, getter in engines:
        runs = (
            await db.scalars(
                select(model)
                .where(model.tenant_id == ctx.tenant_id, model.engagement_id == eid)
                .order_by(model.id)
                .limit(501)
            )
        ).all()
        if len(runs) > 500:
            raise HTTPException(422, "Impact scan exceeds 500 runs per specialist")
        for row in runs:
            if not await permitted(getter(db, ctx, eid, row.id)):
                continue
            refs = set(identifiers(row.dependencies))
            refs.add(str(row.record_id))
            nodes.append(
                dict(id=str(row.id), type=family, version=row.sha256, label=row.kind, refs=refs)
            )
    return nodes


async def fingerprint(db, ctx, eid):
    nodes = await population(db, ctx, eid)
    return digest([{**n, "refs": sorted(n["refs"])} for n in nodes])


async def assess(db, ctx, eid, schedule):
    nodes = await population(db, ctx, eid)
    roots = {r["old_source_id"] for r in schedule.rows}
    affected = set(roots)
    for _ in range(100):
        added = {n["id"] for n in nodes if n["refs"] & affected} - affected
        if not added:
            break
        affected |= added
    else:
        raise HTTPException(422, "Rule impact graph exceeds 100 propagation levels")
    return dict(
        engine="verified-rule-reference-impact/1",
        scope="CURRENT_AUTHORIZED_ENGAGEMENT_ONLY",
        affected_items=[
            {k: v for k, v in n.items() if k != "refs"}
            for n in nodes
            if n["id"] in affected and n["id"] not in roots
        ],
        population_sha256=digest([{**n, "refs": sorted(n["refs"])} for n in nodes]),
        access_filtered=True,
        rule_applied=False,
        implementation_tasks="Prepare independently reviewed tasks through the controlled review-task action",
        professional_conclusion=None,
    )

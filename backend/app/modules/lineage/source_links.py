"""Reject prospective source cycles before a paper becomes unreadable."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.audit_execution.models import AuditRecord
from app.modules.intelligence.models import IntelligenceEvent


async def acyclic_paper_links(db, ctx, eid, record_id, sources):
    if not record_id:
        return
    queue = [
        ("record" if s.kind == "record" else "event", s.id)
        for s in sources
        if s.kind in {"record", "intelligence"}
    ]
    seen = set()
    while queue:
        kind, identifier = queue.pop()
        if kind == "record" and identifier == record_id:
            raise HTTPException(422, "Source links would create a working-paper cycle")
        if (kind, identifier) in seen:
            continue
        seen.add((kind, identifier))
        if len(seen) > 2000:
            raise HTTPException(422, "Source graph exceeds the bounded 2000-node write check")
        model = AuditRecord if kind == "record" else IntelligenceEvent
        item = await db.scalar(
            select(model).where(
                model.tenant_id == ctx.tenant_id, model.engagement_id == eid, model.id == identifier
            )
        )
        if not item:
            continue  # Normal source authorization/validation rejects unavailable references.
        if kind == "record":
            queue.extend(
                ("record" if r["kind"] == "record" else "event", uuid.UUID(str(r["id"])))
                for r in item.body.get("sources", [])
                if r["kind"] in {"record", "intelligence"}
            )
        else:
            queue.extend(
                ("record" if r["type"] == "record" else "event", uuid.UUID(str(r["id"])))
                for r in item.dependencies
                if r["type"] in {"record", "event"}
            )

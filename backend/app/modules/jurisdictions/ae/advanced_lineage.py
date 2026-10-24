"""Transaction-local, idempotent in-app source-change alerts for advanced schedules."""

import uuid

from sqlalchemy import select, text

from app.modules.audit_execution.models import AuditRecord
from app.modules.intelligence.models import IntelligenceEvent


async def source_changed(db, ctx, changed, request_id):
    from app.db.models.platform import Engagement
    from app.modules.intelligence.service import append

    # Scan a bounded engagement graph; ordinary intermediate workpapers are traversed too.
    papers = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == changed.engagement_id,
                AuditRecord.kind == "working-papers",
                AuditRecord.status != "ARCHIVED",
            )
            .limit(2001)
        )
    ).all()
    if not any(p.body.get("advanced_input") for p in papers):
        return
    if len(papers) > 2000:
        # Fail closed: a truncated scan must not masquerade as complete propagation.
        from fastapi import HTTPException

        raise HTTPException(
            409,
            "Advanced lineage exceeds 2000 papers; qualified queued impact scan required before this source change",
        )
    affected = {str(changed.id)}
    targets = []
    for _ in range(100):
        added = []
        for p in papers:
            if str(p.id) in affected:
                continue
            if any(
                str(s.get("id")) in affected
                for s in p.body.get("sources", [])
                if s.get("kind") in {"record", "finding"}
            ):
                added.append(p)
        if not added:
            break
        for p in added:
            affected.add(str(p.id))
            if p.body.get("advanced_input"):
                targets.append(p)
    else:
        from fastapi import HTTPException

        raise HTTPException(
            409, "Advanced lineage depth exceeds 100; resolve before changing this source"
        )
    eng = await db.get(Engagement, changed.engagement_id)
    for paper in targets:
        key = f"advanced-source:{changed.id}:{changed.version}:{paper.id}"
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": str(ctx.tenant_id) + key},
        )
        exists = await db.scalar(
            select(IntelligenceEvent.id).where(
                IntelligenceEvent.tenant_id == ctx.tenant_id,
                IntelligenceEvent.engagement_id == eng.id,
                IntelligenceEvent.kind == "advanced-source-alert",
                IntelligenceEvent.body["dedup_key"].astext == key,
            )
        )
        if exists:
            continue
        recipients = {str(paper.prepared_by), *paper.body.get("review_approvers", [])}
        if paper.body.get("owner_id"):
            recipients.add(paper.body["owner_id"])
        await append(
            db,
            ctx,
            eng,
            "advanced-source-alert",
            dict(
                dedup_key=key,
                use_case_id=paper.body["advanced_input"]["use_case_id"],
                target_id=str(paper.id),
                changed_source_id=str(changed.id),
                changed_source_version=changed.version,
                recipient_ids=sorted(recipients),
                reason="SOURCE_CHANGED_REASSESS_AND_REAPPROVE",
                delivery="IN_APP_CASE_INBOX",
                previous_approved_version_preserved=True,
                automatic_source_value_replacement=False,
            ),
            [],
            request_id,
        )


async def inbox(db, ctx, eid, case_id):
    from app.modules.audit_execution.service import get_record

    rows = (
        await db.scalars(
            select(IntelligenceEvent)
            .where(
                IntelligenceEvent.tenant_id == ctx.tenant_id,
                IntelligenceEvent.engagement_id == eid,
                IntelligenceEvent.kind == "advanced-source-alert",
                IntelligenceEvent.body["use_case_id"].astext == str(case_id),
            )
            .order_by(IntelligenceEvent.created_at.desc())
            .limit(100)
        )
    ).all()
    out = []
    for row in rows:
        if str(ctx.user_id) not in row.body["recipient_ids"]:
            continue
        await get_record(db, ctx, eid, uuid.UUID(row.body["target_id"]), lock=False)
        out.append(dict(id=str(row.id), created_at=row.created_at.isoformat(), **row.body))
    return {"items": out, "channel": "IN_APP_CASE_INBOX", "email_or_push_delivered": False}

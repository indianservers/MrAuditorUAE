import uuid

from sqlalchemy import select, text

from app.modules.grc.models import GRCRun
from app.modules.grc.service import dependency, run


async def assigned(db, ctx, paper):
    if paper.kind == "grc-obligation" and not paper.body.get("notifications_enabled"):
        return
    if paper.kind not in {
        "grc-remediation",
        "grc-alert-decision",
        "grc-deficiency",
        "grc-obligation",
    } or not paper.body.get("owner_id"):
        return
    key = f"grc-assignment:{paper.id}:{paper.version}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(ctx.tenant_id) + key},
    )
    if await db.scalar(
        select(GRCRun.id).where(
            GRCRun.tenant_id == ctx.tenant_id,
            GRCRun.engagement_id == paper.engagement_id,
            GRCRun.kind == "notification",
            GRCRun.inputs["key"].astext == key,
        )
    ):
        return
    await run(
        db,
        ctx,
        paper.engagement_id,
        "notification",
        {"key": key},
        {
            "recipient_id": str(uuid.UUID(paper.body["owner_id"])),
            "reason": "approved_assignment",
            "reference": paper.reference,
            "title": paper.title,
            "due_date": paper.body.get("extension_deadline")
            or paper.body.get("deadline")
            or paper.body.get("target_date", paper.body.get("due_date")),
            "read_requires_current_resource_authorization": True,
        },
        [dependency(paper)],
        paper.id,
    )


async def compliance_reminders(db, ctx, eid, today):
    from datetime import date

    from app.modules.audit_execution.models import AuditRecord
    from app.modules.grc import service
    from app.modules.grc.deadlines import local_today
    from app.modules.lineage.working_papers import freshness

    papers = (
        await db.scalars(
            select(AuditRecord)
            .where(
                AuditRecord.tenant_id == ctx.tenant_id,
                AuditRecord.engagement_id == eid,
                AuditRecord.kind == "grc-obligation",
                AuditRecord.status.in_(["APPROVED", "LOCKED"]),
            )
            .order_by(AuditRecord.id)
            .limit(200)
        )
    ).all()
    count = 0
    for paper in papers:
        await service.authorize_record(db, ctx, paper)
        body = paper.body
        due = body.get("extension_deadline") or body.get("deadline")
        if (
            not body.get("notifications_enabled")
            or (
                isinstance(body.get("jurisdiction_scope"), dict)
                and body["jurisdiction_scope"].get("applicability") != "assessed_applicable"
            )
            or not due
            or body.get("filing_stage") in {"submitted", "acknowledged"}
            or await freshness(db, ctx, paper) != "CURRENT"
        ):
            continue
        scoped_today = local_today(body) if body.get("deadline_rule") else today
        days = (date.fromisoformat(due) - scoped_today).days
        escalated = (
            body.get("escalation_after_days") is not None and days <= -body["escalation_after_days"]
        )
        if days not in body.get("reminder_days", []) and not escalated:
            continue
        recipient = body.get("reviewer_id") if escalated else body["owner_id"]
        if not recipient:
            continue
        key = f"compliance:{paper.id}:{paper.version}:{scoped_today}:{recipient}"
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": str(ctx.tenant_id) + key},
        )
        if await db.scalar(
            select(GRCRun.id).where(
                GRCRun.tenant_id == ctx.tenant_id,
                GRCRun.engagement_id == eid,
                GRCRun.kind == "notification",
                GRCRun.inputs["key"].astext == key,
            )
        ):
            continue
        await run(
            db,
            ctx,
            eid,
            "notification",
            {"key": key},
            {
                "recipient_id": recipient,
                "reason": "compliance_escalation" if escalated else "compliance_reminder",
                "reference": paper.reference,
                "due_date": due,
                "channel": "in_app",
                "delivery_status": "RECORDED_IN_APP",
                "external_delivery": False,
                "read_requires_current_resource_authorization": True,
            },
            [dependency(paper)],
            paper.id,
        )
        count += 1
    return {"recorded": count, "channel": "in_app", "external_messages_sent": 0}

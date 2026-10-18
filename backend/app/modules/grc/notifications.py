import uuid

from sqlalchemy import select, text

from app.modules.grc.models import GRCRun
from app.modules.grc.service import dependency, run


async def assigned(db, ctx, paper):
    if paper.kind not in {
        "grc-remediation",
        "grc-alert-decision",
        "grc-deficiency",
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
            "due_date": paper.body.get("target_date", paper.body.get("due_date")),
            "read_requires_current_resource_authorization": True,
        },
        [dependency(paper)],
        paper.id,
    )

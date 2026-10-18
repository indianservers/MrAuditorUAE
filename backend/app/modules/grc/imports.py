"""Create monitoring outbox entries atomically with a committed accounting import."""

import hashlib

from sqlalchemy import select

from app.db.models.platform import BackgroundJob, Engagement
from app.modules.audit_execution.models import AuditRecord


async def enqueue(db, batch):
    if batch.kind not in {"gl", "journals"}:
        return
    from app.modules.accounting.models import ImportSnapshot

    snapshot = await db.scalar(
        select(ImportSnapshot).where(
            ImportSnapshot.tenant_id == batch.tenant_id, ImportSnapshot.batch_id == batch.id
        )
    )
    if not snapshot:
        return
    rules = (
        await db.scalars(
            select(AuditRecord)
            .join(Engagement, Engagement.id == AuditRecord.engagement_id)
            .where(
                AuditRecord.tenant_id == batch.tenant_id,
                Engagement.tenant_id == batch.tenant_id,
                Engagement.entity_id == batch.entity_id,
                Engagement.period_id == batch.period_id,
                AuditRecord.kind == "grc-monitor-rule",
                AuditRecord.status.in_(["APPROVED", "LOCKED"]),
                AuditRecord.body["trigger_on_import"].as_boolean().is_(True),
                AuditRecord.body["input_kind"].astext == "ledger",
            )
        )
    ).all()
    for rule in rules:
        key = (
            "grc-import:"
            + hashlib.sha256(f"{rule.id}:{rule.version}:{snapshot.id}".encode()).hexdigest()
        )
        if await db.scalar(
            select(BackgroundJob.id).where(
                BackgroundJob.tenant_id == batch.tenant_id, BackgroundJob.idempotency_key == key
            )
        ):
            continue
        db.add(
            BackgroundJob(
                tenant_id=batch.tenant_id,
                created_by=rule.prepared_by,
                job_type="grc.monitor",
                idempotency_key=key,
                payload={
                    "engagement_id": str(rule.engagement_id),
                    "rule_id": str(rule.id),
                    "version": rule.version,
                    "snapshot_override_id": str(snapshot.id),
                    "trigger": "committed-import",
                },
            )
        )

"""Tenant-scoped schedule dispatcher with a durable, recoverable job outbox."""

import asyncio
import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.platform import BackgroundJob, Tenant
from app.db.session import tenant_context
from app.modules.audit_execution.models import AuditRecord
from app.modules.grc.calculations import next_due
from app.modules.grc.models import MonitorSchedule
from app.workers.accounting import work
from app.workers.celery_app import celery_app


async def dispatch():
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    queued = 0
    try:
        async with factory() as db:
            tenants = (await db.scalars(select(Tenant.id).where(Tenant.status == "active"))).all()
        for tenant in tenants:
            async with factory() as db, db.begin():
                await tenant_context(db, str(tenant))
                now = datetime.now(UTC)
                schedules = (
                    await db.scalars(
                        select(MonitorSchedule)
                        .where(
                            MonitorSchedule.tenant_id == tenant,
                            MonitorSchedule.active.is_(True),
                            MonitorSchedule.next_due <= now,
                        )
                        .order_by(MonitorSchedule.next_due)
                        .limit(100)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for schedule in schedules:
                    rule = await db.scalar(
                        select(AuditRecord).where(
                            AuditRecord.tenant_id == tenant,
                            AuditRecord.id == schedule.rule_id,
                            AuditRecord.engagement_id == schedule.engagement_id,
                            AuditRecord.kind == "grc-monitor-rule",
                        )
                    )
                    if (
                        not rule
                        or rule.status not in {"APPROVED", "LOCKED"}
                        or rule.version != schedule.rule_version
                        or not schedule.created_by
                    ):
                        schedule.active = False
                        continue
                    occurrence = schedule.next_due.isoformat()
                    key = (
                        "grc-schedule:"
                        + hashlib.sha256(f"{schedule.id}:{occurrence}".encode()).hexdigest()
                    )
                    job = await db.scalar(
                        select(BackgroundJob).where(
                            BackgroundJob.tenant_id == tenant, BackgroundJob.idempotency_key == key
                        )
                    )
                    if not job:
                        job = BackgroundJob(
                            tenant_id=tenant,
                            created_by=schedule.created_by,
                            job_type="grc.monitor",
                            idempotency_key=key,
                            payload={
                                "engagement_id": str(schedule.engagement_id),
                                "rule_id": str(rule.id),
                                "version": rule.version,
                                "schedule_id": str(schedule.id),
                                "occurrence": occurrence,
                            },
                        )
                        db.add(job)
                        await db.flush()
                    schedule.last_job_id = job.id
                    due = next_due(schedule.next_due, schedule.frequency)
                    while due <= now:
                        due = next_due(due, schedule.frequency)
                    schedule.next_due = due
            # Dispatch after commit. Broker failures leave the same pending job recoverable.
            async with factory() as db, db.begin():
                await tenant_context(db, str(tenant))
                pending = (
                    await db.scalars(
                        select(BackgroundJob)
                        .where(
                            BackgroundJob.tenant_id == tenant,
                            BackgroundJob.job_type == "grc.monitor",
                            BackgroundJob.status == "pending",
                        )
                        .order_by(BackgroundJob.created_at)
                        .limit(100)
                    )
                ).all()
                for job in pending:
                    if job.created_by:
                        work.apply_async(
                            args=[str(job.id), str(tenant), str(job.created_by)],
                            task_id=str(job.id),
                            queue="grc",
                        )
                        queued += 1
        return {"dispatched": queued}
    finally:
        await engine.dispose()


@celery_app.task(name="auditos.grc.tick", soft_time_limit=50, time_limit=55)
def tick():
    return asyncio.run(dispatch())

"""One transaction per step. Broker redelivery resumes stored receipts."""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.dependencies import Context
from app.db.session import tenant_context
from app.modules.enterprise_ai import service
from app.workers.celery_app import celery_app


async def process(tenant, user, eid, identifier):
    engine = create_async_engine(settings().database_url)
    session = async_sessionmaker(engine, expire_on_commit=False)
    ctx = Context(uuid.UUID(user), uuid.UUID(tenant), frozenset())
    try:
        for _ in range(12):
            async with session() as db, db.begin():
                await tenant_context(db, tenant)
                from sqlalchemy import text

                await db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 12))"),
                    {"key": tenant},
                )
                # Reconstruct current permissions, never use caller-serialized permissions.
                from app.modules.audit_execution.access import engagement_permissions

                permissions, _ = await engagement_permissions(
                    db, ctx, uuid.UUID(eid), "ai.workflow.run"
                )
                ctx = Context(ctx.user_id, ctx.tenant_id, permissions)
                run = await service.step(db, ctx, uuid.UUID(eid), uuid.UUID(identifier))
                state = run.state
            if state in service.TERMINAL | {"PAUSED", "WAITING_FOR_APPROVAL"}:
                return {"id": identifier, "state": state}
        return {"id": identifier, "state": "LIMIT_REACHED"}
    except Exception as exc:
        from fastapi import HTTPException
        from sqlalchemy import select

        from app.modules.enterprise_ai.models import Workflow

        if not isinstance(exc, HTTPException) or exc.status_code not in {403, 404, 409}:
            raise
        # A revoked assignment/stale source must not produce an endless outbox retry.
        # Reopen a transaction after the denied step rolled back, without reading sources.
        async with session() as db, db.begin():
            await tenant_context(db, tenant)
            run = await db.scalar(
                select(Workflow)
                .where(
                    Workflow.id == uuid.UUID(identifier),
                    Workflow.tenant_id == ctx.tenant_id,
                    Workflow.created_by == ctx.user_id,
                    Workflow.engagement_id == uuid.UUID(eid),
                )
                .with_for_update()
            )
            if run and run.state not in service.TERMINAL:
                run.state = "FAILED"
                await service.event(
                    db,
                    ctx,
                    run,
                    "worker.authorization-stopped",
                    "stopped",
                    {"category": "AUTHORIZATION_OR_SOURCE_CHANGED", "status": exc.status_code},
                )
        return {"id": identifier, "state": "FAILED"}
    finally:
        await engine.dispose()


@celery_app.task(
    name="auditos.enterprise_ai.work", acks_late=True, soft_time_limit=1000, time_limit=1100
)
def work(tenant, user, eid, identifier):
    return asyncio.run(process(tenant, user, eid, identifier))


async def dispatch_due():
    from datetime import UTC, datetime

    from fastapi import HTTPException
    from sqlalchemy import select

    from app.db.models.platform import Tenant
    from app.modules.audit_execution.access import engagement_permissions
    from app.modules.enterprise_ai.models import Event, Schedule, Workflow
    from app.modules.enterprise_ai.schemas import Command
    from app.modules.enterprise_ai.security import digest
    from app.modules.grc.calculations import next_due

    engine = create_async_engine(settings().database_url)
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
                        select(Schedule)
                        .where(
                            Schedule.tenant_id == tenant,
                            Schedule.active.is_(True),
                            Schedule.next_due <= now,
                        )
                        .order_by(Schedule.next_due)
                        .limit(100)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for schedule in schedules:
                    if schedule.created_by is None:
                        schedule.active = False
                        continue
                    ctx = Context(schedule.created_by, tenant, frozenset())
                    try:
                        async with db.begin_nested():
                            permissions, _ = await engagement_permissions(
                                db, ctx, schedule.engagement_id, "ai.workflow.schedule"
                            )
                            ctx = Context(ctx.user_id, tenant, permissions)
                            key = "schedule:" + digest(
                                {"id": str(schedule.id), "due": schedule.next_due.isoformat()}
                            )
                            run = await service.create(
                                db,
                                ctx,
                                Command(
                                    engagement_id=schedule.engagement_id,
                                    task=schedule.task,
                                    prompt="Explicitly authorized scheduled source collection",
                                    idempotency_key=key,
                                    inputs=schedule.inputs,
                                ),
                            )
                            await service.event(
                                db,
                                ctx,
                                run,
                                "queued",
                                "queued",
                                {
                                    "schedule_id": str(schedule.id),
                                    "occurrence": schedule.next_due.isoformat(),
                                },
                            )
                    except HTTPException:
                        schedule.active = False
                        continue
                    due = next_due(schedule.next_due, schedule.frequency)
                    while due <= now:
                        due = next_due(due, schedule.frequency)
                    schedule.next_due = due
            # Only explicitly queued workflows are dispatched. Unsubmitted plans
            # never cause confidential background reads.
            async with factory() as db, db.begin():
                await tenant_context(db, str(tenant))
                runs = (
                    await db.scalars(
                        select(Workflow)
                        .join(Event, Event.run_id == Workflow.id)
                        .where(
                            Workflow.tenant_id == tenant,
                            Event.tenant_id == tenant,
                            Event.key == "queued",
                            Workflow.state.in_(["CREATED", "RUNNING", "RESUMING"]),
                        )
                        .order_by(Workflow.created_at)
                        .limit(100)
                    )
                ).all()
                for run in runs:
                    try:
                        work.apply_async(
                            args=[
                                str(tenant),
                                str(run.created_by),
                                str(run.engagement_id),
                                str(run.id),
                            ],
                            queue="enterprise-ai",
                        )
                        queued += 1
                    except Exception:
                        break
        return {"queued": queued}
    finally:
        await engine.dispose()


@celery_app.task(name="auditos.enterprise_ai.tick", soft_time_limit=50, time_limit=60)
def tick():
    return asyncio.run(dispatch_due())

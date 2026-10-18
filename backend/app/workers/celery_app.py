from celery import Celery
from celery.signals import beat_init, worker_init

from app.core.config import settings

celery_app = Celery(
    "auditos",
    broker=settings().redis_url,
    include=[
        "app.workers.tasks",
        "app.workers.accounting",
        "app.workers.grc",
        "app.workers.enterprise_ai",
    ],
)
celery_app.conf.update(
    beat_schedule={
        "grc-due-schedules": {"task": "auditos.grc.tick", "schedule": 60.0},
        "ai-due-schedules": {"task": "auditos.enterprise_ai.tick", "schedule": 60.0},
    },
    task_routes={
        "auditos.grc.tick": {"queue": "grc"},
        "auditos.enterprise_ai.tick": {"queue": "enterprise-ai"},
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=30,
    task_time_limit=40,
)


async def production_readiness():
    from app.api.v1.health import ready
    from app.db.session import engine

    try:
        await ready()
    finally:
        await engine.dispose()


@worker_init.connect
@beat_init.connect
def enforce_production_readiness(**kwargs):
    if settings().environment != "production":
        return
    import asyncio

    try:
        asyncio.run(production_readiness())
    except Exception:
        # Signal dispatch catches ordinary Exceptions. Stop before consumption.
        raise SystemExit(78) from None

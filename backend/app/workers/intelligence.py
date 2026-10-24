import asyncio

from app.workers.celery_app import celery_app


@celery_app.task(
    name="auditos.intelligence.run",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=200,
)
def run(identifier, tenant):
    from app.modules.intelligence.jobs import process

    asyncio.run(process(identifier, tenant))


@celery_app.task(name="auditos.intelligence.recover", soft_time_limit=30, time_limit=40)
def recover():
    from app.modules.intelligence.jobs import recover_due

    return asyncio.run(recover_due())

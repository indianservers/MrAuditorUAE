from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "auditos", broker=settings().redis_url, include=["app.workers.tasks", "app.workers.accounting"]
)
celery_app.conf.update(
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

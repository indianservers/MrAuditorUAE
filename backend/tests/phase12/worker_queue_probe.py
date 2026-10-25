"""Explicitly imported only by the isolated, test-environment queue probe."""

import json
import re

from redis import Redis

from app.core.config import settings
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="auditos.qa.worker_queue_probe")
def probe(self, run_id, expected_queue):
    if settings().environment != "test" or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise RuntimeError("Queue probes require an isolated test environment")
    actual = self.request.delivery_info.get("routing_key")
    client = Redis.from_url(settings().redis_url)
    try:
        client.rpush(
            f"qa:worker-queues:{run_id}",
            json.dumps(
                {
                    "expected_queue": expected_queue,
                    "routing_key": actual,
                    "matches": actual == expected_queue,
                }
            ),
        )
    finally:
        client.close()

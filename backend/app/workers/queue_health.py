"""Worker health requires consumers for every configured route and default queue."""

import argparse
import json
import socket
from collections.abc import Mapping

from kombu.exceptions import OperationalError


def required_queues(routes, default_queue):
    if not isinstance(default_queue, str) or not default_queue:
        raise ValueError("An explicit default queue is required")
    if not isinstance(routes, Mapping):
        raise TypeError("Dynamic task routers require separate subscription assessment")
    queues = {default_queue}
    for options in routes.values():
        if not isinstance(options, Mapping):
            raise TypeError("Unsupported dynamic task route")
        queue = options.get("queue", default_queue)
        if not isinstance(queue, str) or not queue.strip():
            raise ValueError("Task route has no explicit supported queue")
        queues.add(queue)
    return queues


def inspect_worker(application, node, timeout=3):
    try:
        required = required_queues(
            application.conf.task_routes, application.conf.task_default_queue
        )
        active = application.control.inspect(destination=[node], timeout=timeout).active_queues()
        if not isinstance(active, Mapping) or node not in active:
            return {
                "status": "FAIL",
                "reason": "WORKER_NOT_REACHABLE",
                "required_queues": sorted(required),
                "missing_queues": sorted(required),
            }
        subscribed = {item["name"] for item in active[node]}
        if any(not isinstance(name, str) for name in subscribed):
            raise ValueError("Malformed worker subscription response")
        missing = required - subscribed
        return {
            "status": "FAIL" if missing else "PASS",
            "reason": "SUBSCRIPTION_MISSING" if missing else "REQUIRED_QUEUES_ACTIVE",
            "required_queues": sorted(required),
            "subscribed_queues": sorted(subscribed),
            "missing_queues": sorted(missing),
        }
    except (ValueError, TypeError, KeyError, OSError, OperationalError):
        return {"status": "FAIL", "reason": "QUEUE_HEALTH_UNVERIFIED"}


def main():
    from app.workers.celery_app import celery_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="celery@" + socket.gethostname())
    parser.add_argument("--timeout", type=float, default=3)
    args = parser.parse_args()
    if not 0 < args.timeout <= 5:
        parser.error("Queue health reply timeout must be between zero and five seconds")
    result = inspect_worker(celery_app, args.node, args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

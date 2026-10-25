"""Check explicit deployment subscriptions against the configured Celery routes."""

import argparse
import json
import sys
from pathlib import Path


def required_queues(routes, default_queue):
    from app.workers.queue_health import required_queues as configured_queues

    return configured_queues(routes, default_queue)


def consumer_queues(command):
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(value, str) for value in command)
        or command[0] != "celery"
        or "worker" not in command
    ):
        raise ValueError("Worker must use an explicit Celery argument array")
    selected = []
    for index, value in enumerate(command):
        if value in {"-X", "--exclude-queues"} or value.startswith("--exclude-queues="):
            raise ValueError(
                "Queue exclusions require separate subscription assessment"
            )
        if value in {"-Q", "--queues"}:
            if index + 1 >= len(command):
                raise ValueError("Worker queue option has no value")
            selected.append(command[index + 1])
        elif value.startswith("--queues="):
            selected.append(value.split("=", 1)[1])
    if len(selected) != 1:
        raise ValueError("Declare exactly one worker subscription list")
    names = selected[0].split(",")
    if (
        not names
        or any(
            not name or name != name.strip() or name.startswith("-") for name in names
        )
        or len(set(names)) != len(names)
    ):
        raise ValueError("Worker subscriptions must be distinct explicit queue names")
    return set(names)


def assess(command, routes, default_queue):
    needed = required_queues(routes, default_queue)
    declared = consumer_queues(command)
    missing = needed - declared
    return {
        "scope": "STATIC_CELERY_SUBSCRIPTION_CONTRACT",
        "status": "FAIL" if missing else "PASS",
        "required_queues": sorted(needed),
        "subscribed_queues": sorted(declared),
        "missing_queues": sorted(missing),
    }


def load_worker(path):
    import yaml

    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ValueError("Malformed deployment configuration") from None
    return data["services"]["worker"]["command"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compose")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.workers.celery_app import celery_app

    try:
        result = assess(
            load_worker(args.compose),
            celery_app.conf.task_routes,
            celery_app.conf.task_default_queue,
        )
    except (ValueError, KeyError, TypeError, OSError):
        result = {
            "scope": "STATIC_CELERY_SUBSCRIPTION_CONTRACT",
            "status": "FAIL",
            "error": "Worker subscriptions could not be verified",
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

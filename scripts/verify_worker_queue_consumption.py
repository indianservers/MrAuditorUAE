"""Real local Redis/Celery consumption of deployment-template queue subscriptions."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil
from kombu.exceptions import OperationalError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from worker_queue_contract import assess, load_worker

ROOT = Path(__file__).resolve().parents[1]


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    parent = psutil.Process(process.pid)
    owned = [*parent.children(recursive=True), parent]
    for child in reversed(owned):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(owned, timeout=5)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)
    process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redis-server",
        type=Path,
        default=ROOT / ".local-runtime/redis/redis-server.exe",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/phase-12/worker-queue-consumption.json",
    )
    args = parser.parse_args()
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("Explicit isolated test settings required")
    run_id = uuid.uuid4().hex
    local = ROOT / ".local-runtime" / ("worker-queue-probe-" + run_id)
    local.mkdir(parents=True, exist_ok=False)
    redis_log = (local / "redis.log").open("wb")
    worker_log = (local / "worker.log").open("wb")
    redis_process = worker_process = client = application = None
    owns_broker = False
    started = time.monotonic()
    result = {
        "scope": "LOCAL_SYNTHETIC_TEMPLATE_QUEUE_CONSUMPTION",
        "status": "FAIL",
        "executed_at": datetime.now(UTC).isoformat(),
        "pool": "solo",
        "platform": sys.platform,
        "database_operations": "NONE_TEST_TASKS_ONLY",
        "hosted_or_container_qualification": False,
    }
    try:
        if not args.redis_server.is_file():
            raise ValueError("Local Redis executable required")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        redis_process = subprocess.Popen(
            [
                str(args.redis_server.resolve()),
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--protected-mode",
                "yes",
                "--dir",
                str(local),
            ],
            stdout=redis_log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        url = f"redis://127.0.0.1:{port}/0"
        client = Redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=1)
        deadline = time.monotonic() + 15
        while True:
            if redis_process.poll() is not None:
                raise RuntimeError("Owned Redis did not start")
            try:
                info = client.info("server")
                if info["process_id"] != redis_process.pid:
                    raise RuntimeError("Broker is not the newly owned Redis process")
                owns_broker = True
                if client.dbsize() != 0:
                    raise RuntimeError("Owned test broker is not empty")
                break
            except (RedisConnectionError, RedisTimeoutError, OSError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        result["broker_version"] = info["redis_version"]
        os.environ["REDIS_URL"] = url
        sys.path.insert(0, str(ROOT / "backend"))
        from app.workers.celery_app import celery_app

        application = celery_app
        template = ROOT / "deploy/compose.staging.yml"
        command = load_worker(template)
        check = assess(
            command, celery_app.conf.task_routes, celery_app.conf.task_default_queue
        )
        result["subscription_contract"] = check
        result["deployment_template_sha256"] = hashlib.sha256(
            template.read_bytes()
        ).hexdigest()
        if check["status"] != "PASS":
            raise ValueError(
                "Deployment worker does not subscribe to every configured route"
            )
        required = set(check["required_queues"])
        node = f"queue-proof-{run_id}@isolated"
        index = command.index("worker")
        worker_args = [
            sys.executable,
            "-m",
            "celery",
            *command[1:index],
            *command[index:],
            "--include=tests.phase12.worker_queue_probe",
            "--pool=solo",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--hostname=" + node,
        ]
        environment = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "backend")
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        )
        worker_process = subprocess.Popen(
            worker_args,
            cwd=ROOT / "backend",
            env=environment,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        deadline = time.monotonic() + 40
        while True:
            if worker_process.poll() is not None:
                raise RuntimeError("Owned worker exited before subscription readiness")
            active = (
                celery_app.control.inspect(
                    destination=[node], timeout=1
                ).active_queues()
                or {}
            )
            if node in active:
                observed = {queue["name"] for queue in active[node]}
                if not required <= observed:
                    raise RuntimeError("Running worker omits a configured queue")
                result["observed_active_queues"] = sorted(observed)
                break
            if time.monotonic() > deadline:
                raise TimeoutError("Owned worker did not report queue readiness")

        def health():
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.workers.queue_health",
                    "--node",
                    node,
                    "--timeout",
                    "1",
                ],
                cwd=ROOT / "backend",
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=flags,
            )
            return completed.returncode, json.loads(completed.stdout)

        initial_code, initial_health = health()
        if initial_code != 0 or initial_health["status"] != "PASS":
            raise RuntimeError(
                "Worker health entrypoint did not verify required subscriptions"
            )
        application.control.cancel_consumer(
            "intelligence", destination=[node], reply=True, timeout=2
        )
        absent_code, absent_health = health()
        if absent_code != 1 or absent_health.get("missing_queues") != ["intelligence"]:
            raise RuntimeError(
                "Worker health did not reject a missing country-workflow consumer"
            )
        application.control.add_consumer(
            "intelligence", destination=[node], reply=True, timeout=2
        )
        restored_code, restored_health = health()
        if restored_code != 0 or restored_health["status"] != "PASS":
            raise RuntimeError("Worker health did not verify restored subscriptions")
        result["health_entrypoint"] = {
            "all_consumers": initial_health,
            "country_consumer_removed": absent_health,
            "country_consumer_restored": restored_health,
        }
        for queue in sorted(required):
            celery_app.send_task(
                "auditos.qa.worker_queue_probe", args=[run_id, queue], queue=queue
            )
        records = []
        deadline = time.monotonic() + 25
        while len(records) < len(required) and time.monotonic() < deadline:
            item = client.blpop(f"qa:worker-queues:{run_id}", timeout=1)
            if item:
                records.append(json.loads(item[1]))
        if (
            len(records) != len(required)
            or {record["routing_key"] for record in records} != required
            or not all(record["matches"] for record in records)
        ):
            raise RuntimeError("Not every required queue delivered its probe task")
        result.update(
            status="PASS",
            completed_queues=sorted(required),
            completed_tasks=len(records),
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        OSError,
        ImportError,
        RedisError,
        OperationalError,
        subprocess.SubprocessError,
    ) as exc:
        result["error"] = (
            type(exc).__name__ + ": queue proof failed; inspect the owned local logs"
        )
    finally:
        if (
            application is not None
            and worker_process is not None
            and worker_process.poll() is None
        ):
            try:
                application.control.shutdown(destination=[node])
                worker_process.wait(timeout=8)
            except (OSError, RedisError, OperationalError, subprocess.SubprocessError):
                result["worker_forced_stop"] = True
        stop_owned(worker_process)
        if client is not None:
            try:
                if owns_broker:
                    client.shutdown(save=False)
            except (OSError, RedisError):
                result["broker_forced_stop"] = True
            client.close()
        stop_owned(redis_process)
        redis_log.close()
        worker_log.close()
        result["owned_processes_stopped"] = all(
            process is None or process.poll() is not None
            for process in (worker_process, redis_process)
        )
        if not result["owned_processes_stopped"]:
            result["status"] = "FAIL"
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

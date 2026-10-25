import importlib.util
from pathlib import Path

import pytest

from app.workers.celery_app import celery_app

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "worker_queue_contract", ROOT / "scripts/worker_queue_contract.py"
)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def test_staging_worker_covers_actual_application_routes_and_default_queue():
    command = contract.load_worker(ROOT / "deploy/compose.staging.yml")
    result = contract.assess(
        command, celery_app.conf.task_routes, celery_app.conf.task_default_queue
    )
    assert result["status"] == "PASS", result
    assert set(result["required_queues"]) == {"celery", "grc", "enterprise-ai", "intelligence"}


def test_missing_country_queue_is_detected_before_launch():
    result = contract.assess(
        ["celery", "worker", "-Q", "celery,grc,enterprise-ai"],
        celery_app.conf.task_routes,
        "celery",
    )
    assert result["status"] == "FAIL"
    assert result["missing_queues"] == ["intelligence"]


def test_future_configured_queue_cannot_silently_lose_its_consumer():
    routes = {**celery_app.conf.task_routes, "future.producer": {"queue": "future-provider"}}
    command = contract.load_worker(ROOT / "deploy/compose.staging.yml")
    assert contract.assess(command, routes, "celery")["missing_queues"] == ["future-provider"]


@pytest.mark.parametrize(
    "tail",
    [
        [],
        ["-Q"],
        ["-Q", "celery", "--queues=intelligence"],
        ["-Q", "celery,,intelligence"],
        ["-Q", "celery,celery"],
        ["-Q", "celery, intelligence"],
        ["-Q", "celery", "--exclude-queues=intelligence"],
    ],
)
def test_ambiguous_subscription_arguments_are_rejected(tail):
    with pytest.raises(ValueError):
        contract.consumer_queues(["celery", "worker", *tail])


def test_long_queue_option_and_dynamic_router_boundary():
    assert contract.consumer_queues(["celery", "worker", "--queues=celery,intelligence"]) == {
        "celery",
        "intelligence",
    }
    with pytest.raises(TypeError):
        contract.required_queues(["custom.router"], "celery")


@pytest.mark.parametrize("production", [False, True])
def test_probe_task_requires_test_environment_and_valid_run_identity(monkeypatch, production):
    from app.core.config import settings
    from tests.phase12.worker_queue_probe import probe

    monkeypatch.setattr(settings(), "environment", "production" if production else "test")
    with pytest.raises(RuntimeError, match="isolated test environment"):
        probe.run("a" * 32 if production else "invalid-run-id", "intelligence")


def test_probe_never_shuts_down_a_broker_it_does_not_own(tmp_path, monkeypatch):
    import json
    import sys

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    probe_spec = importlib.util.spec_from_file_location(
        "queue_consumption_probe", ROOT / "scripts/verify_worker_queue_consumption.py"
    )
    module = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "test")
    executable = tmp_path / "fake-redis"
    executable.write_text("test-only", encoding="utf-8")
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys, "argv", ["probe", "--redis-server", str(executable), "--output", str(report)]
    )

    class Process:
        pid = 12345
        done = False

        def poll(self):
            return 0 if self.done else None

    process = Process()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        module, "stop_owned", lambda owned: setattr(owned, "done", True) if owned else None
    )

    class Client:
        shutdown_called = False
        closed = False

        def info(self, _):
            return {"process_id": 99999}

        def shutdown(self, **_):
            self.shutdown_called = True

        def close(self):
            self.closed = True

    client = Client()

    class RedisFactory:
        @staticmethod
        def from_url(*args, **kwargs):
            return client

    monkeypatch.setattr(module, "Redis", RedisFactory)
    assert module.main() == 1
    assert not client.shutdown_called
    assert client.closed
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "FAIL"


@pytest.mark.parametrize(
    "queues,reason",
    [
        (None, "WORKER_NOT_REACHABLE"),
        ([{"name": "celery"}], "SUBSCRIPTION_MISSING"),
        ([{}], "QUEUE_HEALTH_UNVERIFIED"),
        ([{"name": None}], "QUEUE_HEALTH_UNVERIFIED"),
        ([{"name": "celery"}, {"name": "intelligence"}], "REQUIRED_QUEUES_ACTIVE"),
    ],
)
def test_runtime_health_requires_all_consumers(queues, reason):
    from types import SimpleNamespace

    from app.workers.queue_health import inspect_worker

    application = SimpleNamespace(
        conf=SimpleNamespace(
            task_routes={"task": {"queue": "intelligence"}}, task_default_queue="celery"
        ),
        control=SimpleNamespace(
            inspect=lambda **kwargs: SimpleNamespace(
                active_queues=lambda: None if queues is None else {"worker": queues}
            )
        ),
    )
    result = inspect_worker(application, "worker")
    assert result["reason"] == reason
    assert result["status"] == ("PASS" if reason == "REQUIRED_QUEUES_ACTIVE" else "FAIL")


def test_staging_health_runs_subscription_entrypoint():
    import yaml

    compose = yaml.safe_load((ROOT / "deploy/compose.staging.yml").read_text(encoding="utf-8"))
    assert compose["services"]["worker"]["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-m",
        "app.workers.queue_health",
        "--timeout",
        "3",
    ]

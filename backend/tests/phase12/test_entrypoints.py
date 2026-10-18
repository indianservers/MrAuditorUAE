import os

import pytest

from app.core.config import settings
from app.workers import celery_app
from tests.integration.test_platform import environment as environment


@pytest.mark.parametrize("production", [False, True])
def test_background_startup_checks_only_production(monkeypatch, production):
    called = []

    async def ready():
        called.append(True)

    monkeypatch.setattr(settings(), "environment", "production" if production else "test")
    monkeypatch.setattr(celery_app, "production_readiness", ready)
    celery_app.enforce_production_readiness()
    assert bool(called) == production


def test_background_startup_stops_before_consumption_on_failed_readiness(monkeypatch):
    async def unavailable():
        raise RuntimeError("synthetic marker, unsafe role or dependency failure")

    monkeypatch.setattr(settings(), "environment", "production")
    monkeypatch.setattr(celery_app, "production_readiness", unavailable)
    with pytest.raises(SystemExit) as exc:
        celery_app.enforce_production_readiness()
    assert exc.value.code == 78


@pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable migrated database required"
)
async def test_readiness_rejects_renamed_known_demo_tenant(environment, monkeypatch):
    from fastapi import HTTPException

    from app.api.v1.health import ready
    from app.db.models.platform import Tenant
    from app.db.session import Session
    from app.modules.demo.guard import DEMO_TENANT

    monkeypatch.setattr(settings(), "environment", "production")
    assert (await ready()).status == "ready"
    async with Session() as db, db.begin():
        db.add(Tenant(id=DEMO_TENANT, name="Renamed test tenant without marker"))
    with pytest.raises(HTTPException) as exc:
        await ready()
    assert exc.value.status_code == 503

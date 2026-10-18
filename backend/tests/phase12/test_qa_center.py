import os
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, settings
from app.db.models.platform import User
from app.db.session import Session
from app.modules.identity.service import issue
from app.modules.saas.models import Operation, PlatformOperator
from tests.integration.test_platform import environment as environment
from tests.integration.test_platform import setup


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "production"),
        ("synthetic_data_enabled", False),
        ("database_url", "postgresql+asyncpg://app@127.0.0.1:55432/shared"),
    ],
)
async def test_campaign_seeding_rejects_unsafe_config_before_database_access(
    monkeypatch, field, value
):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from qa_campaign import guard

    monkeypatch.setenv("QA_CAMPAIGN_ENABLED", "true")
    monkeypatch.setattr(settings(), "environment", "development")
    monkeypatch.setattr(settings(), "synthetic_data_enabled", True)
    monkeypatch.setattr(
        settings(),
        "database_url",
        "postgresql+asyncpg://app@127.0.0.1:55432/auditos_qa_campaign_demo",
    )
    monkeypatch.setattr(settings(), field, value)
    with pytest.raises(RuntimeError, match="explicit local isolated"):
        await guard(None)


@pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required")
async def test_migrated_ledger_has_tenant_order_pagination_index(environment):
    from sqlalchemy import text

    async with Session() as db:
        definition = await db.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname='ix_lines_tenant_created_id'"
            )
        )
        assert "(tenant_id, created_at, id)" in definition


def test_qa_campaign_configuration_forbidden_in_production():
    with pytest.raises(ValidationError, match="QA campaign controls"):
        Settings(
            database_url="postgresql+asyncpg://test/test",
            jwt_secret="x" * 64,
            bootstrap_secret="",
            environment="production",
            qa_campaign_enabled=True,
        )


@pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required")
async def test_client_directory_searches_name_or_code_without_wildcard_expansion(environment):
    c = environment
    h, _ = await setup(c)
    r = await c.post(
        "/api/v1/clients",
        headers=h,
        json={"code": "QA-CODE-ONLY", "name": "Fictional Search Company"},
    )
    assert r.status_code == 201
    found = await c.get("/api/v1/clients", headers=h, params={"search": "qa-code-only"})
    assert found.status_code == 200
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["id"] == r.json()["id"]
    assert (
        await c.get("/api/v1/clients", headers=h, params={"search": "Fictional Search"})
    ).json()["total"] == 1
    assert (await c.get("/api/v1/clients", headers=h, params={"search": "%"})).json()["total"] == 0


@pytest.mark.skipif(os.getenv("INTEGRATION_TESTS") != "1", reason="Disposable database required")
async def test_qa_center_requires_operator_mfa_flag_and_reads_persisted_results(
    environment, monkeypatch
):
    c = environment
    h, _ = await setup(c)
    assert (await c.get("/api/v1/platform/qa-center")).status_code == 401
    assert (await c.get("/api/v1/platform/qa-center", headers=h)).status_code == 403
    async with Session() as db, db.begin():
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        user.mfa_enabled = True
        db.add(PlatformOperator(user_id=user.id))
        db.add(
            Operation(
                actor_id=user.id,
                tenant_id=None,
                action="qa.campaign.results",
                details={
                    "passed": 7,
                    "failed": 2,
                    "skipped": 1,
                    "executed_at": datetime.now(UTC).isoformat(),
                },
            )
        )
        tokens = await issue(db, user.id, mfa=True)
    verified = {"Authorization": "Bearer " + tokens.access_token}
    monkeypatch.setattr(settings(), "qa_campaign_enabled", False)
    assert (await c.get("/api/v1/platform/qa-center", headers=verified)).status_code == 404
    monkeypatch.setattr(settings(), "qa_campaign_enabled", True)
    r = await c.get("/api/v1/platform/qa-center", headers=verified)
    assert r.status_code == 200, r.text
    assert r.json()["runs"][0]["results"]["failed"] == 2
    assert r.json()["runs"][0]["results"]["passed"] == 7
    assert uuid.UUID(r.json()["runs"][0]["id"])

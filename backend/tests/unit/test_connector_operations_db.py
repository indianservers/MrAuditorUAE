"""Opt-in PostgreSQL RLS/concurrency and real Redis checks; dedicated databases only."""

import asyncio
import importlib.util
import io
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import tenant_context
from app.modules.connectors.quota import OrganizationQuota, QuotaDeferred
from app.modules.connectors.runtime import ConnectorRuntime
from app.modules.lineage.storage import ObjectStore

pytestmark = pytest.mark.skipif(not os.getenv("CONNECTOR_TEST_DATABASE_URL"), reason="Run scripts/connector_operations_run.py for isolated real DB tests")


@pytest.fixture
async def database(monkeypatch, tmp_path):
    url = os.environ["CONNECTOR_TEST_DATABASE_URL"]
    assert re.fullmatch(r"connector_test_[a-f0-9]{32}", make_url(url).database or "")
    role = os.environ["CONNECTOR_TEST_ROLE"]
    assert re.fullmatch(r"connector_test_[a-f0-9]{32}_app", role)
    admin_url = os.environ["CONNECTOR_TEST_ADMIN_URL"]
    assert make_url(admin_url).database == make_url(url).database
    admin = await asyncpg.connect(admin_url)
    await admin.execute('DROP TABLE IF EXISTS connector_states, tenants, users CASCADE')
    await admin.execute('DROP FUNCTION IF EXISTS protect_connector_evidence()')
    await admin.execute('CREATE TABLE tenants(id UUID PRIMARY KEY); CREATE TABLE users(id UUID PRIMARY KEY)')
    admin_engine = create_async_engine(admin_url.replace("postgresql://", "postgresql+asyncpg://"))
    migration_path = Path(__file__).resolve().parents[2] / "alembic/versions/0019_connector_operations.py"
    spec = importlib.util.spec_from_file_location("connector_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with admin_engine.begin() as connection:
        def upgrade(sync):
            migration.op = Operations(MigrationContext.configure(sync))
            migration.upgrade()
        await connection.run_sync(upgrade)
    await admin_engine.dispose()
    await admin.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO "{role}"')
    tenants = [uuid.uuid4(), uuid.uuid4()]
    user = uuid.uuid4()
    for tenant in tenants:
        await admin.execute('INSERT INTO tenants VALUES($1)', tenant)
    await admin.execute('INSERT INTO users VALUES($1)', user)
    await admin.close()
    monkeypatch.setattr(settings(), "connector_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings(), "source_storage_path", str(tmp_path))
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    contexts = [SimpleNamespace(tenant_id=t, user_id=user) for t in tenants]
    yield factory, contexts
    await engine.dispose()


async def test_rls_tenant_isolation_and_immutable_evidence(database):
    factory, contexts = database
    runtime = ConnectorRuntime(factory, contexts[0], uuid.uuid4())
    await runtime.put("session", "same-key", {"status": "extracting"})
    await runtime.put("source_revision", "immutable", {"evidence": True})
    other = ConnectorRuntime(factory, contexts[1], uuid.uuid4())
    assert await other.get("session", "same-key") is None
    await other.put("session", "same-key", {"status": "other_tenant"})
    assert (await runtime.get("session", "same-key"))["status"] == "extracting"
    with pytest.raises(Exception, match="immutable"):
        await runtime.put("source_revision", "immutable", {"evidence": False})
    async with factory() as db, db.begin():
        await tenant_context(db, str(contexts[0].tenant_id))
        deleted = await db.execute(text("DELETE FROM connector_states WHERE namespace='session' RETURNING id"))
        assert len(deleted.all()) == 1  # Trigger must RETURN OLD on nonimmutable DELETE.
    assert await runtime.get("session", "same-key") is None


async def test_parallel_grant_refresh_rotates_once_and_keeps_current_client_secret(database):
    factory, contexts = database
    runtimes = [ConnectorRuntime(factory, contexts[0], uuid.uuid4()) for _ in range(4)]
    exchanges = []
    async def exchange(source):
        exchanges.append(source)
        await asyncio.sleep(.02)
        return {**source, "access_token": "new-access", "refresh_token": "new-refresh"}
    original = {"client_id": "client", "client_secret": "old-secret", "access_token": "old-access", "refresh_token": "old-refresh"}
    values = await asyncio.gather(*(r.rotate_grant("shared-grant", original, exchange, force=True) for r in runtimes))
    assert len(exchanges) == 1 and all(value["refresh_token"] == "new-refresh" for value in values)
    latest = await runtimes[0].rotate_grant("shared-grant", {**original, "client_secret": "new-secret"}, exchange)
    assert latest["client_secret"] == "new-secret"


async def test_checkpoint_commits_outside_caller_and_rejects_tampered_bytes(database, monkeypatch):
    factory, contexts = database
    runtime = ConnectorRuntime(factory, contexts[0], uuid.uuid4())
    async def persist(raw):
        return ObjectStore().put(str(contexts[0].tenant_id), io.BytesIO(raw))
    monkeypatch.setattr(runtime, "persist_object", persist)
    calls = []
    async def fetch():
        calls.append(True)
        return {"amount": 12}, b'{"amount":12}'
    async with factory() as caller, caller.begin():
        await tenant_context(caller, str(contexts[0].tenant_id))
        await runtime.cached_read("session", "page", fetch)
        await caller.rollback()
    second = ConnectorRuntime(factory, contexts[0], runtime.connection_id)
    assert (await second.cached_read("session", "page", fetch))[0] == {"amount": 12}
    assert len(calls) == 1 and second.replayed == 1
    pointer = second.last_object
    with ObjectStore().local(pointer["object_key"], pointer["object_version"]) as path:
        path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        await second.cached_read("session", "page", fetch)


async def test_real_redis_org_budget_and_concurrency_are_shared_across_clients():
    redis = Redis.from_url(os.environ["CONNECTOR_TEST_REDIS_URL"])
    organization = "connector-test-" + uuid.uuid4().hex
    first = OrganizationQuota(redis, "test", organization, "client-a", 2, 10, 1)
    second = OrganizationQuota(redis, "test", organization, "client-b", 2, 10, 1)
    try:
        lease = await first.acquire()
        with pytest.raises(QuotaDeferred):
            await second.acquire()
        await first.release(lease)
        lease = await second.acquire()
        await second.release(lease)
        with pytest.raises(QuotaDeferred):
            await first.acquire()
    finally:
        await redis.delete(first.key, first.key + ":leases")
        await redis.aclose()

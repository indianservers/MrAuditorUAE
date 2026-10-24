"""Run connector DB/Redis tests in a new database, then remove only that database/role."""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url


async def main():
    admin_url = os.getenv("CONNECTOR_TEST_ADMIN_URL", "postgresql://postgres@127.0.0.1:55432/postgres")
    root = Path(__file__).resolve().parents[1]
    name = "connector_test_" + uuid.uuid4().hex
    role = name + "_app"
    admin = await asyncpg.connect(admin_url)
    created_role = created_database = False
    try:
        await admin.execute(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS')
        created_role = True
        await admin.execute(f'CREATE DATABASE "{name}"')
        created_database = True
        url = make_url(admin_url).set(database=name)
        env = {**os.environ, "ENVIRONMENT": "test", "CONNECTOR_TEST_DATABASE_URL": str(url.set(drivername="postgresql+asyncpg", username=role).render_as_string(hide_password=False)),
            "CONNECTOR_TEST_ADMIN_URL": url.render_as_string(hide_password=False),
            "CONNECTOR_TEST_ROLE": role, "CONNECTOR_TEST_REDIS_URL": os.getenv("CONNECTOR_TEST_REDIS_URL", "redis://127.0.0.1:56379/0"),
            "JWT_SECRET": "connector-tests-only-at-least-48-characters-long-key", "DATABASE_URL": str(url.set(drivername="postgresql+asyncpg", username=role).render_as_string(hide_password=False))}
        return subprocess.call([sys.executable, "-m", "pytest", "tests/unit/test_connector_operations_db.py", "-q"], cwd=root / "backend", env=env)
    finally:
        # Both identifiers are generated here, never derived from a user path or
        # existing database. No existing schema, role or Redis database is cleared.
        if created_database:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        if created_role:
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

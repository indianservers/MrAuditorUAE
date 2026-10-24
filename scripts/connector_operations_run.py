"""Run connector DB/Redis tests in a new database, then remove only that database/role."""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import asyncpg
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url


async def main():
    admin_url = os.getenv(
        "CONNECTOR_TEST_ADMIN_URL", "postgresql://postgres@127.0.0.1:55432/postgres"
    )
    root = Path(__file__).resolve().parents[1]
    name = "connector_test_" + uuid.uuid4().hex + "_test"
    role = name + "_app"
    role_password = uuid.uuid4().hex
    admin = await asyncpg.connect(admin_url)
    created_role = created_database = False
    redis_process = None
    temporary = tempfile.TemporaryDirectory(prefix="auditos-connector-tests-")
    try:
        await admin.execute(
            f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{role_password}'"
        )
        created_role = True
        await admin.execute(f'CREATE DATABASE "{name}"')
        created_database = True
        url = make_url(admin_url).set(database=name)
        env = {
            **os.environ,
            "ENVIRONMENT": "test",
            "CONNECTOR_TEST_DATABASE_URL": str(
                url.set(
                    drivername="postgresql+asyncpg", username=role, password=role_password
                ).render_as_string(hide_password=False)
            ),
            "CONNECTOR_TEST_ADMIN_URL": url.render_as_string(hide_password=False),
            "CONNECTOR_TEST_ROLE": role,
            "CONNECTOR_TEST_REDIS_URL": os.getenv(
                "CONNECTOR_TEST_REDIS_URL", "redis://127.0.0.1:56379/0"
            ),
            "JWT_SECRET": "connector-tests-only-at-least-48-characters-long-key",
            "DATABASE_URL": str(
                url.set(
                    drivername="postgresql+asyncpg", username=role, password=role_password
                ).render_as_string(hide_password=False)
            ),
        }
        if "--integration" in sys.argv:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            redis_binary = root / ".local-runtime/redis/redis-server.exe"
            redis_process = subprocess.Popen(
                [
                    str(redis_binary),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                ],
                cwd=temporary.name,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for _ in range(60):
                with socket.socket() as probe:
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        break
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError("Disposable Redis did not start")
            env.update(
                REDIS_URL=f"redis://127.0.0.1:{port}/0",
                INTEGRATION_TESTS="1",
                BOOTSTRAP_SECRET="connector-integration-bootstrap",
                CONNECTOR_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                SOURCE_STORAGE_PATH=temporary.name + "/objects",
                MFA_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                SYNTHETIC_DATA_ENABLED="false",
                QA_CAMPAIGN_ENABLED="false",
            )
            migration_env = {
                **env,
                "DATABASE_URL": url.set(drivername="postgresql+asyncpg").render_as_string(
                    hide_password=False
                ),
            }
            code = subprocess.call(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=root / "backend",
                env=migration_env,
            )
            if code:
                return code
            grant = await asyncpg.connect(url.render_as_string(hide_password=False))
            await grant.execute(
                f'GRANT USAGE ON SCHEMA public TO "{role}"; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{role}"; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{role}"'
            )
            await grant.close()
            return subprocess.call(
                [sys.executable, "-m", "pytest", "tests/phase2", "-q"],
                cwd=root / "backend",
                env=env,
            )
        return subprocess.call(
            [sys.executable, "-m", "pytest", "tests/unit/test_connector_operations_db.py", "-q"],
            cwd=root / "backend",
            env=env,
        )
    finally:
        # Both identifiers are generated here, never derived from a user path or
        # existing database. No existing schema, role or Redis database is cleared.
        if created_database:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        if created_role:
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()
        if redis_process:
            redis_process.terminate()
            redis_process.wait(timeout=10)
        temporary.cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

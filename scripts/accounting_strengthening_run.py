"""Isolated verification environment: only auditos_accounting_strengthening_test is used."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "auditos_accounting_strengthening_test"
config = ROOT / ".local-runtime/qa-campaign/environment.local.json"
if not config.exists() or len(sys.argv) < 2:
    raise SystemExit(
        "Initialize the existing local QA secrets and supply prepare or a command"
    )
os.environ.update(json.loads(config.read_text()))
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=f"postgresql+asyncpg://auditos_phase4_app@127.0.0.1:55432/{DATABASE}",
    REDIS_URL="redis://127.0.0.1:56379/10",
    SOURCE_STORAGE_PATH=str(ROOT / ".local-runtime/accounting-strengthening/objects"),
    INTEGRATION_TESTS="1",
    SYNTHETIC_DATA_ENABLED="false",
    DEMO_DATABASE_NAME="",
    DEMO_TENANT_ID="",
    QA_CAMPAIGN_ENABLED="true",
    AI_API_KEY="",
    AUDIT_AI_EXTERNAL_APPROVED="false",
    ACCOUNTING_ARTIFACT_DIR=str(ROOT / "docs/engine-strengthening/phase3"),
)


async def prepare():
    import asyncpg

    connection = await asyncpg.connect(
        user="postgres", host="127.0.0.1", port=55432, database="postgres"
    )
    try:
        if not await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", DATABASE
        ):
            await connection.execute(
                "CREATE DATABASE auditos_accounting_strengthening_test OWNER auditos_phase4_app"
            )
    finally:
        await connection.close()


if sys.argv[1] == "prepare":
    asyncio.run(prepare())
    args = [
        str(ROOT / "backend/.venv/Scripts/python.exe"),
        "-m",
        "alembic",
        "upgrade",
        "head",
    ]
else:
    args = sys.argv[1:]
    if args[0].startswith(".venv/"):
        args[0] = str(ROOT / "backend" / args[0])
raise SystemExit(subprocess.call(args, cwd=ROOT / "backend", env=os.environ))

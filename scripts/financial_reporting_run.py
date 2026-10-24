"""Run verification against a dedicated disposable financial workflow database."""

import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = root / ".local-runtime/qa-campaign/environment.local.json"
if not config.exists() or len(sys.argv) < 2:
    raise SystemExit("Initialize the local QA environment, then supply a command")
os.environ.update(json.loads(config.read_text()))
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL="postgresql+asyncpg://auditos_phase4_app@127.0.0.1:55432/auditos_financial_workflow_test",
    REDIS_URL="redis://127.0.0.1:56379/7",
    SOURCE_STORAGE_PATH=str(root / ".local-runtime/financial-reporting/objects"),
    INTEGRATION_TESTS="1",
    SYNTHETIC_DATA_ENABLED="false",
    DEMO_DATABASE_NAME="",
    DEMO_TENANT_ID="",
    QA_CAMPAIGN_ENABLED="true",
    AI_API_KEY="",
    AUDIT_AI_EXTERNAL_APPROVED="false",
)
args = sys.argv[1:]
if args[0].startswith(".venv/"):
    args[0] = str(root / "backend" / args[0])
sys.exit(subprocess.call(args, cwd=root / "backend", env=os.environ))

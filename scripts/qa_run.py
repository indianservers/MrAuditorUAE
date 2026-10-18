import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
local = root / ".local-runtime/qa-campaign"
local.mkdir(parents=True, exist_ok=True)
config = local / "environment.local.json"
if not config.exists():
    config.write_text(
        json.dumps(
            {
                "JWT_SECRET": secrets.token_hex(48),
                "BOOTSTRAP_SECRET": secrets.token_hex(32),
                "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "QA_PASSWORD": secrets.token_urlsafe(24),
            }
        )
    )
os.environ.update(json.loads(config.read_text()))
if len(sys.argv) < 3 or sys.argv[1] not in {"test", "demo"}:
    raise SystemExit("Usage: qa_run.py {test|demo} COMMAND [ARGS]")
mode = sys.argv[1]
database = "auditos_qa_campaign_test" if mode == "test" else "auditos_qa_campaign_demo"
os.environ.update(
    ENVIRONMENT="test" if mode == "test" else "development",
    DATABASE_URL="postgresql+asyncpg://auditos_phase4_app@127.0.0.1:55432/" + database,
    REDIS_URL="redis://127.0.0.1:56379/4",
    SOURCE_STORAGE_PATH=str(local / ("test-objects" if mode == "test" else "objects")),
    INTEGRATION_TESTS="1",
    SYNTHETIC_DATA_ENABLED="true" if mode != "test" else "false",
    DEMO_DATABASE_NAME=database if mode != "test" else "",
    DEMO_TENANT_ID="8733db06-81bc-59b3-afcc-bf0f4c0cd8a2" if mode != "test" else "",
    QA_CAMPAIGN_ENABLED="true",
    AI_API_KEY="",
    AUDIT_AI_EXTERNAL_APPROVED="false",
)
args = sys.argv[2:]
args[0] = str(root / "backend" / args[0]) if args[0].startswith(".venv/") else args[0]
sys.exit(subprocess.call(args, cwd=root / "backend", env=os.environ))

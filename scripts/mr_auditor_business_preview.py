"""Synthetic browser seed; refuses every database except the owned disposable audit-gap DB."""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    if settings().environment != "test" or not settings().database_url.endswith("/auditos_audit_gap_test") or os.getenv("INTEGRATION_TESTS") != "1":
        raise SystemExit("Only the owned auditos_audit_gap_test database is allowed")
    from tests.integration.test_platform import environment
    from tests.phase5.test_reporting import prepared
    fixture = environment.__wrapped__()
    client = await anext(fixture)
    try:
        h, eid, _, _, _, profile, _, _, ready = await prepared(client)
        lease = await ready("lease", {"profile_id": profile["id"], "commencement": "2026-01-01", "end_date": "2026-12-31",
            "annual_discount_rate": "0.05", "payments": [{"date": "2026-12-31", "amount": "12000"}],
            "recognition_assessment": "SYNTHETIC office lease evidence", "options_assessment": "No renewal options in this synthetic fixture"})
        target = ROOT / ".local-runtime/mr-auditor-business/fixture.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"tenant_id": h["X-Tenant-ID"], "engagement_id": eid,
            "lease_id": lease["id"], "synthetic": True}, indent=2))
        print(json.dumps({"seeded": True, "synthetic": True, "engagement_id": eid}))
    finally:
        await fixture.aclose()


asyncio.run(main())

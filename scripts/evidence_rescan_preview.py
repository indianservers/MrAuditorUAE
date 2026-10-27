"""Owned synthetic quarantined originals; no live scanner qualification."""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import create
    from tests.qa_crud.test_generic_candidates import context

    config = settings()
    if (
        config.environment != "test"
        or not config.database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
        or config.evidence_clamav_host
    ):
        raise SystemExit("Owned disposable database and explicitly unconfigured scanner required")
    fixture = environment.__wrapped__()
    c = await anext(fixture)
    try:
        existing = await context(c, "AE")
        saved = {"synthetic": True, "scanner": "UNCONFIGURED_QUARANTINE_PATH", "countries": {}}
        for country in ("AE", "IN"):
            h, _, eid, audit = existing if country == "AE" else await context(c, country, existing)
            record = await create(
                c, h, audit, "evidence", dict(category="Other", retain_until="2036-12-31")
            )
            upload = await c.post(
                audit + "/evidence-files/" + record["id"],
                headers=h,
                files={
                    "file": (
                        f"SYNTHETIC-{country}-rescan.txt",
                        b"SYNTHETIC retained original",
                        "text/plain",
                    )
                },
            )
            assert upload.status_code == 201, upload.text
            assert upload.json()["scan_status"] == "QUARANTINED"
            saved["countries"][country] = {
                "engagement": eid,
                "record": record["id"],
                "sha256": upload.json()["sha256"],
            }
        (ROOT / ".local-runtime/country-workflows/evidence-rescan-fixture.json").write_text(
            json.dumps(saved, indent=2) + "\n", encoding="utf-8"
        )
        print("Saved UAE/India quarantined originals for browser rescan verification")
    finally:
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

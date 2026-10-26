"""Prepare synthetic grant sources in the owned disposable database for browser QA."""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    from app.core.operations_contracts import country_workflow_hash

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only owned disposable workflow verification DB allowed")
    import pytest
    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import actor, grant, setup
    from tests.qa_crud.test_country_workflows import double_boundaries
    from tests.qa_crud.test_grant_utilisation import prepare

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, options, eid, audit = await setup(c)
        reviewer = await actor(h, "Firm Administrator", "grant-browser-source-reviewer")
        await grant(c, h, audit, reviewer)
        saved = {
            "implementation_sha256": country_workflow_hash(),
            "cases": {},
            "country_order": ["AE", "IN"],
        }
        for country in ("AE", "IN"):
            if country == "IN":
                entity = await c.post(
                    "/api/v1/entities",
                    headers=h,
                    json={
                        "client_id": options["client_id"],
                        "name": "SYNTHETIC India grant recipient",
                        "country": "IN",
                        "jurisdiction": "Synthetic India",
                        "functional_currency": "INR",
                        "presentation_currency": "INR",
                    },
                )
                assert entity.status_code == 201, entity.text
                period = await c.post(
                    "/api/v1/financial-periods",
                    headers=h,
                    json={
                        "entity_id": entity.json()["id"],
                        "start_date": "2026-04-01",
                        "end_date": "2027-03-31",
                    },
                )
                assert period.status_code == 201, period.text
                engagement = await c.post(
                    "/api/v1/engagements",
                    headers=h,
                    json={
                        "entity_id": entity.json()["id"],
                        "period_id": period.json()["id"],
                        "name": "SYNTHETIC India grant review",
                        "engagement_type": "External Audit",
                    },
                )
                assert engagement.status_code == 201, engagement.text
                eid = engagement.json()["id"]
                audit = f"/api/v1/engagements/{eid}/audit"
                await grant(c, h, audit, reviewer)
            saved["cases"][country] = {}
            for case in ("matched", "credit", "nil", "over-budget", "unallocated"):
                prepared = await prepare(c, h, eid, reviewer, country, case)
                saved["cases"][country][case] = {
                    "engagement": eid,
                    "payload": prepared["payload"],
                    "documents": {
                        role: {
                            key: value
                            for key, value in document.items()
                            if key != "bytes"
                        }
                        for role, document in prepared["documents"].items()
                    },
                }
        path = ROOT / ".local-runtime/country-workflows/grant-fixture.json"
        path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        print("Saved synthetic UAE/India grant sources for real-worker browser QA")
    finally:
        patch.undo()
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

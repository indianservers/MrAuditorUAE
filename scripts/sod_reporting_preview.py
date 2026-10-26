"""Owned disposable UAE/India SoD fixtures; never real clients or production."""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only owned disposable workflow verification DB allowed")
    import pytest

    from app.modules.grc.sod_sources import implementation_hash
    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import actor, grant, setup
    from tests.qa_crud.test_country_workflows import double_boundaries
    from tests.qa_crud.test_sod_reporting import prepare

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, options, eid, audit = await setup(c)
        reviewer = await actor(h, "Firm Administrator", "sod-preview-reviewer")
        await grant(c, h, audit, reviewer)
        saved = dict(
            implementation_sha256=implementation_hash(), country_order=["AE", "IN"], cases={}
        )
        for country in ("AE", "IN"):
            if country == "IN":
                response = await c.post(
                    "/api/v1/entities",
                    headers=h,
                    json=dict(
                        client_id=options["client_id"],
                        name="SYNTHETIC India SoD entity",
                        country="IN",
                        jurisdiction="Synthetic India",
                        functional_currency="INR",
                        presentation_currency="INR",
                    ),
                )
                assert response.status_code == 201, response.text
                entity = response.json()["id"]
                response = await c.post(
                    "/api/v1/financial-periods",
                    headers=h,
                    json=dict(entity_id=entity, start_date="2026-01-01", end_date="2026-12-31"),
                )
                assert response.status_code == 201, response.text
                response = await c.post(
                    "/api/v1/engagements",
                    headers=h,
                    json=dict(
                        entity_id=entity,
                        period_id=response.json()["id"],
                        name="SYNTHETIC India SoD audit",
                        engagement_type="External Audit",
                    ),
                )
                assert response.status_code == 201, response.text
                eid = response.json()["id"]
                audit = f"/api/v1/engagements/{eid}/audit"
                await grant(c, h, audit, reviewer)
            case = await prepare(c, h, eid, audit, reviewer, country)
            saved["cases"][country] = dict(
                engagement=eid,
                run=case["run"]["id"],
                source=case["source"],
                access=case["access"]["id"],
                reference=case["reference"],
            )
        # Kept in ignored local runtime, including reviewer headers for controlled staleness QA.
        saved.update(headers=h, reviewer=reviewer[0])
        path = ROOT / ".local-runtime/country-workflows/sod-reporting-fixture.json"
        path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        print("Saved synthetic UAE and India SoD reporting fixtures")
    finally:
        patch.undo()
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

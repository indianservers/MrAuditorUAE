"""Prepare reviewed UAE/India ambiguity sources for real-worker browser QA."""

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
        raise SystemExit("Only owned disposable workflow verification database allowed")
    import pytest

    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import actor, grant, setup
    from tests.qa_crud.test_country_workflows import double_boundaries
    from tests.qa_crud.test_matching_candidates import prepare

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, options, eid, base = await setup(c)
        reviewer = await actor(h, "Firm Administrator", "matching-preview-reviewer")
        await grant(c, h, base, reviewer)
        saved = dict(implementation_sha256=country_workflow_hash(), countries={})
        for country in ("AE", "IN"):
            if country == "IN":
                entity = await c.post(
                    "/api/v1/entities",
                    headers=h,
                    json=dict(
                        client_id=options["client_id"],
                        name="SYNTHETIC India matching candidates",
                        country="IN",
                        jurisdiction="Synthetic India",
                        functional_currency="INR",
                        presentation_currency="INR",
                    ),
                )
                assert entity.status_code == 201, entity.text
                period = await c.post(
                    "/api/v1/financial-periods",
                    headers=h,
                    json=dict(
                        entity_id=entity.json()["id"],
                        start_date="2026-04-01",
                        end_date="2027-03-31",
                    ),
                )
                assert period.status_code == 201, period.text
                eng = await c.post(
                    "/api/v1/engagements",
                    headers=h,
                    json=dict(
                        entity_id=entity.json()["id"],
                        period_id=period.json()["id"],
                        name="SYNTHETIC India competing bank transactions",
                        engagement_type="External Audit",
                    ),
                )
                assert eng.status_code == 201, eng.text
                eid = eng.json()["id"]
                await grant(c, h, f"/api/v1/engagements/{eid}/audit", reviewer)
            prepared = await prepare(c, h, eid, reviewer, country)
            saved["countries"][country] = dict(
                engagement=eid,
                payload=prepared["payload"],
                ambiguous_items=121,
                candidates_per_item=121,
                candidate_links=14641,
            )
        (ROOT / ".local-runtime/country-workflows/matching-fixture.json").write_text(
            json.dumps(saved, indent=2) + "\n", encoding="utf-8"
        )
        print("Saved synthetic UAE/India competing-bank source fixtures")
    finally:
        patch.undo()
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

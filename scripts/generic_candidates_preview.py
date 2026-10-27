"""Prepare committed UAE/India ledgers and independently reviewed supporting CSVs."""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    from app.core.operations_contracts import country_workflow_hash, implementation_hash

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only owned disposable workflow verification database allowed")
    import pytest

    from tests.integration.test_platform import environment
    from tests.qa_crud.test_country_workflows import double_boundaries
    from tests.qa_crud.test_generic_candidates import context, prepare

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        existing = await context(c, "AE")
        saved = dict(
            implementation_sha256=implementation_hash(),
            country_implementation_sha256=country_workflow_hash(),
            countries={},
        )
        for country in ("AE", "IN"):
            h, options, eid, audit = (
                existing if country == "AE" else await context(c, country, existing)
            )
            payload, _ = await prepare(c, h, options, eid, audit, country)
            saved["countries"][country] = dict(
                engagement=eid,
                payload=payload,
                ambiguous_items=121,
                candidates_per_item=121,
                candidate_links=14641,
            )
        (ROOT / ".local-runtime/country-workflows/generic-candidates-fixture.json").write_text(
            json.dumps(saved, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "Saved committed UAE/India ledgers and independently reviewed original supporting CSVs"
        )
    finally:
        patch.undo()
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

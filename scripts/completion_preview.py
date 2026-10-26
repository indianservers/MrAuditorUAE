"""Prepare current/stale/reassessed completion cases in the owned test database."""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def implementation_hash():
    paths = [
        "backend/app/modules/audit_execution/completion_sources.py",
        "backend/app/modules/audit_execution/service.py",
        "backend/app/modules/lineage/working_papers.py",
        "backend/app/api/v1/audit_execution.py",
        "frontend/src/features/audit-studio.tsx",
        "frontend/src/features/completion-controls.tsx",
    ]
    return hashlib.sha256(
        json.dumps(
            {
                name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest()
                for name in paths
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def main():
    from app.core.config import settings

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only the owned disposable workflow verification database is allowed")
    import pytest

    from tests.integration.test_platform import environment
    from tests.phase4.test_workflows import actor, setup
    from tests.qa_crud.test_completion_freshness import move, prepare, reassess, replace_ledger
    from tests.qa_crud.test_country_workflows import double_boundaries

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    patch = pytest.MonkeyPatch()
    try:
        double_boundaries(patch)
        h, initial, _, _ = await setup(c)
        partner = await actor(h, "Audit Partner", "completion-preview-partner")
        saved = dict(implementation_sha256=implementation_hash(), countries={})
        for country in ("AE", "IN"):
            saved["countries"][country] = {}
            for case in ("current", "stale", "reassessed"):
                entity = await c.post(
                    "/api/v1/entities",
                    headers=h,
                    json=dict(
                        client_id=initial["client_id"],
                        name=f"SYNTHETIC {country} {case} completion entity",
                        country=country,
                        jurisdiction=f"Synthetic {country}",
                        functional_currency="AED" if country == "AE" else "INR",
                        presentation_currency="AED" if country == "AE" else "INR",
                    ),
                )
                assert entity.status_code == 201, entity.text
                period = await c.post(
                    "/api/v1/financial-periods",
                    headers=h,
                    json=dict(
                        entity_id=entity.json()["id"],
                        start_date="2026-01-01" if country == "AE" else "2026-04-01",
                        end_date="2026-12-31" if country == "AE" else "2027-03-31",
                    ),
                )
                assert period.status_code == 201, period.text
                eng = await c.post(
                    "/api/v1/engagements",
                    headers=h,
                    json=dict(
                        entity_id=entity.json()["id"],
                        period_id=period.json()["id"],
                        name=f"SYNTHETIC {country} {case} completion case",
                        engagement_type="External Audit",
                    ),
                )
                assert eng.status_code == 201, eng.text
                eid = eng.json()["id"]
                options = dict(
                    initial, entity_id=entity.json()["id"], period_id=period.json()["id"]
                )
                prepared = await prepare(
                    c,
                    h,
                    options,
                    eid,
                    f"/api/v1/engagements/{eid}/audit",
                    country,
                    configured=True,
                    actors=(partner, None),
                )
                for target in (
                    "ACCEPTANCE_PENDING",
                    "ACCEPTED",
                    "PLANNING",
                    "RISK_ASSESSMENT",
                    "FIELDWORK",
                ):
                    await move(c, prepared, target)
                if case != "current":
                    _, snapshot = await replace_ledger(c, prepared)
                    if case == "reassessed":
                        await reassess(c, prepared, snapshot)
                checks = (await c.get(prepared["base"] + "/completion-checks", headers=h)).json()
                assert checks["ready"] == (case != "stale"), checks
                saved["countries"][country][case] = dict(
                    engagement=eid,
                    expected_ready=checks["ready"],
                    affected_records=[
                        prepared[key]["id"] for key in ("testing", "paper", "completion")
                    ]
                    if case == "stale"
                    else [],
                    checked_records=next(
                        check["checked_records"]
                        for check in checks["checks"]
                        if check["code"] == "reviewed_source_freshness"
                    ),
                )
        (ROOT / ".local-runtime/country-workflows/completion-fixture.json").write_text(
            json.dumps(saved, indent=2) + "\n", encoding="utf-8"
        )
        print("Saved six synthetic UAE/India completion freshness cases")
    finally:
        patch.undo()
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

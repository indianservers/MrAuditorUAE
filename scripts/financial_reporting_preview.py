"""Reset the explicitly disposable CRUD test database and prepare browser fixtures.

Run only after integration tests, via financial_reporting_run.py. Never targets demo/live data.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def main():
    from app.core.config import settings

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_financial_workflow_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit("Only the disposable auditos_financial_workflow_test database is allowed")
    from tests.integration.test_platform import environment
    from tests.phase2.test_pipeline import committed
    from tests.phase4.test_workflows import setup
    from tests.phase5.test_reporting import CSV, prepared

    fixture = environment.__wrapped__()
    c = await anext(fixture)
    try:
        h, opts, eid, base = await setup(c)
        p = await c.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": opts["entity_id"],
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            },
        )
        assert p.status_code == 201, p.text
        _, prior = await committed(
            c,
            h,
            {
                **opts,
                "period_id": p.json()["id"],
                "expected_rows": 6,
                "expected_debit": "170",
                "expected_credit": "170",
            },
            CSV.replace(b"2026-", b"2025-").replace(b"500,Expense", b"600,Old expense"),
        )
        _, _, _, _reviewer, _partner, profile, _mapping, _note, _ready = await prepared(
            c, (h, opts, eid, base)
        )
        api = f"/api/v1/ifrs/engagements/{eid}"
        run = await c.post(api + "/financial-statements/" + profile["id"], headers=h)
        assert run.status_code == 201, run.text
        data = {
            "synthetic": True,
            "engagement_id": eid,
            "profile_id": profile["id"],
            "run_id": run.json()["id"],
            "snapshot_id": profile["body"]["snapshot_id"],
            "prior_snapshot_id": prior,
            **{k: opts[k] for k in ("client_id", "entity_id", "period_id")},
        }
        target = (
            Path(__file__).resolve().parents[1]
            / ".local-runtime/financial-reporting/fixture.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2))
        print(
            "Synthetic financial workflow fixture prepared in disposable test database"
        )
    finally:
        await fixture.aclose()


if __name__ == "__main__":
    asyncio.run(main())

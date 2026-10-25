"""Read-only paired history benchmark against the owned synthetic preview DB.

Uses the same current implementation and complete JSON in both modes. Only
request-local reuse is disabled for the reference; no freshness receipt, source
hash or authorization check is overridden. Never targets production or pilots.
"""

import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def main():
    from app.core.config import settings
    from app.core.operations_contracts import country_workflow_hash
    from app.core.security import access_token
    from app.db.models.platform import User
    from app.db.session import Session, engine
    from app.main import app
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import event, select

    if (
        settings().environment != "test"
        or not settings().database_url.endswith("/auditos_country_workflows_test")
        or os.getenv("INTEGRATION_TESTS") != "1"
    ):
        raise SystemExit(
            "Only the owned disposable country workflow test database is allowed"
        )
    fixture = json.loads(
        (ROOT / ".local-runtime/country-workflows/fixture.json").read_text(
            encoding="utf-8"
        )
    )
    if fixture.get("synthetic") is not True:
        raise SystemExit("Explicitly synthetic preview fixtures required")
    implementation = country_workflow_hash()
    async with Session() as db:
        user = await db.scalar(select(User).where(User.email == "admin@example.com"))
        if user is None:
            raise SystemExit("Prepare synthetic preview fixtures first")
        headers = {
            "Authorization": "Bearer " + access_token(user.id),
            "X-Tenant-ID": fixture["tenant"],
        }
    results = []
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for country, eid in (
            ("AE", fixture["uae_engagement"]),
            ("IN", fixture["india_engagement"]),
        ):
            samples = []
            expected = None
            for index in range(3):
                for mode in (
                    ("reference", "reuse") if index % 2 == 0 else ("reuse", "reference")
                ):
                    queries = 0

                    def query(*args):
                        nonlocal queries
                        queries += 1

                    control = (
                        patch(
                            "app.core.read_projection.read_projection",
                            lambda *args: nullcontext(),
                        )
                        if mode == "reference"
                        else nullcontext()
                    )
                    event.listen(engine.sync_engine, "before_cursor_execute", query)
                    started = time.perf_counter()
                    try:
                        with control:
                            response = await client.get(
                                f"/api/v1/intelligence/engagements/{eid}/events?limit=100&newest=true",
                                headers=headers,
                            )
                    finally:
                        elapsed = time.perf_counter() - started
                        event.remove(engine.sync_engine, "before_cursor_execute", query)
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"History request failed with status {response.status_code}"
                        )
                    data = response.json()
                    if expected is None:
                        expected = data
                    if (
                        data != expected
                        or len(data["items"]) != 100
                        or not any(
                            row["freshness"] == "CURRENT" for row in data["items"]
                        )
                    ):
                        raise RuntimeError(
                            "Equal, full, currently qualified synthetic history pages required"
                        )
                    samples.append(
                        {"mode": mode, "seconds": round(elapsed, 6), "queries": queries}
                    )
            summary = {
                mode: {
                    "median_seconds": round(
                        statistics.median(
                            row["seconds"] for row in samples if row["mode"] == mode
                        ),
                        6,
                    ),
                    "queries": [
                        row["queries"] for row in samples if row["mode"] == mode
                    ],
                }
                for mode in ("reference", "reuse")
            }
            if (
                max(summary["reuse"]["queries"])
                >= min(summary["reference"]["queries"]) / 2
            ):
                raise RuntimeError("History query reduction below the verified target")
            results.append(
                {
                    "country": country,
                    "items": 100,
                    "results_equal": True,
                    "payload_sha256": hashlib.sha256(
                        json.dumps(
                            expected, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    "current": sum(
                        row["freshness"] == "CURRENT" for row in expected["items"]
                    ),
                    "summary": summary,
                    "samples": samples,
                }
            )
    if implementation != country_workflow_hash():
        raise RuntimeError(
            "Implementation changed during measurement; prepare and verify again"
        )
    report = {
        "classification": "SYNTHETIC_LOCAL_HISTORY_BENCHMARK_NOT_A_PRODUCTION_SLA",
        "measured_at": datetime.now(UTC).isoformat(),
        "implementation_sha256": implementation,
        "method": "Same complete JSON and implementation; request reuse off versus on; three alternating pairs per country",
        "limits": "Owned local DB/ASGI/object fixtures, one actor, sequential requests; excludes network, concurrent polling, large tenants and production capacity",
        "results": results,
    }
    destination = ROOT / "docs/phase-12/history-projection-benchmark.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(destination),
                "results": [
                    {"country": row["country"], **row["summary"]} for row in results
                ],
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

"""Measure a source-specific configuration beside defaults; preserve both outputs."""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.db.session import Session, engine, tenant_context
from app.main import app
from app.modules.accounting.models import Finding, JournalLine, SourceRecord
from qa_campaign import guard
from sqlalchemy import select


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    baseline = json.loads((out / "exception-results.json").read_text(encoding="utf8"))
    parameters = {
        "snapshot_id": baseline["snapshot_id"],
        "year_end": "2026-12-31",
        "near_duplicate_ratio": "0",
        "velocity_limit": 500,
    }
    # The fixture deliberately contains100similar low-value automated sales in one day.
    # Exact duplicates, cutoff, unusual descriptions and all other rules stay enabled.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=300,
    ) as c:
        login = await c.post(
            "/api/v1/auth/login",
            data={
                "username": "qa.admin@auditos.example",
                "password": os.environ["QA_PASSWORD"],
            },
        )
        h = {
            "Authorization": "Bearer " + login.json()["access_token"],
            "X-Tenant-ID": data["tenant_id"],
        }
        r = await c.post("/api/v1/analytics/runs", headers=h, json=parameters)
        assert r.status_code == 201, r.text
        run = r.json()
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, data["tenant_id"])
        normal = {
            str(i)
            for i in (
                await db.scalars(
                    select(JournalLine.id)
                    .join(SourceRecord, SourceRecord.id == JournalLine.source_record_id)
                    .where(
                        JournalLine.snapshot_id == uuid.UUID(baseline["snapshot_id"]),
                        SourceRecord.source_id.startswith("QA-NORMAL-"),
                    )
                )
            ).all()
        }
        flags = {
            (str(line), rule)
            for line, rule in (
                await db.execute(
                    select(Finding.line_id, Finding.rule_id).where(
                        Finding.run_id == uuid.UUID(run["id"])
                    )
                )
            ).all()
        }
    evaluations = [
        {
            **case,
            "actual_rules": sorted(
                rule for line, rule in flags if line == case["line_id"]
            ),
            "missed_rules": sorted(
                rule
                for rule in case["expected_rules"]
                if (case["line_id"], rule) not in flags
            ),
        }
        for case in baseline["evaluations"]
    ]
    result = {
        "run_id": run["id"],
        "parameters": parameters,
        "rationale": "Known source has100similar automated sales perday; configuration changes are explicit and must not generalize without validation. Default evidence retained.",
        "normal_lines": len(normal),
        "normal_lines_flagged": len({line for line, _ in flags if line in normal}),
        "missed_direct_rule_cases": sum(bool(e["missed_rules"]) for e in evaluations),
        "evaluations": evaluations,
        "rules": run["result"]["rules"],
        "production_promoted": False,
    }
    (out / "calibrated-exception-results.json").write_text(
        json.dumps(result, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"evaluations", "rules"}}
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

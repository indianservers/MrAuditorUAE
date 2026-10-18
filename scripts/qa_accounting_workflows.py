"""Persist real TB, reconciliation and sample results for each QA client snapshot."""

import asyncio
import csv
import hashlib
import io
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.db.session import Session, engine
from app.main import app
from qa_campaign import guard, journal_csv


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    async with Session() as db:
        await guard(db)
    evidence = out / "accounting-workflow-results.json"
    results = (
        json.loads(evidence.read_text(encoding="utf8")) if evidence.exists() else []
    )
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
        assert login.status_code == 200
        h = {
            "Authorization": "Bearer " + login.json()["access_token"],
            "X-Tenant-ID": data["tenant_id"],
        }
        for index, batch in enumerate(data["batches"]):
            if any(r["snapshot_id"] == batch["snapshot_id"] for r in results):
                continue
            company = next(
                x for x in data["companies"] if x["name"] == batch["company"]
            )
            scope = {k: company[k] for k in ["client_id", "entity_id", "period_id"]}
            year = 2026 - index // 25
            if year != 2026:
                scope["period_id"] = company["scale_periods"][str(year)]
            assignments = {}
            totals = {}
            source, _ = journal_csv(index * 10000, 10000, year)
            assert hashlib.sha256(source).hexdigest() == batch["sha256"]
            for row in csv.DictReader(io.StringIO(source.decode())):
                code = row["Account Code"]
                totals.setdefault(code, [Decimal(0), Decimal(0)])
                totals[code][0] += Decimal(row["Debit"])
                totals[code][1] += Decimal(row["Credit"])
                assignments[code] = {
                    "classification": "Assets"
                    if int(code) < 200
                    else "Liabilities"
                    if int(code) < 300
                    else "Equity"
                    if int(code) < 400
                    else "Income"
                    if int(code) < 500
                    else "Expenses",
                    "contra": code == "141",
                }
            mapping = await c.post(
                "/api/v1/accounting/mappings",
                headers=h,
                json={
                    **scope,
                    "name": "QA source chart mapping",
                    "approved": True,
                    "mapping": {"accounts": assignments},
                },
            )
            assert mapping.status_code == 201, mapping.text
            stream = io.StringIO()
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                [
                    "Account Code",
                    "Account Name",
                    "Opening Balance",
                    "Debit",
                    "Credit",
                    "Closing Balance",
                    "Source ID",
                ]
            )
            for code, (debit, credit) in sorted(totals.items()):
                writer.writerow(
                    [
                        code,
                        code,
                        "0",
                        str(debit),
                        str(credit),
                        str(debit - credit),
                        "QA-TB-" + code,
                    ]
                )
            options = {
                **scope,
                "kind": "tb",
                "expected_rows": len(totals),
                "expected_debit": batch["debit"],
                "expected_credit": batch["credit"],
                "source_complete": True,
            }
            imported = await c.post(
                "/api/v1/accounting/imports",
                headers=h,
                data={"options": json.dumps(options)},
                files={
                    "file": (
                        "QA-INDEPENDENT-TB.csv",
                        stream.getvalue().encode(),
                        "text/csv",
                    )
                },
            )
            assert imported.status_code == 201, imported.text
            bid = imported.json()["id"]
            for action in ["validate", "commit"]:
                r = await c.post(
                    f"/api/v1/accounting/imports/{bid}/{action}", headers=h
                )
                assert r.status_code == 200, r.text
            comparison = (
                await c.get("/api/v1/accounting/imports/" + bid, headers=h)
            ).json()["snapshot_id"]
            record = {"snapshot_id": batch["snapshot_id"], "company": batch["company"]}
            for path, body in [
                ("accounting/trial-balance", {"snapshot_id": batch["snapshot_id"]}),
                (
                    "reconciliation/runs",
                    {
                        "snapshot_id": batch["snapshot_id"],
                        "comparison_snapshot_id": comparison,
                        "tolerance": "0",
                    },
                ),
                (
                    "sampling/runs",
                    {
                        "snapshot_id": batch["snapshot_id"],
                        "method": "random",
                        "size": 10,
                        "seed": 2026,
                    },
                ),
            ]:
                response = await c.post("/api/v1/" + path, headers=h, json=body)
                assert response.status_code < 400, (
                    path,
                    response.status_code,
                    response.text,
                )
                result = response.json()
                record[path] = {
                    "id": result["id"],
                    "status": result["status"],
                    "result": result.get("result", {}),
                }
                assert result["status"] in {"completed", "balanced", "passed"}, result
            results.append(record)
            evidence.write_text(json.dumps(results, indent=2), encoding="utf8")
    (out / "accounting-workflow-results.json").write_text(
        json.dumps(results, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {"client_snapshots": len(results), "persisted_runs": len(results) * 3}
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

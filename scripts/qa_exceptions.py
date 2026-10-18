"""Independent labeled journal cases run through real import and persisted analytics."""

import asyncio
import csv
import io
import json
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.db.session import Session, engine, tenant_context
from app.main import app
from app.modules.accounting.models import Finding, JournalLine, SourceRecord
from qa_campaign import guard
from sqlalchemy import select

NAMES = [
    "Duplicate supplier payments",
    "Duplicate invoices",
    "Unusual revenue",
    "Year end anomaly",
    "Incorrect account combination",
    "Suspense balance",
    "Unexpected credit note",
    "Missing invoice reference",
    "Round number",
    "Reversal anomaly",
    "Related party misclassification",
    "Expense capitalization",
    "VAT coding",
    "Unreconciled balance",
    "Unsupported accrual",
    "Unusual vendor activity",
    "SoD conflict",
    "Incomplete support",
    "Incorrect FS mapping",
    "Review failure",
]


async def main():
    out = ROOT / "docs/qa-campaign"
    data = json.loads((out / "dataset.json").read_text(encoding="utf8"))
    async with Session() as db:
        await guard(db)
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

        async def post(path, body):
            r = await c.post("/api/v1/" + path, headers=h, json=body)
            assert r.status_code < 400, (path, r.status_code, r.text)
            return r.json()

        company = data["companies"][24]
        entity = await post(
            "entities",
            {
                "client_id": company["client_id"],
                "name": "QA FICTIONAL labeled exception lab",
                "country": "AE",
                "jurisdiction": "SYNTHETIC QA",
                "functional_currency": "AED",
                "presentation_currency": "AED",
            },
        )
        period = await post(
            "financial-periods",
            {
                "entity_id": entity["id"],
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
        scope = {
            "client_id": company["client_id"],
            "entity_id": entity["id"],
            "period_id": period["id"],
        }
        rows = []
        labels = []

        def journal(
            ref,
            amount,
            day="2026-06-02",
            a="101",
            b="400",
            description="SYNTHETIC normal sale",
            manual=False,
        ):
            for leg, code in enumerate([a, b]):
                rows.append(
                    [
                        code,
                        "Suspense" if code == "999" else code,
                        ref,
                        day,
                        str(amount if leg == 0 else 0),
                        str(amount if leg else 0),
                        ref + "-" + str(leg),
                        "false",
                        str(manual).lower(),
                        description,
                    ]
                )

        for i in range(100):
            journal(f"QA-NORMAL-{i}", Decimal("151.13") + Decimal(i) / 100)
        expected_rules = {
            0: ["J05"],
            1: ["J05"],
            2: ["J07"],
            3: ["J10"],
            4: ["J12"],
            5: ["J16"],
            8: ["J04"],
            14: ["J07"],
        }
        for i, name in enumerate(NAMES):
            ref = f"QA-LABEL-{i:02}"
            amount = Decimal(10000) if i == 8 else Decimal("723.91")
            if i in {0, 1}:
                amount = Decimal("999.37")
            a, b = (
                ("400", "101")
                if i == 4
                else ("999", "101")
                if i == 5
                else ("520", "210")
                if i == 14
                else ("101", "400")
            )
            description = (
                "SYNTHETIC manual override unsupported adjustment"
                if i in {2, 14}
                else "SYNTHETIC " + name
            )
            journal(
                ref,
                amount,
                "2026-12-31" if i == 3 else "2026-06-02",
                a,
                b,
                description,
                i == 3,
            )
            labels.append(
                {
                    "case": name,
                    "source_id": ref + "-0",
                    "expected_rules": expected_rules.get(i, []),
                    "coverage": "DIRECT_RULE"
                    if i in expected_rules
                    else "REQUIRES_NON_GL_WORKFLOW_CONTEXT",
                    "not_a_fraud_conclusion": True,
                }
            )
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "Account Code",
                "Account Name",
                "Journal Number",
                "Posting Date",
                "Debit",
                "Credit",
                "Source ID",
                "Opening",
                "Manual",
                "Narration",
            ]
        )
        writer.writerows(rows)
        payload = stream.getvalue().encode()
        total = sum(Decimal(r[4]) for r in rows)
        (out / "exception-labels.json").write_text(
            json.dumps(labels, indent=2), encoding="utf8"
        )
        r = await c.post(
            "/api/v1/accounting/imports",
            headers=h,
            data={
                "options": json.dumps(
                    {
                        **scope,
                        "expected_rows": len(rows),
                        "expected_debit": str(total),
                        "expected_credit": str(total),
                        "source_complete": True,
                    }
                )
            },
            files={"file": ("QA-EXCEPTIONS.csv", payload, "text/csv")},
        )
        assert r.status_code == 201, r.text
        bid = r.json()["id"]
        await post(f"accounting/imports/{bid}/validate", None)
        await post(f"accounting/imports/{bid}/commit", None)
        detail = (await c.get("/api/v1/accounting/imports/" + bid, headers=h)).json()
        await post(
            "accounting/mappings",
            {
                **scope,
                "name": "QA labeled population",
                "approved": True,
                "mapping": {
                    "accounts": {
                        "101": {"classification": "Assets"},
                        "400": {"classification": "Income"},
                        "520": {"classification": "Expenses"},
                        "210": {"classification": "Liabilities"},
                        "999": {"classification": "Assets", "source_group": "suspense"},
                    }
                },
            },
        )
        run = await post(
            "analytics/runs",
            {"snapshot_id": detail["snapshot_id"], "year_end": "2026-12-31"},
        )
        async with Session() as db, db.begin():
            await tenant_context(db, data["tenant_id"])
            sources = dict(
                (
                    await db.execute(
                        select(SourceRecord.source_id, JournalLine.id)
                        .join(
                            JournalLine, JournalLine.source_record_id == SourceRecord.id
                        )
                        .where(SourceRecord.batch_id == uuid.UUID(bid))
                    )
                ).all()
            )
            findings = (
                await db.execute(
                    select(Finding.line_id, Finding.rule_id).where(
                        Finding.run_id == uuid.UUID(run["id"])
                    )
                )
            ).all()
        flags = {(str(line), rule) for line, rule in findings}
        evaluations = []
        for label in labels:
            identifier = str(sources[label["source_id"]])
            actual = sorted(rule for line, rule in flags if line == identifier)
            evaluations.append(
                {
                    **label,
                    "line_id": identifier,
                    "actual_rules": actual,
                    "missed_rules": sorted(set(label["expected_rules"]) - set(actual)),
                }
            )
        normals = {
            str(value) for key, value in sources.items() if key.startswith("QA-NORMAL-")
        }
        summary = {
            "run_id": run["id"],
            "snapshot_id": detail["snapshot_id"],
            "labeled_cases": len(labels),
            "direct_rule_cases": len(expected_rules),
            "missed_direct_rule_cases": sum(
                bool(e["missed_rules"]) for e in evaluations
            ),
            "normal_lines": len(normals),
            "normal_lines_flagged": len({line for line, _ in flags if line in normals}),
            "false_positive_definition": "Any indicator on a deliberately normal line; indicators are review signals, not fraud diagnoses",
            "rules": run["result"]["rules"],
            "evaluations": evaluations,
        }
        (out / "exception-results.json").write_text(
            json.dumps(summary, indent=2), encoding="utf8"
        )
        print(
            json.dumps(
                {k: v for k, v in summary.items() if k not in {"rules", "evaluations"}}
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

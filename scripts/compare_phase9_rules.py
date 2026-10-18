"""Compare actual Phase 2 rule engine with held-out fixture labels; no retraining."""

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db.session import Session, engine, tenant_context
from app.modules.audit_analytics.engine import VERSION, AnalyticsEngine
from app.modules.audit_analytics.schemas import AnalyticsRequest
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.ml.models import MLEvent
from app.modules.ml.service import read_object

ROOT = Path(__file__).resolve().parents[1]


async def main():
    manifest = json.loads((ROOT / "docs/phase-9/demo-dataset.json").read_text())
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        source = await db.get(MLEvent, uuid.UUID(manifest["dataset_id"]))
    data = json.loads(read_object(source.body["object"]))
    rows = [
        r
        for i, r in enumerate(data["rows"])
        if data["split"][i] == "test" and "label" in r
    ]
    population = [
        {
            "id": r["id"],
            "account_code": r["account"],
            "journal_ref": r["journal"],
            "posting_date": r["date"],
            "debit": str(r["debit"]),
            "credit": str(r["credit"]),
            "description": r["description"],
            "counterparty": r.get("counterparty"),
            "manual": r.get("manual"),
            "category": ["Assets", "Liabilities", "Equity", "Income", "Expenses"][
                r["category"]
            ],
        }
        for r in rows
    ]
    rules = AnalyticsEngine(population)
    try:
        summaries = rules.evaluate(
            AnalyticsRequest(snapshot_id=uuid.uuid4(), year_end="2025-12-31")
        )
        flagged = {
            x[0] for x in rules.db.execute("SELECT DISTINCT id FROM flags").fetchall()
        }
        tp = sum(bool(r["label"]) and r["id"] in flagged for r in rows)
        fp = sum(not r["label"] and r["id"] in flagged for r in rows)
        fn = sum(bool(r["label"]) and r["id"] not in flagged for r in rows)
        tn = len(rows) - tp - fp - fn
        precision = tp / (tp + fp or 1)
        recall = tp / (tp + fn or 1)
        report = {
            "engine_version": VERSION,
            "dataset_id": manifest["dataset_id"],
            "held_out_rows": len(rows),
            "parameters": "Existing AnalyticsRequest defaults; year_end 2025-12-31; no labels supplied to rule engine",
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall or 1),
            "false_positive_rate": fp / (fp + tn or 1),
            "confusion_matrix": [[tn, fp], [fn, tp]],
            "rules": summaries,
            "scope": "Any actual Phase 2 rule flag, not a confirmed fraud/misstatement label; not comparable to five-way account category accuracy",
        }
        (ROOT / "docs/phase-9/existing-rule-comparison.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n"
        )
    finally:
        rules.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

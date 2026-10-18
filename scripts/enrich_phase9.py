"""Guarded synthetic ML dataset; never edits accounting facts or infers labels from rules."""

import asyncio
import json
import random
import sys
import uuid
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import select

from app.core.dependencies import Context
from app.db.session import Session, engine, tenant_context
from app.modules.accounting.models import Account, JournalLine
from app.modules.demo.guard import DEMO_TENANT, guard
from app.modules.ml import service
from app.modules.ml.models import MLEvent

ROOT = Path(__file__).resolve().parents[1]


def fixtures(seed=2026):
    rng = random.Random(seed)
    rows = []
    splits = []
    names = [
        "Bank current cash",
        "Supplier payable liability",
        "Owner capital equity",
        "Sales revenue income",
        "Payroll operating expense",
    ]
    patterns = [
        "normal",
        "duplicate",
        "unusual_account",
        "amount",
        "cutoff",
        "reversal",
    ]
    for split, n in [
        ("train", 3600),
        ("validation", 1200),
        ("test", 1200),
        ("ood", 600),
    ]:
        for i in range(n):
            category = i % 5
            label = int(i % 7 == 0)
            scenario = patterns[1 + i % 5] if label else "normal"
            amount = round(rng.uniform(100, 15000), 2)
            day = date(2025, 1, 1) + timedelta(days=rng.randrange(300))
            description = [
                "Customer receipt",
                "Supplier invoice",
                "Payroll accrual",
                "Depreciation expense",
                "Interest settlement",
                "Inventory purchase",
                "Bank payment",
                "Standard reversal",
            ][i % 8]
            manual = False
            if scenario == "amount":
                amount = 100000 * (1 + i % 7)
                manual = True
            elif scenario == "cutoff":
                day = date(2025, 12, 31)
                amount *= 8
            elif scenario == "reversal":
                description = "Unusual manual reversing adjustment"
                manual = True
                amount *= 20
            elif scenario == "unusual_account":
                description = "Manual exceptional account combination"
                manual = True
                category = (category + 2) % 5
                amount *= 12
            elif scenario == "duplicate":
                description = "Repeated payment reference"
                amount = 50000
                manual = True
            if split == "ood":
                amount *= 3.17
                description = "Unseen acquisition settlement " + description
            journal = f"p9-{split}-{i}"
            client = f"SYNTHETIC-{split}"
            uid = str(uuid.uuid5(DEMO_TENANT, journal))
            # A complete balanced journal lives entirely in one split.
            for leg in range(2):
                rows.append(
                    {
                        "id": uid + f"-{leg}",
                        "journal": journal,
                        "client": client,
                        "date": day.isoformat(),
                        "debit": amount if leg == 0 else 0,
                        "credit": amount if leg else 0,
                        "currency": ["AED", "USD", "EUR"][i % 3],
                        "functional_currency": "AED",
                        "description": description,
                        "account": str(category if leg == 0 else 0),
                        "counterparty": f"Fixture party {i % 37}",
                        "manual": manual,
                        "label": label,
                        "label_kind": "synthetic_injected"
                        if label
                        else "synthetic_normal",
                        "category": category if leg == 0 else 0,
                        "account_name": names[category if leg == 0 else 0]
                        + f" division {split} {i % 11}",
                    }
                )
                splits.append(split)
    return rows, splits


async def main():
    manifest = json.loads((ROOT / "docs/phase-7/demo-manifest.json").read_text())
    entry = next(x for x in manifest["engagements"] if x["year"] == 2026)
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, str(DEMO_TENANT))
        existing = await db.scalar(
            select(MLEvent).where(
                MLEvent.kind == "dataset",
                MLEvent.tenant_id == DEMO_TENANT,
                MLEvent.body["seed_version"].astext == "phase9-v2",
            )
        )
        if existing:
            print(json.dumps({"dataset_id": str(existing.id), "replayed": True}))
            return
        query = (
            select(JournalLine, Account.name)
            .join(Account, Account.id == JournalLine.account_id)
            .where(JournalLine.tenant_id == DEMO_TENANT)
            .order_by(JournalLine.posting_date, JournalLine.id)
        )
        rows = []
        splits = []
        for r, name in (await db.execute(query)).all():
            rows.append(
                {
                    "id": str(r.id),
                    "journal": str(r.journal_id),
                    "client": str(r.client_id),
                    "date": str(r.posting_date),
                    "debit": float(r.base_debit),
                    "credit": float(r.base_credit),
                    "currency": r.currency,
                    "functional_currency": r.functional_currency,
                    "description": r.description,
                    "account": str(r.account_id),
                    "account_name": name,
                    "counterparty": r.counterparty,
                    "label_kind": "unknown",
                    "snapshot_id": str(r.snapshot_id),
                }
            )
            splits.append("train" if r.posting_date.year < 2025 else "test")
        count = len(rows)
        f, sp = fixtures()
        rows += f
        splits += sp
        data = {"rows": rows, "split": splits, "synthetic": True}
        meta = service.put_json(DEMO_TENANT, data)
        ctx = Context(uuid.UUID(manifest["users"][1]["id"]), DEMO_TENANT, frozenset())
        obj = await service.event(
            db,
            ctx,
            uuid.UUID(entry["id"]),
            "dataset",
            {
                "seed_version": "phase9-v2",
                "object": meta,
                "synthetic": True,
                "source_rows": count,
                "fixture_rows": len(f),
                "total_rows": len(rows),
                "splits": dict(Counter(splits)),
                "labels": dict(Counter(r["label_kind"] for r in rows)),
                "split_method": "Source chronological, unknown excluded from supervised fitting; controlled fixtures client-separated and journal-grouped",
                "scope": "Guarded isolated demo tenant only; no cross-tenant pooling",
            },
        )
        summary = {
            "dataset_id": str(obj.id),
            "engagement_id": entry["id"],
            **{k: v for k, v in obj.body.items() if k != "object"},
        }
        (ROOT / "docs/phase-9/demo-dataset.json").write_text(
            json.dumps(summary, indent=2) + "\n"
        )
        print(json.dumps(summary))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

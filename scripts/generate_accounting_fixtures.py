"""Generate clearly fictional Phase 2 correctness fixtures; no production seeding."""

import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "backend/tests/fixtures/phase2"
root.mkdir(parents=True, exist_ok=True)
columns = [
    "account_code",
    "account_name",
    "journal_ref",
    "posting_date",
    "document_date",
    "debit",
    "credit",
    "source_id",
    "opening",
    "manual",
    "description",
    "currency",
    "reversal_ref",
    "counterparty",
]
rows = []
names = {
    "100": "Cash",
    "300": "Equity",
    "500": "Expense",
    "999": "Suspense",
    "777": "Unmapped account",
}


def journal(
    ref, day, debit_account, credit_account, amount, opening=False, manual=False, reversal=""
):
    for n, (code, debit, credit) in enumerate(
        [(debit_account, amount, "0"), (credit_account, "0", amount)], 1
    ):
        rows.append(
            dict(
                account_code=code,
                account_name=names[code],
                journal_ref=ref,
                posting_date=day,
                document_date=day,
                debit=debit,
                credit=credit,
                source_id=ref + ":" + str(n),
                opening=str(opening).lower(),
                manual=str(manual).lower(),
                description="SYNTHETIC "
                + ("year-end manual adjustment" if manual else "fixture transaction"),
                currency="AED",
                reversal_ref=reversal,
                counterparty="FICTIONAL Test Supplier",
            )
        )


journal("OPEN", "2026-01-01", "100", "300", "10000", True)
journal("100", "2026-06-01", "500", "100", "100")
journal("101", "2026-06-01", "500", "100", "100")
journal("103", "2026-12-26", "500", "100", "250000")
journal("104", "2026-12-31", "500", "100", "750000", manual=True)
journal("105", "2026-12-30", "999", "100", "700")
journal("106", "2026-12-31", "100", "500", "100", reversal="100")
journal("107", "2026-12-29", "777", "100", "300")
rows[-1]["source_id"] = ""
for filename, data in [
    ("synthetic-general-ledger.csv", rows),
    ("synthetic-journals.csv", rows),
    ("synthetic-unbalanced.csv", [*rows[:-1], {**rows[-1], "credit": "299"}]),
]:
    with (root / filename).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)
with (root / "synthetic-chart-of-accounts.csv").open("w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["account_code", "account_name"])
    writer.writerows(names.items())
with (root / "synthetic-opening-balances.csv").open("w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows[:2])
totals = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
for row in rows:
    target = totals[row["account_code"]]
    debit, credit = Decimal(row["debit"]), Decimal(row["credit"])
    if row["opening"] == "true":
        target[0] += debit - credit
    else:
        target[1] += debit
        target[2] += credit
with (root / "synthetic-trial-balance.csv").open("w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(
        ["account_code", "account_name", "opening_balance", "debit", "credit", "closing_balance"]
    )
    for code, (opening, debit, credit) in sorted(totals.items()):
        writer.writerow([code, names[code], opening, debit, credit, opening + debit - credit])
manifest = {
    "synthetic": True,
    "company": "FICTIONAL Gulf Example LLC — synthetic test only",
    "rows": len(rows),
    "debit": str(sum(Decimal(r["debit"]) for r in rows)),
    "credit": str(sum(Decimal(r["credit"]) for r in rows)),
    "fixtures": [
        "balanced journals",
        "unbalanced import (separate file)",
        "duplicate journals",
        "weekend posting",
        "year-end adjustment",
        "large expense",
        "unmapped account",
        "missing source reference",
        "reversal",
    ],
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Wrote synthetic fixtures:", root)

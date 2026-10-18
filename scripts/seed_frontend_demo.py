"""Create clearly labeled synthetic browser-test records through the real API.

Requires DEMO_SEED=1 and a disposable local backend. Never resets existing data.
Credentials are the disposable integration-test account, not production defaults.
"""

import csv
import io
import json
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx


def main():
    raise SystemExit("Legacy preview seeding is disabled: use the guarded Phase 7 seed-demo command against its explicit demo database and tenant.")
    if os.getenv("DEMO_SEED") != "1":
        raise SystemExit("Set DEMO_SEED=1 only against the disposable local test backend")
    root = Path(__file__).resolve().parents[1]
    with httpx.Client(base_url="http://127.0.0.1:58000/api/v1", timeout=120) as client:

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        tokens = call(
            "POST",
            "/auth/login",
            data={"username": "admin@example.com", "password": "test-strong-password-123"},
        )
        client.headers["Authorization"] = "Bearer " + tokens["access_token"]
        tenants = call("GET", "/tenants")
        client.headers["X-Tenant-ID"] = tenants[0]["id"]
        code = "UI_" + uuid.uuid4().hex[:8]
        customer = call(
            "POST",
            "/clients",
            json={"code": code, "name": "SYNTHETIC — Gulf Example Group", "kind": "group"},
        )
        entity = call(
            "POST",
            "/entities",
            json={
                "client_id": customer["id"],
                "name": "SYNTHETIC — Example Trading LLC",
                "country": "AE",
                "jurisdiction": "Synthetic test only",
                "functional_currency": "AED",
                "presentation_currency": "AED",
            },
        )
        period = call(
            "POST",
            "/financial-periods",
            json={"entity_id": entity["id"], "start_date": "2026-01-01", "end_date": "2026-12-31"},
        )
        engagement = call(
            "POST",
            "/engagements",
            json={
                "entity_id": entity["id"],
                "period_id": period["id"],
                "name": "SYNTHETIC — FY2026 External Audit",
                "engagement_type": "External Audit",
                "status": "active",
            },
        )
        rows = []
        names = {
            "1100": "Cash and bank balances",
            "1200": "Trade receivables",
            "2100": "Trade payables",
            "4100": "Sales revenue",
            "5100": "Operating expenses",
            "5200": "Professional fees",
        }
        for i in range(1, 91):
            amount = Decimal(i * 751 if i % 5 else 100000 + i * 1000).quantize(Decimal("0.01"))
            debit, credit = [
                ("1100", "4100"),
                ("5100", "2100"),
                ("1200", "4100"),
                ("5200", "1100"),
            ][i % 4]
            posting = date(2026, 1, 1) + timedelta(days=(i * 4) % 364)
            for side, account in enumerate([debit, credit]):
                rows.append(
                    [
                        account,
                        names[account],
                        f"SYN-{i:04d}",
                        posting.isoformat(),
                        str(amount if side == 0 else 0),
                        str(amount if side == 1 else 0),
                        f"SYN-L{i}-{side}",
                        "Synthetic year end adjustment"
                        if i % 5 == 0
                        else "Synthetic trading transaction",
                        "true",
                        "Synthetic counterparty",
                    ]
                )
        file = io.StringIO(newline="")
        writer = csv.writer(file)
        writer.writerow(
            [
                "Account Code",
                "Account Name",
                "Journal Number",
                "Posting Date",
                "Debit",
                "Credit",
                "Source ID",
                "Narration",
                "Manual",
                "Counterparty",
            ]
        )
        writer.writerows(rows)
        payload = file.getvalue().encode()
        options = {
            "client_id": customer["id"],
            "entity_id": entity["id"],
            "period_id": period["id"],
            "kind": "gl",
            "expected_rows": len(rows),
            "expected_debit": str(sum(Decimal(r[4]) for r in rows)),
            "expected_credit": str(sum(Decimal(r[5]) for r in rows)),
            "source_complete": True,
        }
        batch = call(
            "POST",
            "/accounting/imports",
            data={"options": json.dumps(options)},
            files={"file": ("SYNTHETIC-browser-fixture.csv", payload, "text/csv")},
        )
        call("POST", f"/accounting/imports/{batch['id']}/validate")
        call("POST", f"/accounting/imports/{batch['id']}/commit")
        details = call("GET", f"/accounting/imports/{batch['id']}")
        snapshot = details["snapshot_id"]
        classification = {
            "1100": "Assets",
            "1200": "Assets",
            "2100": "Liabilities",
            "4100": "Income",
            "5100": "Expenses",
            "5200": "Expenses",
        }
        call(
            "POST",
            "/accounting/mappings",
            json={
                **{k: options[k] for k in ["client_id", "entity_id", "period_id"]},
                "name": "Synthetic explicit classifications",
                "approved": True,
                "mapping": {
                    "accounts": {
                        code: {"classification": classification[code], "statement_group": name}
                        for code, name in names.items()
                    }
                },
            },
        )
        analytics = call(
            "POST",
            "/analytics/runs",
            json={"snapshot_id": snapshot, "materiality": "100000", "year_end": "2026-12-31"},
        )
        reconciliation = call("POST", "/reconciliation/runs", json={"snapshot_id": snapshot})
        evidence = {
            "synthetic": True,
            "client_id": customer["id"],
            "entity_id": entity["id"],
            "period_id": period["id"],
            "engagement_id": engagement["id"],
            "batch_id": batch["id"],
            "snapshot_id": snapshot,
            "analytics_run_id": analytics["id"],
            "reconciliation_run_id": reconciliation["id"],
            "rows": len(rows),
        }
        (root / "docs/phase-3/browser-fixture.json").write_text(json.dumps(evidence, indent=2))
        print(
            "Created labeled synthetic browser fixture: 180 lines, 6 accounts; no customer records."
        )


if __name__ == "__main__":
    main()

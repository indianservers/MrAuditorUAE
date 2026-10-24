"""Bounded, synthetic bank matching benchmark; excludes DB/I/O and professional accuracy."""

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.country_workflows.calculations import calculate  # noqa: E402
from app.modules.country_workflows.schemas import WorkflowInput  # noqa: E402

results = []
for size in [1000, 5000]:
    rows = [
        {
            "id": str(i),
            "account": "SYNTHETIC-BANK",
            "reference": f"SYNTHETIC-{i}",
            "date": "2026-06-01",
            "currency": "AED",
            "amount": str(i + 1),
            "counterparty": "Synthetic customer",
        }
        for i in range(size)
    ]
    total = str(size * (size + 1) // 2)
    sources = {
        r: {
            "table_type": "transactions",
            "rows": [{**row, "id": r + row["id"]} for row in rows],
            "control_totals": {"AED": total},
        }
        for r in ["books", "statement"]
    }
    data = WorkflowInput(
        workflow="bank-brs",
        source_ids={r: uuid.uuid4() for r in sources},
        as_of="2026-06-30",
        title="Synthetic performance scenario",
        rationale="Bounded matching benchmark excluding storage and review",
        account="SYNTHETIC-BANK",
        book_opening="0",
        book_closing=total,
        statement_opening="0",
        statement_closing=total,
    )
    start = time.perf_counter()
    result = calculate(data, "AE", sources)
    elapsed = time.perf_counter() - start
    assert (
        len(result["matches"]) == size and not result["blocked"] and result["exception_count"] == 0
    )
    results.append(
        {"rows_per_side": size, "seconds": round(elapsed, 4), "matches": len(result["matches"])}
    )
output = {
    "synthetic": True,
    "scope": "In-process unique-reference/amount matching, excluding DB, parsing, worker queue and worst-case collisions",
    "results": results,
}
path = ROOT / "docs/country-workflows/performance.json"
path.write_text(json.dumps(output, indent=2))
print(json.dumps(output))

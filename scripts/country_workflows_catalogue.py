"""Publish scenario metadata and sample CSVs from executable synthetic fixtures."""

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tests.unit.country_workflow_cases import CASES  # noqa: E402

target = ROOT / "docs/country-workflows"
target.mkdir(exist_ok=True)
items = [{k: c[k] for k in ["id", "title", "workflow", "country", "expected"]} for c in CASES]
(ROOT / "backend/app/modules/country_workflows/scenarios.json").write_text(
    json.dumps(items, indent=2), encoding="utf-8"
)
(target / "scenario-matrix.json").write_text(
    json.dumps(
        {
            "synthetic": True,
            "count": len(CASES),
            "scope": "Operational evidence scenarios, not independently qualified laws or integrations",
            "items": items,
        },
        indent=2,
    ),
    encoding="utf-8",
)
samples = target / "sample-inputs"
samples.mkdir(exist_ok=True)
used = set()
for case in CASES:
    if case["workflow"] in used:
        continue
    used.add(case["workflow"])
    for role, rows in case["sources"].items():
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        (samples / f"{case['workflow']}-{role}.csv").write_text(
            buffer.getvalue(), encoding="utf-8", newline=""
        )
print(f"{len(CASES)} named synthetic scenarios; canonical examples for {len(used)} workflows")

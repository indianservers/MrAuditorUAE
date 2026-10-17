"""Fail CI when the aggregate calculation/validation core falls below its Phase 2 target."""

import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
paths = [
    "app/modules/accounting/calculations.py",
    "app/modules/accounting/service.py",
    "app/modules/ingestion/parser.py",
    "app/modules/audit_analytics/engine.py",
    "app/modules/audit_analytics/sampling.py",
    "app/modules/reconciliation/service.py",
]
statements = covered = 0
for name, info in report["files"].items():
    if name.replace("\\", "/") in paths:
        statements += info["summary"]["num_statements"]
        covered += info["summary"]["covered_lines"]
if not statements:
    raise SystemExit("No core coverage data found")
percentage = covered / statements * 100
print(f"Phase 2 calculation/validation core coverage: {percentage:.2f}% ({covered}/{statements})")
if percentage < 85:
    raise SystemExit("Core coverage is below 85%")

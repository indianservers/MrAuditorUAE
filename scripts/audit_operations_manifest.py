"""Summarize retained Phase 4 reports without including runtime credentials."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / "docs/engine-strengthening/phase4"
reports = {}
for name in ("unit-results.xml", "integration-results.xml", "frontend-results.xml"):
    tree = ET.parse(folder / name).getroot()
    cases = list(tree.iter("testcase"))
    failures = sum(c.find("failure") is not None for c in cases)
    errors = sum(c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    reports[name] = {
        "total": len(cases),
        "passed": len(cases) - failures - errors - skipped,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }
files = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(folder.iterdir())
    if path.is_file() and path.name != "verification.json"
}
manifest = {
    "scope": "labeled synthetic Phase 4 verification; no production validation claim",
    "reports": reports,
    "tensorflow": {
        "report": "tensorflow-results.txt",
        "passed": 7,
        "backend": "TensorFlow.js JavaScript CPU",
        "native_node_binding_installed": False,
        "language_credentials_required": False,
    },
    "other_checks": ["frontend tsc --noEmit", "frontend country-workflows eslint", "scoped backend ruff", "git diff --check"],
    "sha256": files,
}
(folder / "verification.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(reports, indent=2))

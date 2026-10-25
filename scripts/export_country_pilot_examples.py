"""Save existing synthetic input/expected-result fixtures without claiming client data."""

import hashlib
import json
import re
import runpy
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/tests/unit/country_workflow_cases.py"
DESTINATION = ROOT / "pilot-data/synthetic-examples"
COUNTRIES = {"AE": "UAE", "IN": "India"}


def export():
    cases = runpy.run_path(str(SOURCE))["CASES"]
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    counts = Counter()
    index = []
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]) or case["country"] not in COUNTRIES:
            raise ValueError("Unsupported synthetic scenario identity or country")
        country = COUNTRIES[case["country"]]
        folder = DESTINATION / country
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (case["id"] + ".json")
        document = {
            "dataset_kind": "SYNTHETIC_ENGINE_FIXTURE",
            "real_client_data": False,
            "professional_validation": "NOT_ESTABLISHED",
            "source_fixture": SOURCE.relative_to(ROOT).as_posix(),
            "source_fixture_sha256": source_hash,
            "case": case,
        }
        content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"Preserve the existing example before regenerating: {path}")
        path.write_text(content, encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8"))["case"] == case
        counts[country] += 1
        index.append({"id": case["id"], "country": case["country"], "workflow": case["workflow"], "file": f"{country}/{path.name}"})
    (DESTINATION / "catalog.json").write_text(json.dumps({
        "dataset_kind": "SYNTHETIC_ENGINE_FIXTURES_NOT_CLIENT_PILOTS",
        "source_fixture_sha256": source_hash,
        "scenario_count": len(cases), "counts_by_country": dict(counts), "cases": index,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Saved and verified {len(cases)} synthetic input/expected-result cases: {dict(counts)}")


if __name__ == "__main__":
    export()

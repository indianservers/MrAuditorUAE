"""Export current API and intelligence payload schemas; never runs jobs or deployment."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def contracts():
    from app.main import app
    from app.modules.country_workflows.schemas import ROW_TYPES
    from app.modules.country_workflows.uae_tax_group_workpaper import mapping_schema
    from app.modules.intelligence.schemas import OPERATIONS

    return {
        "docs/country-workflows/uae-tax-group-mapping.schema.json": mapping_schema(),
        "docs/phase-12/openapi.json": app.openapi(),
        "docs/country-workflows/job-input-contracts.json": {
            "contract": "intelligence-payload-contracts/1",
            "runtime_validation_required": True,
            "scope": "Structural payload schemas only. Country applicability, cross-field validators, authorization, retained evidence, freshness and review are enforced at runtime.",
            "operations": {
                name: {
                    "model": model.__name__,
                    "payload_schema": model.model_json_schema(),
                }
                for name, model in sorted(OPERATIONS.items())
            },
            "source_rows": {
                name: model.model_json_schema()
                for name, model in sorted(ROW_TYPES.items())
            },
        },
    }


def outdated(root, documents):
    changes = []
    for name, expected in documents.items():
        path = root / name
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            actual = None
        if actual != expected:
            changes.append(name)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Refuse stale snapshots without writing"
    )
    args = parser.parse_args()
    documents = contracts()
    changes = outdated(ROOT, documents)
    if args.check:
        if changes:
            raise SystemExit("Stale API contract snapshots: " + ", ".join(changes))
        print("API and intelligence payload snapshots match current runtime models")
        return
    for name, value in documents.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(
        f"Saved {len(documents)} current contract snapshots; regenerate frontend API types"
    )


if __name__ == "__main__":
    main()

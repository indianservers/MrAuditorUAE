"""Reproducible contract inventory. Discovery is explicitly not a passing test."""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app
from app.modules.audit_execution.catalogue import APPROVE, PREPARE
from app.modules.audit_execution.schemas import BODIES

OUT = ROOT / "docs/qa-crud"


def main():
    schema = app.openapi()
    endpoints = [
        {
            "path": path,
            "method": method.upper(),
            "operation": spec.get("operationId"),
            "tags": spec.get("tags", []),
        }
        for path, methods in schema["paths"].items()
        for method, spec in methods.items()
        if method in {"get", "post", "patch", "put", "delete"}
    ]
    tables = []
    for path in (ROOT / "backend/app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ClassDef):
                for statement in node.body:
                    if (
                        isinstance(statement, ast.Assign)
                        and any(
                            isinstance(t, ast.Name) and t.id == "__tablename__"
                            for t in statement.targets
                        )
                        and isinstance(statement.value, ast.Constant)
                    ):
                        tables.append(
                            {
                                "entity": node.name,
                                "table": statement.value.value,
                                "source": str(path.relative_to(ROOT)),
                                "coverage": "DISCOVERED; see executed receipts",
                            }
                        )
    drafts = {
        "working-papers",
        "risks",
        "vat-invoice",
        "requests",
        "planning",
        "programs",
        "procedures",
    }
    frontend_routes = {}
    for path in (ROOT / "frontend/src/features").glob("*.tsx"):
        source = path.read_text(encoding="utf8")
        for group in re.finditer(
            r"export const (\w+)Areas\s*=\s*\[([\s\S]*?)\]\s*as const", source
        ):
            family = group[1]
            for entry in re.finditer(
                r'\[\s*"([a-z0-9-]+)"\s*,\s*"[^"\n]+"(?:\s*,\s*"([a-z0-9-]+)")?\s*\]',
                group[2],
            ):
                area, kind = entry[1], entry[2] or entry[1]
                if family == "audit":
                    frontend_routes.setdefault(kind, []).append(
                        f"/engagements/{{eid}}/{area}"
                    )
                elif family in {"ifrs", "tax", "vat", "tp", "grc"}:
                    frontend_routes.setdefault(f"{family}-{kind}", []).append(
                        f"/{family}/{{eid}}/{area}"
                    )
    records = [
        {
            "entity": kind,
            "module": kind.split("-")[0],
            "frontend": frontend_routes.get(kind, []),
            "frontend_mapping": "source catalogue"
            if kind in frontend_routes
            else "No direct kind route mapped; inspect specialist sub-kind selector",
            "api": f"/api/v1/engagements/{{eid}}/audit/{kind}",
            "database": "audit_records + audit_record_versions + audit_review_decisions",
            "create": kind != "ai",
            "read": True,
            "edit": "AI proposal workflow only"
            if kind in {"ai", "tp-ai"}
            else "Editable states only; version required",
            "delete": False,
            "archive": kind in drafts,
            "restore": kind in drafts,
            "permissions": {"prepare": PREPARE.get(kind), "review": APPROVE.get(kind)},
            "side_effects": "Immutable revision and audit event; dependent calculations compare version/status on read",
            "dependencies": list(BODIES[kind].model_fields),
            "coverage": "NOT TESTED as a complete CRUD browser workflow",
        }
        for kind in sorted(BODIES)
    ]
    inventory = {
        "endpoints": endpoints,
        "tables": tables,
        "record_kinds": records,
        "warning": "Endpoint presence is not execution coverage. Specialist routes are listed separately in endpoints; dynamic audit kind routes resolve through this catalogue.",
    }
    (OUT / "crud-inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf8"
    )
    (OUT / "openapi.json").write_text(json.dumps(schema, indent=2), encoding="utf8")
    lines = [
        "# CRUD inventory",
        "",
        f"Discovered {len(endpoints)} HTTP operations, {len(tables)} mapped tables and {len(records)} typed audit record kinds. Full fields, route contracts, permissions and source locations are in crud-inventory.json and openapi.json.",
        "",
        "Discovery does not establish passing CRUD coverage. Source snapshots, journals, calculation runs, evidence versions, reviews and ML registry events preserve immutable history; replacement/reversal or append-only versions are required.",
        "",
    ]
    for r in records:
        lines += [
            f"- `{r['entity']}`: create/read; versioned edit in editable states; hard delete unavailable; draft archive/restore {'supported' if r['archive'] else 'unavailable (governed workflow required)'}. Prepare `{r['permissions']['prepare']}`; review `{r['permissions']['review']}`."
        ]
    (OUT / "crud-inventory.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "operations": len(endpoints),
                "tables": len(tables),
                "record_kinds": len(records),
            }
        )
    )


if __name__ == "__main__":
    main()

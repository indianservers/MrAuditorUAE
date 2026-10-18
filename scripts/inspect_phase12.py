"""Source and schema inventory. Discovery is never reported as functional verification."""

import ast
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.permissions import ROLE_PERMISSIONS
from app.db.session import Session, engine
from app.main import app
from app.modules.demo.guard import guard


async def main():
    folder = ROOT / "docs/phase-12"
    schema = app.openapi()
    (folder / "openapi.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    (folder / "role-permissions.json").write_text(
        json.dumps(ROLE_PERMISSIONS, indent=2), encoding="utf-8"
    )
    modules = []
    for directory in sorted((ROOT / "backend/app/modules").iterdir()):
        if not directory.is_dir() or directory.name.startswith("_"):
            continue
        files = sorted(directory.rglob("*.py"))
        tables = []
        functions = []
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "__tablename__" for t in node.targets
                    )
                    and isinstance(node.value, ast.Constant)
                ):
                    tables.append(node.value.value)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "function": node.name,
                            "line": node.lineno,
                        }
                    )
        modules.append(
            {
                "id": "MODULE-" + directory.name.upper(),
                "module": directory.name,
                "files": [str(p.relative_to(ROOT)) for p in files],
                "tables": tables,
                "functions": functions,
                "status": "PARTIALLY_VERIFIED",
                "readiness": "Internal synthetic evaluation only; see test matrix and module limitations",
                "authorization": "API require() plus existing service checks; tenant-owned tables FORCE RLS. See role-permissions.json. Individual actions require their own test evidence.",
            }
        )
    endpoints = [
        {
            "method": method.upper(),
            "path": path,
            "operation_id": operation.get("operationId"),
            "tags": operation.get("tags", []),
            "status": "NOT_TESTED",
            "note": "Discovered contract; execution coverage requires matching test assertions, not route existence",
        }
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    async with Session() as db:
        await guard(db)
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        role = (
            (
                await db.execute(
                    text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
            )
            .mappings()
            .one()
        )
        tables = (
            (
                await db.execute(
                    text(
                        "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname"
                    )
                )
            )
            .mappings()
            .all()
        )
        ledger = (
            await db.scalar(text("SELECT count(*) FROM journal_lines"))
            if role["rolsuper"]
            else None
        )
        # Set only the explicit demo tenant for owned table counts.
        from app.db.session import tenant_context
        from app.modules.demo.guard import DEMO_TENANT

        await tenant_context(db, str(DEMO_TENANT))
        ledger = await db.scalar(text("SELECT count(*) FROM journal_lines"))
        schedules = await db.scalar(
            text("SELECT count(*) FROM ai_scheduled_workflows WHERE active")
        )
        load_users = await db.scalar(
            text(
                "SELECT count(*) FROM users WHERE email LIKE 'synthetic.p12.load%' AND status='active'"
            )
        )
    inventory = {
        "scope": "Source/schema discovery with executed-test evidence linked separately; not a complete independent audit",
        "modules": modules,
        "api_operations": endpoints,
        "migration": revision,
        "database_role": dict(role),
        "schema_tables": [dict(x) for x in tables],
        "demo_journal_lines": ledger,
        "active_ai_schedules": schedules,
        "active_load_users": load_users,
        "module_count": len(modules),
        "api_operation_count": len(endpoints),
        "api_path_count": len(schema["paths"]),
    }
    (folder / "system-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    manifest = []
    for root in [
        ROOT / "backend/app",
        ROOT / "backend/alembic",
        ROOT / "frontend/src",
        ROOT / "ml-engine/src",
        ROOT / "deploy",
        ROOT / "scripts",
        ROOT / ".github",
    ]:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".css", ".tf", ".yml"}:
                manifest.append(
                    {
                        "path": str(p.relative_to(ROOT)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                )
    for name in [
        ".dockerignore",
        ".gitleaks.toml",
        ".env.example",
        "docker-compose.yml",
        "deploy/backend.Dockerfile",
        "deploy/Caddyfile",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "frontend/package.json",
        "frontend/package-lock.json",
        "ml-engine/package.json",
        "ml-engine/package-lock.json",
    ]:
        path = ROOT / name
        manifest.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (folder / "source-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                k: v
                for k, v in inventory.items()
                if k not in {"modules", "api_operations", "schema_tables"}
            }
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

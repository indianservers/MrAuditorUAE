"""Discover actual source/runtime contracts; execute fail-closed API and role probes."""

import ast
import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.core.permissions import ROLE_PERMISSIONS
from app.db.session import Session, engine, tenant_context
from app.main import app
from qa_campaign import guard
from sqlalchemy import text

OUT = ROOT / "docs/qa-campaign"


async def main():
    data = json.loads((OUT / "dataset.json").read_text(encoding="utf8"))
    schema = app.openapi()
    (OUT / "openapi.json").write_text(json.dumps(schema, indent=2), encoding="utf8")
    modules = []
    for directory in sorted((ROOT / "backend/app/modules").iterdir()):
        if not directory.is_dir() or directory.name.startswith("_"):
            continue
        tables, functions = [], []
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "__tablename__"
                        for t in node.targets
                    )
                    and isinstance(node.value, ast.Constant)
                ):
                    tables.append(node.value.value)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
        modules.append(
            {
                "module": directory.name,
                "tables": tables,
                "functions": functions,
                "status": "PARTIALLY_FUNCTIONAL",
                "evidence": "See executed tests; discovery alone does not establish functionality",
            }
        )
    text_source = "\n".join(
        p.read_text(encoding="utf8") for p in (ROOT / "frontend/src").rglob("*.tsx")
    )
    routes = set(re.findall(r'case\s+"(/[^" ]*)"', text_source))
    for page in (ROOT / "frontend/src/app").rglob("page.tsx"):
        parts = [
            p
            for p in page.relative_to(ROOT / "frontend/src/app").parts[:-1]
            if not p.startswith("(")
        ]
        if not any(p.startswith("[") for p in parts):
            routes.add("/" + "/".join(parts))
    # The workbench exposes dynamic areas through its actual navigation catalogues.
    prior = (
        json.loads(
            (ROOT / "docs/phase-12/route-inventory.json").read_text(encoding="utf8")
        )
        if (ROOT / "docs/phase-12/route-inventory.json").exists()
        else []
    )
    inventory = {
        "modules": modules,
        "roles": ROLE_PERMISSIONS,
        "routes": sorted(routes),
        "prior_route_inventory": prior,
        "endpoints": [],
    }
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, data["tenant_id"])
        inventory["tables"] = [
            dict(row)
            for row in (
                await db.execute(
                    text(
                        "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                    )
                )
            ).mappings()
        ]
    results, role_results = [], []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=60
    ) as c:
        auth = await c.post(
            "/api/v1/auth/login",
            data={
                "username": "qa.admin@auditos.example",
                "password": os.environ["QA_PASSWORD"],
            },
        )
        assert auth.status_code == 200
        headers = {
            "Authorization": "Bearer " + auth.json()["access_token"],
            "X-Tenant-ID": data["tenant_id"],
        }
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                inventory["endpoints"].append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "operation_id": operation.get("operationId"),
                        "tags": operation.get("tags", []),
                    }
                )
                resolved = re.sub(
                    r"\{[^}]+\}", "00000000-0000-4000-8000-000000000001", path
                )
                if "{area}" in path:
                    resolved = path.replace("{area}", "overview")
                r = await c.request(
                    method, resolved, **({"json": {}} if method != "get" else {})
                )
                public = path in {
                    "/health/live",
                    "/health/ready",
                    "/api/v1/system/version",
                } or path.startswith("/api/v1/auth/")
                results.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "case": "missing_auth",
                        "status": r.status_code,
                        "passed": r.status_code < 500
                        and (public or r.status_code in {401, 403, 422}),
                        "functional_claim": False,
                    }
                )
                if method == "get":
                    r = await c.get(resolved, headers=headers)
                    results.append(
                        {
                            "method": "GET",
                            "path": path,
                            "case": "authorized_catalogue_or_missing_resource",
                            "status": r.status_code,
                            "passed": r.status_code < 500,
                            "functional_claim": False,
                        }
                    )
        for user in data["users"]:
            # Respect the real per-IP authentication throttle during sequential users.
            await asyncio.sleep(2.2)
            r = await c.post(
                "/api/v1/auth/login",
                data={"username": user["email"], "password": os.environ["QA_PASSWORD"]},
            )
            if r.status_code == 429:
                await asyncio.sleep(60)
                r = await c.post(
                    "/api/v1/auth/login",
                    data={
                        "username": user["email"],
                        "password": os.environ["QA_PASSWORD"],
                    },
                )
            assert r.status_code == 200, (user["role"], r.status_code)
            h = {
                "Authorization": "Bearer " + r.json()["access_token"],
                "X-Tenant-ID": data["tenant_id"],
            }
            checks = []
            for method, path, permission in [
                ("GET", "clients", "clients.read"),
                (
                    "PATCH",
                    "clients/00000000-0000-4000-8000-000000000001",
                    "clients.write",
                ),
                ("GET", "analytics/rules", "analytics.read"),
                ("GET", "ai/providers", "ai.provider.manage"),
            ]:
                r = await c.request(
                    method,
                    "/api/v1/" + path,
                    headers=h,
                    **(
                        {"json": {"name": "SYNTHETIC QA missing resource probe"}}
                        if method == "PATCH"
                        else {}
                    ),
                )
                allowed = permission in ROLE_PERMISSIONS[user["role"]]
                checks.append(
                    {
                        "method": method,
                        "path": path,
                        "permission": permission,
                        "expected_permission": allowed,
                        "status": r.status_code,
                        "passed": r.status_code < 500
                        and (r.status_code != 403 if allowed else r.status_code == 403),
                    }
                )
            r = await c.get(
                "/api/v1/clients", headers={**h, "X-Tenant-ID": str(uuid.uuid4())}
            )
            checks.append(
                {
                    "case": "wrong_tenant",
                    "status": r.status_code,
                    "passed": r.status_code == 403,
                }
            )
            role_results.append({"role": user["role"], "login": True, "checks": checks})
    for name, value in [
        ("inventory.json", inventory),
        ("api-contract-results.json", results),
        ("role-results.json", role_results),
    ]:
        (OUT / name).write_text(json.dumps(value, indent=2), encoding="utf8")
    print(
        json.dumps(
            {
                "modules": len(modules),
                "endpoints": len(inventory["endpoints"]),
                "api_checks": len(results),
                "api_failed": sum(not r["passed"] for r in results),
                "roles": len(role_results),
                "role_failed": sum(
                    not c["passed"] for r in role_results for c in r["checks"]
                ),
            }
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

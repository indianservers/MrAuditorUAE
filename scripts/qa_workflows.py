"""Execute existing real-service workflow assertions against QA business scopes.

Only fixture allocation is adapted: clients/engagements and role users are reused
from this campaign. Application services, numerical assertions and HTTP responses
are unchanged. Failures remain recorded; no transaction cleanup or truncation.
"""

import asyncio
import importlib
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.core.security import access_token
from app.db.session import Session, engine
from app.main import app
from qa_campaign import guard

OUT = ROOT / "docs/qa-campaign"
CASES = [
    (
        "tests.phase6.test_workflows",
        "test_tax_group_aggregation_and_ownership_boundaries",
    ),
    ("tests.phase5.test_reporting", "test_company_statements_approval_and_exports"),
    ("tests.phase6.test_workflows", "test_mainland_approved_vs_proposed_and_exports"),
    (
        "tests.phase6.test_workflows",
        "test_qfzp_contract_segmentation_and_incomplete_conditions",
    ),
    (
        "tests.phase6.test_workflows",
        "test_loss_utilisation_versions_and_immutable_ledger",
    ),
    (
        "tests.phase7.test_vat_workflows",
        "test_vat201_actual_sources_return_review_and_stale_export",
    ),
    (
        "tests.phase7.test_vat_workflows",
        "test_invoice_defects_duplicates_and_date_versions",
    ),
    ("tests.phase8.test_workflows", "test_actual_rp_sales_benchmark_and_segmentation"),
    (
        "tests.phase8.test_workflows",
        "test_actual_loan_benchmark_credit_and_source_scope",
    ),
    (
        "tests.phase8.test_workflows",
        "test_source_reconciled_services_and_reviewed_localfile_exports",
    ),
    (
        "tests.phase9.test_workflows",
        "test_dmtt_actual_ifrs_approval_computation_and_ai",
    ),
    (
        "tests.phase9.test_workflows",
        "test_real_tensorflow_artifacts_approval_inference_rls_and_feedback",
    ),
    (
        "tests.phase10.test_workflows",
        "test_grc_independent_approval_owner_isolation_and_immutable_snapshots",
    ),
    (
        "tests.phase11.test_workflows",
        "test_investigation_permissions_resume_proposal_and_stale_approval",
    ),
    (
        "tests.phase11.test_templates",
        "test_configured_readonly_graph_activation_and_execution",
    ),
]


async def main():
    data = json.loads((OUT / "dataset.json").read_text(encoding="utf8"))
    async with Session() as db:
        await guard(db)
    roles = {u["role"]: u for u in data["users"]}
    admin = roles["Firm Administrator"]
    h = {
        "Authorization": "Bearer " + access_token(uuid.UUID(admin["id"])),
        "X-Tenant-ID": data["tenant_id"],
    }
    position = int(os.getenv("QA_WORKFLOW_OFFSET", "0"))

    async def setup(client):
        nonlocal position
        company = data["companies"][position % 25]
        position += 1
        options = {k: company[k] for k in ["client_id", "entity_id", "period_id"]}
        # Separate legal entity prevents replacing the campaign's scale imports.
        e = await client.post(
            "/api/v1/entities",
            headers=h,
            json={
                "client_id": company["client_id"],
                "name": f"QA FICTIONAL workflow entity {position}",
                "country": "AE",
                "jurisdiction": "SYNTHETIC QA",
                "functional_currency": "AED",
                "presentation_currency": "AED",
            },
        )
        assert e.status_code == 201, e.text
        options["entity_id"] = e.json()["id"]
        p = await client.post(
            "/api/v1/financial-periods",
            headers=h,
            json={
                "entity_id": options["entity_id"],
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
        assert p.status_code == 201, p.text
        options["period_id"] = p.json()["id"]
        engagement = await client.post(
            "/api/v1/engagements",
            headers=h,
            json={
                "entity_id": options["entity_id"],
                "period_id": options["period_id"],
                "name": f"QA workflow {position}",
                "engagement_type": "External Audit",
            },
        )
        assert engagement.status_code == 201, engagement.text
        eid = engagement.json()["id"]
        return h, options, eid, f"/api/v1/engagements/{eid}/audit"

    async def actor(headers, role, suffix):
        u = roles[role]
        return (
            {**headers, "Authorization": "Bearer " + access_token(uuid.UUID(u["id"]))},
            u["membership_id"],
            u["role_id"],
            u["id"],
        )

    async def second_entity(client, headers, suffix="-sub"):
        tax = importlib.import_module("tests.phase6.test_workflows")
        return await tax.prepared(client, await setup(client), suffix)

    # Import first, then change only orchestration fixture references, never services.
    modules = {name: importlib.import_module(name) for name, _ in CASES}
    importlib.import_module("tests.phase4.test_workflows")
    for name, module in list(sys.modules.items()):
        if name.startswith("tests.") and module:
            if (
                hasattr(module, "setup")
                and getattr(module.setup, "__module__", "")
                == "tests.phase4.test_workflows"
            ):
                module.setup = setup
            if hasattr(module, "actor"):
                module.actor = actor
            if hasattr(module, "second_entity"):
                module.second_entity = second_entity
    results = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=900,
    ) as c:
        for module, name in CASES:
            if os.getenv("QA_WORKFLOW_CASE") and os.environ["QA_WORKFLOW_CASE"] != name:
                continue
            if (
                os.getenv("QA_WORKFLOW_FILTER")
                and os.environ["QA_WORKFLOW_FILTER"] not in module
            ):
                continue
            start = time.perf_counter()
            result = {"id": module + "." + name, "status": "RUNNING"}
            try:
                function = getattr(modules[module], name)
                import inspect

                kwargs = {"environment": c}
                if "tmp_path" in inspect.signature(function).parameters:
                    folder = OUT / "exports" / name
                    folder.mkdir(parents=True, exist_ok=True)
                    kwargs["tmp_path"] = folder
                await function(**kwargs)
                result["status"] = "PASS"
            except Exception as exc:  # noqa: BLE001 - retain each failure and continue independent QA cases
                result.update(
                    status="FAIL", error=str(exc), traceback=traceback.format_exc()
                )
            result["seconds"] = time.perf_counter() - start
            results.append(result)
            filename = (
                "workflow-results-tp-rerun.json"
                if os.getenv("QA_WORKFLOW_FILTER")
                else "workflow-results.json"
            )
            if os.getenv("QA_WORKFLOW_CASE"):
                filename = "workflow-results-extra.json"
            (OUT / filename).write_text(json.dumps(results, indent=2), encoding="utf8")
            print(
                json.dumps(
                    {k: v for k, v in result.items() if k not in {"traceback", "error"}}
                ),
                flush=True,
            )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

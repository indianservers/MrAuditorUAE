"""Persist real campaign results and render evidence-based repository reports."""

import asyncio
import csv
import hashlib
import json
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.security import hash_password
from app.db.models.platform import EntityRelationship, User
from app.db.session import Session, engine, tenant_context
from app.modules.identity.mfa import enroll
from app.modules.saas.models import Operation, PlatformOperator
from qa_campaign import guard
from sqlalchemy import text

OUT = ROOT / "docs/qa-campaign"


def load(name, default=None):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf8")) if p.exists() else default


def markdown(name, title, paragraphs):
    replacements = {
        "modelresultsJSONfor": "model-results.json for",
        "syntheticQA": "synthetic QA",
        "realclientdata": "real client data",
        "performance/modelmetrics:summary.json": "performance/model metrics: summary.json",
        "commands/evidence:commands.md": "commands/evidence: commands.md",
        "XML/log/JSONfiles": "XML/log/JSON files",
        "onlyname": "only names",
        "sameentity/year": "same entity/year",
        "source-manifest batchIDs": "source-manifest batch IDs",
        "withoutMFA": "without MFA",
        "operatorgrant": "operator grant",
        "MFA+operatorgrant": "MFA + operator grant",
        "representsource": "represent source",
        "everytest": "every test",
        "productionreadiness": "production readiness",
    }
    paragraphs = [
        re.sub(r"(?<=[0-9])(?=[A-Za-z])|(?<=[a-z])(?=[0-9])", " ", p)
        for p in paragraphs
    ]
    for old, new in replacements.items():
        paragraphs = [p.replace(old, new) for p in paragraphs]
    (OUT / name).write_text(
        "# " + title + "\n\n" + "\n\n".join(paragraphs) + "\n", encoding="utf8"
    )


async def main():
    data = load("dataset.json")
    inventory = load("inventory.json", {})
    routes = load("frontend-route-results.json", [])
    public_routes = load("public-route-results.json", [])
    contracts = load("api-contract-results.json", [])
    roles = load("role-results.json", [])
    financial = load("financial-results.json", [])
    workflow = {r["id"]: r for r in load("workflow-results.json", [])}
    workflow.update({r["id"]: r for r in load("workflow-results-tp-rerun.json", [])})
    workflow.update({r["id"]: r for r in load("workflow-results-extra.json", [])})
    exceptions = load("exception-results.json", {})
    matrix = {}
    # Last execution wins; preserve original failing XML alongside regression XML.
    for p in sorted(OUT.glob("*.xml"), key=lambda p: p.stat().st_mtime):
        for t in ET.parse(p).getroot().iter("testcase"):
            key = t.get("classname", "") + "." + t.get("name", "")
            matrix[key] = {
                "id": key,
                "status": "FAIL"
                if t.find("failure") is not None or t.find("error") is not None
                else "SKIP"
                if t.find("skipped") is not None
                else "PASS",
                "seconds": float(t.get("time", 0)),
                "evidence": p.name,
            }
    counts = {}
    kinds = []
    models = []
    relationships = []
    async with Session() as db, db.begin():
        await guard(db)
        await tenant_context(db, data["tenant_id"])
        operator_id = uuid.uuid5(uuid.UUID(data["tenant_id"]), "qa-platform-operator")
        user = await db.get(User, operator_id)
        if not user:
            user = User(
                id=operator_id,
                email="qa.operator@auditos.example",
                password_hash=hash_password(os.environ["QA_PASSWORD"]),
            )
            db.add(user)
            await db.flush()
            secret = enroll(user)["secret"]
            user.mfa_enabled = True
            db.add(PlatformOperator(user_id=operator_id))
            (ROOT / ".local-runtime/qa-campaign/operator.local.json").write_text(
                json.dumps({"email": user.email, "secret": secret}), encoding="utf8"
            )
        for parent, child, share in [
            (12, 0, "100"),
            (12, 1, "95"),
            (12, 23, "80"),
            (21, 13, "100"),
            (21, 24, "50"),
        ]:
            identifier = uuid.uuid5(
                uuid.UUID(data["tenant_id"]), f"relationship/{parent}/{child}"
            )
            if not await db.get(EntityRelationship, identifier):
                db.add(
                    EntityRelationship(
                        id=identifier,
                        tenant_id=uuid.UUID(data["tenant_id"]),
                        created_by=uuid.UUID(data["users"][0]["id"]),
                        parent_id=uuid.UUID(data["companies"][parent]["entity_id"]),
                        child_id=uuid.UUID(data["companies"][child]["entity_id"]),
                        ownership_percent=Decimal(share),
                        effective_from=date(2023, 1, 1),
                    )
                )
            relationships.append(
                {
                    "parent": data["companies"][parent]["name"],
                    "child": data["companies"][child]["name"],
                    "ownership_percent": share,
                }
            )
        await db.flush()
        tables = (
            (
                await db.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                    )
                )
            )
            .scalars()
            .all()
        )
        for table in tables:
            has_tenant = await db.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=:name AND column_name='tenant_id')"
                ),
                {"name": table},
            )
            clause = " WHERE tenant_id=:tenant" if has_tenant else ""
            counts[table] = await db.scalar(
                text('SELECT count(*) FROM "' + table + '"' + clause),
                {"tenant": uuid.UUID(data["tenant_id"])} if has_tenant else {},
            )
        kinds = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "SELECT kind,status,count(*) count FROM audit_records WHERE tenant_id=:tenant GROUP BY kind,status ORDER BY kind,status"
                    ),
                    {"tenant": uuid.UUID(data["tenant_id"])},
                )
            ).mappings()
        ]
        models = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "SELECT id::text,kind,body FROM ml_registry_events WHERE tenant_id=:tenant AND kind IN ('model','evaluation','inference','deployment') ORDER BY created_at"
                    ),
                    {"tenant": uuid.UUID(data["tenant_id"])},
                )
            ).mappings()
        ]
    summary = {
        "executed_at": datetime.now(UTC).isoformat(),
        "database": data["database"],
        "synthetic": True,
        "clients": counts.get("clients", 0),
        "journal_lines": counts.get("journal_lines", 0),
        "engagements": counts.get("engagements", 0),
        "users": counts.get("users", 0),
        "vat_invoices": sum(k["count"] for k in kinds if k["kind"] == "vat-invoice"),
        "nonempty_tables": sum(v > 0 for v in counts.values()),
        "empty_tables": [k for k, v in counts.items() if not v],
        "scale_journal_lines": sum(b["lines"] for b in data["batches"]),
        "backend_passed": sum(r["status"] == "PASS" for r in matrix.values()),
        "backend_failed": sum(r["status"] == "FAIL" for r in matrix.values()),
        "backend_skipped": sum(r["status"] == "SKIP" for r in matrix.values()),
        "modules_discovered": len(inventory.get("modules", [])),
        "api_operations_discovered": len(inventory.get("endpoints", [])),
        "api_contract_checks": len(contracts),
        "api_contract_failures": sum(not r["passed"] for r in contracts),
        "api_scope": "Authentication/error envelope probes; valid business mutations additionally exercised by workflows. Not every parameter combination tested.",
        "frontend_routes_visited": len(routes) + len(public_routes),
        "frontend_javascript_errors": sum(len(r["errors"]) for r in routes),
        "frontend_server_errors": sum(len(r["failed"]) for r in routes),
        "frontend_overflow_routes": sum(r["horizontalOverflow"] for r in routes),
        "role_logins": len(roles),
        "role_checks": sum(len(r["checks"]) for r in roles),
        "role_failures": sum(not c["passed"] for r in roles for c in r["checks"]),
        "financial_passed": sum(r["status"] == "PASS" for r in financial),
        "financial_failed": sum(r["status"] == "FAIL" for r in financial),
        "workflows_passed": sum(r["status"] == "PASS" for r in workflow.values()),
        "workflows_failed": sum(r["status"] == "FAIL" for r in workflow.values()),
        "labeled_exception_cases": exceptions.get("labeled_cases", 0),
        "direct_exception_cases_missed": exceptions.get("missed_direct_rule_cases"),
        "normal_lines_flagged": exceptions.get("normal_lines_flagged"),
        "normal_lines_tested": exceptions.get("normal_lines"),
        "calibrated_exception_results": load("calibrated-exception-results.json", {}),
        "test_scope": "Local synthetic engineering verification; production certification and independent professional review remain outstanding.",
        "readiness": "CONDITIONAL INTERNAL QA ONLY; FULL CAMPAIGN ACCEPTANCE NOT YET SATISFIED",
        "limitations": [
            "Every route was rendered, but not every enabled control/action received an independent business-state assertion.",
            "12 exception categories require evidence/workflow context beyond the injected GL markers.",
            "External paid AI/OCR, connector providers, ClamAV and deployed production infrastructure are not qualified.",
            "Default analytics flags all normal rows in this dense fixture; calibration and task-specific precision studies remain required.",
        ],
        "records_per_table": counts,
        "audit_record_kinds": kinds,
        "stages": data["stages"],
        "workflows": list(workflow.values()),
        "load_results": load("load-results.json", []),
        "model_results": models,
    }
    model = next((r["body"]["metrics"] for r in models if r["kind"] == "model"), {})
    heldout = model.get("evaluation", {}).get("test", {}).get("model", {})
    for metric in ["precision", "recall", "f1", "false_positive_rate"]:
        summary["ml_heldout_" + metric] = heldout.get(metric)
    summary["ml_status"] = "EXPERIMENTAL; accuracy acceptance not satisfied"
    ml_summary = []
    for row in models:
        if row["kind"] != "model":
            continue
        m = row["body"]["metrics"]
        ml_summary.append(
            {
                "id": row["id"],
                "family": m["config"]["family"],
                "test": m.get("evaluation", {}).get("test", {}),
                "ood": m.get("evaluation", {}).get("ood", {}),
                "resources": m.get("resources", {}),
                "production_validated": row["body"]["production_validated"],
            }
        )
    (OUT / "ml-evaluation-summary.json").write_text(
        json.dumps(ml_summary, indent=2), encoding="utf8"
    )
    summary["ml_families_trained"] = len(ml_summary)
    summary["accounting_reconciled_snapshots"] = len(
        load("accounting-workflow-results.json", [])
    )
    summary["worker_results"] = load("worker-results.json", {})
    load100 = next((r for r in summary["load_results"] if r["concurrency"] == 100), {})
    summary["load100_p95_seconds"] = load100.get("p95_seconds")
    summary["load100_failed_responses"] = load100.get("failures")
    defects = [
        {
            "id": "QA-001",
            "severity": "MEDIUM",
            "status": "FIXED",
            "category": "product",
            "title": "Client code search mismatch",
        },
        {
            "id": "QA-002",
            "severity": "LOW",
            "status": "FIXED",
            "category": "harness",
            "title": "TP fixture selected foreign engagement ledger",
        },
        {
            "id": "QA-003",
            "severity": "LOW",
            "status": "FIXED",
            "category": "harness",
            "title": "Scale fixture attempted protected active-import replacement",
        },
        {
            "id": "QA-004",
            "severity": "LOW",
            "status": "FIXED",
            "category": "harness",
            "title": "Checkpoint counted unrelated workflow lines",
        },
        {
            "id": "QA-005",
            "severity": "HIGH",
            "status": "OPEN",
            "category": "quality",
            "title": "Representative analytics calibration not qualified; small synthetic calibration passed",
        },
        {
            "id": "QA-006",
            "severity": "MEDIUM",
            "status": "FIXED",
            "category": "performance",
            "title": "Million-line tenant pagination sort",
        },
        {
            "id": "QA-007",
            "severity": "HIGH",
            "status": "OPEN",
            "category": "quality",
            "title": "Experimental classifier held-out and OOD F1 zero",
        },
        {
            "id": "QA-008",
            "severity": "HIGH",
            "status": "OPEN",
            "category": "coverage",
            "title": "Every enabled control and role-operation pair not independently verified",
        },
        {
            "id": "QA-009",
            "severity": "HIGH",
            "status": "BLOCKED",
            "category": "integration",
            "title": "Live external AI, connectors, scanning and production infrastructure not qualified",
        },
        {
            "id": "QA-010",
            "severity": "MEDIUM",
            "status": "OPEN",
            "category": "reliability",
            "title": "One intermediate load transport disconnect; completed repeat had zero failures",
        },
    ]
    summary["active_defects"] = sum(d["status"] != "FIXED" for d in defects)
    summary["remaining_issue_counts"] = {
        level: sum(d["status"] != "FIXED" and d["severity"] == level for d in defects)
        for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    }
    (OUT / "defects.json").write_text(json.dumps(defects, indent=2), encoding="utf8")
    async with Session() as db, db.begin():
        await guard(db)
        db.add(
            Operation(
                actor_id=operator_id,
                tenant_id=uuid.UUID(data["tenant_id"]),
                action="qa.campaign.results",
                details=summary,
            )
        )
    for name, value in [
        ("summary.json", summary),
        ("test-matrix.json", list(matrix.values())),
        ("module-record-counts.json", counts),
        ("model-results.json", models),
        ("group-relationships.json", relationships),
    ]:
        (OUT / name).write_text(
            json.dumps(value, indent=2, default=str), encoding="utf8"
        )
    note = "Scope is local synthetic verification. Discovery and HTTP 200 alone are not evidence of complete business functionality."
    module_lines = []
    coverage_rows = []
    aliases = {
        "audit_execution": "engagements",
        "audit_analytics": "analytics",
        "audit_log": "workspace",
        "ai_engine": "ai",
        "enterprise_ai": "ai",
        "financial_ai": "financial-ai",
        "identity": "auth",
        "organizations": "entities",
        "ingestion": "accounting",
        "lineage": "accounting",
        "saas": "platform",
        "demo": "accounting",
    }
    for m in inventory.get("modules", []):
        prefix = aliases.get(m["module"], m["module"])
        apis = sorted(
            {
                r["path"]
                for r in inventory.get("endpoints", [])
                if r["path"].startswith("/api/v1/" + prefix)
            }
        )
        module_routes = [
            r["route"] for r in routes if r["route"].startswith("/" + prefix)
        ]
        permissions = sorted(
            {
                p
                for values in inventory.get("roles", {}).values()
                for p in values
                if p.startswith((prefix + ".", m["module"] + "."))
            }
        )
        status = (
            "External integration required"
            if m["module"] == "connectors"
            else "Partially functional"
        )
        coverage_rows.append(
            {
                "Module": m["module"],
                "Route": "; ".join(module_routes)
                or "Shared service / see route inventory",
                "API": "; ".join(apis),
                "Database": "; ".join(f"{t}={counts.get(t, 0)}" for t in m["tables"]),
                "Permission": "; ".join(permissions)
                or "Inherited request/service permission checks; see inventory.json",
                "Test": "test-matrix.json; workflow-results*.json; api-contract-results.json",
                "Status": status,
            }
        )
        module_lines.append(
            f"- **{m['module']}** — PARTIALLY FUNCTIONAL/VERIFIED. Tables: {', '.join(m['tables']) or 'shared services'}. Permissions: inventory.json roles. Tests: test-matrix.json and workflow-results*.json; external dependencies and uncovered controls remain explicit."
        )
    with (OUT / "module-testing-matrix.csv").open(
        "w", encoding="utf8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Module",
                "Route",
                "API",
                "Database",
                "Permission",
                "Test",
                "Status",
            ],
        )
        writer.writeheader()
        writer.writerows(coverage_rows)
    markdown(
        "module-inventory.md",
        "Actual module inventory",
        [
            note,
            "\n".join(module_lines),
            "Routes: frontend-route-inventory.json. APIs: openapi.json and inventory.json. The complete source area catalogues generated 196 candidate URLs; executed route results are authoritative.",
        ],
    )
    markdown(
        "database-assessment.md",
        "Database isolation and backup",
        [
            "Connected only to PostgreSQL127.0.0.1:55432. Campaign data: auditos_qa_campaign_demo. Destructive test fixtures: separate auditos_qa_campaign_test. Runtime application role is non-superuser/non-BYPASSRLS.",
            "database-assessment.json records prior database names, tenant markers and counts. Pre-campaign existing-demo custom-format backup was made before campaign DB creation; it remains ignored under .local-runtime/qa-campaign. No original demo records were modified by population.",
            "Population requires exact host, port, database name, development mode, synthetic flag and explicit QA_CAMPAIGN_ENABLED=true. Any unexpected tenant name blocks population.",
        ],
    )
    markdown(
        "synthetic-data-design.md",
        "Synthetic business and lineage",
        [
            "25 fictional companies span17industry categories, mainland/free-zone/foreign jurisdictions. Five explicit ownership relationships include parent/subsidiaries and50%JV. Industry is a fixture attribute/name; first-class client industry fields are not implemented.",
            "61 configured professional role users plus separately provisioned MFA operator; temporary load users are disabled after benchmark. Identifiers and domains are fictional.",
            "Deterministic18transaction families, balanced two-leg journals, immutable imports/source row SHA256 lineage, actual ledger-derived TB. Stages use separate entity/year snapshots; they are not overlapping replacement snapshots. Journal currencies are AED; foreign FX metadata is not broadly populated.",
            "20 exception labels are stored separately in exception-labels.json before detector execution. No final audit findings are inserted by the QA generator; analytics creates its own persisted findings.",
        ],
    )
    markdown(
        "data-generation-results.md",
        "Actual persisted QA data",
        [
            f"Clients: {summary['clients']}; journal lines: {summary['journal_lines']}; scale journal lines: {summary['scale_journal_lines']}; engagements: {summary['engagements']}; users: {summary['users']}.",
            "Complete table counts: module-record-counts.json. Domain record kinds/statuses: summary.json audit_record_kinds. dataset.json includes each source hash, import timing, snapshot and checkpoint. Failed attempts are retained; raw counts include any completed diagnostic fixtures.",
        ],
    )
    markdown(
        "account-reconciliation-report.md",
        "Accounting reconciliation",
        [
            "All committed scale batches passed real API trial-balance balanced checks. At each scale checkpoint independent SQL sums matched debits/credits and exact committed scale batch counts.",
            json.dumps(data["stages"], indent=2),
            "See dataset.json and financial-results.json. Full entity/year TB snapshots are separate populations; no unapproved merge or overwrite is performed. Opening/movement/closing is independently exercised by fixed Decimal fixtures.",
        ],
    )
    markdown(
        "module-testing-matrix.md",
        "Module testing matrix",
        [
            note,
            f"Backend latest per-test statuses: {summary['backend_passed']}PASS, {summary['backend_failed']}FAIL, {summary['backend_skipped']}SKIP. Details: test-matrix.json. Domain workflows: {summary['workflows_passed']}PASS, {summary['workflows_failed']}FAIL. Original failures remain in workflow-results.json; latest TP rerun is separate.",
            "Module statuses are partial where controls, external providers or specialist cases lack campaign evidence. No module is marked wholly functional merely by discovery.",
        ],
    )
    markdown(
        "api-testing-results.md",
        "API verification",
        [
            f"{summary['api_operations_discovered']} operations discovered; {summary['api_contract_checks']} contract/error checks; {summary['api_contract_failures']} currently classified failures.",
            summary["api_scope"],
            "The public /system/version endpoint was initially misclassified as protected by the harness; its explicit Version response is public by design. This harness error is retained in the original run log and corrected in the rerun.",
            "API mutations and persisted financial consistency are asserted by baseline XML and QA workflow tests; API execution receipts for population are in api-execution.jsonl.",
        ],
    )
    markdown(
        "frontend-testing-results.md",
        "Frontend verification",
        [
            f"{len(routes)} routes rendered; {summary['frontend_javascript_errors']}JS exceptions; {summary['frontend_server_errors']}5xx responses; {summary['frontend_overflow_routes']}horizontal-overflow routes at1600x900.",
            "Client code search failed in the browser and independently in a backend regression; the backend query now searches name OR code with escaped SQL wildcard characters. Search/filter/edit/reload/wrong-tenant denial rerun passed.",
            "Route/control inventories are frontend-route-results.json. Render sweep does not certify every enabled button. Platform operations denied the ordinary firm administrator. QA dashboard additionally requires separately granted operator plus MFA.",
            "Visual inspection compared the client screenshot with Mockup images/02_Client_Company_Management.png. Existing shell, dense grid and status styling were retained; no redesign. Before/after code-search screenshots are provided.",
        ],
    )
    markdown(
        "financial-accuracy-results.md",
        "Financial accuracy",
        [
            f"{summary['financial_passed']} fixed Decimal checks passed; {summary['financial_failed']}failed. financial-results.json preserves explicit golden values and differences.",
            "Additional backend suites cover financial-statement/cash-flow consistency, ECL, leases, revenue, deferred tax, depreciation, CT/interest/loss/QFZP, VAT, TP quartiles/loans, GloBE/covered tax/ETR/SBIE/topup. Test names and counts are in test-matrix.json. Fixtures validate implementation arithmetic, not independent statutory certification.",
        ],
    )
    markdown(
        "ai-evaluation-results.md",
        "AI evaluation",
        [
            "Actual synthetic investigation, template activation, tool authorization, proposal/review and stale-citation scenarios executed through QA services. Backend tests also exercise task schemas, invalid outputs, failure handling, budgets and prompt injection.",
            "No external paid provider credentials were supplied to this campaign. Deterministic fallback/stub-provider contract cases do not establish external model factual accuracy. Quantitative external citation/numerical fidelity and live-provider success metrics remain BLOCKED, not100% accurate.",
            "Evidence: baseline-backend.xml, workflow-results.json and persisted enterprise_ai* table counts.",
        ],
    )
    markdown(
        "tensorflowjs-training-results.md",
        "TensorFlow.js training and inference",
        [
            "Four real TensorFlow.js families were fitted: autoencoder, journal classifier, risk ranking and account classifier. The registry workflow exercised private artifact saving/loading, held-out evaluation, approval, inference, permissions and feedback. New family candidates were not approved or deployed. No metrics were invented.",
            "On the small held-out fixture, journal and risk classifiers had F1=0; autoencoder F1 was 0.888889; account-classifier accuracy was 0.6. Exact precision/recall, OOD metrics, rankings and resource measurements are in ml-evaluation-summary.json. All four candidates are production_validated=false. Scores do not establish representative audit accuracy.",
            "model-results.json records actual persisted model metrics, including reload checks. Small classifier training fixtures are engineering checks and must not be promoted on the basis of these scores. Broader anomaly-family precision/recall/F1/P@K and representative drift/rollback validation remain incomplete.",
            "ML engine unit tests and build evidence: ml-tests.txt, ml-build.txt.",
        ],
    )
    markdown(
        "role-permission-results.md",
        "Role security",
        [
            f"{summary['role_logins']} roles logged in; {summary['role_checks']} backend checks; {summary['role_failures']}failed. role-results.json contains each expectation and observed status.",
            "Scope: clients read/write gate, analytics read, AI provider management and wrong tenant. Domain-specific review/export/AI permissions additionally have regression/workflow evidence; this is not an exhaustive role×operation matrix. Login throttling was respected by paced requests, without disabling the control.",
        ],
    )
    markdown(
        "security-findings.md",
        "Security and integrity",
        [
            "No confirmed critical security or financial integrity vulnerability was found by the executed scope. This does not certify untested controls.",
            "Cross-tenant, source scope, self-approval, immutable history, session revocation, MFA replay and entitlement checks execute in real PostgreSQL-backed tests. QA results endpoint denies ordinary firm admins, requiresMFA+operatorgrant and is disabled unless explicitly enabled. Production configuration rejects QA controls.",
            "External upload scanning, hosted DAST, production infrastructure and actual external connector credentials remain blocked. All synthetic source objects and credentials stay in ignored private directories.",
        ],
    )
    markdown(
        "performance-results.md",
        "Measured performance",
        [
            "Progressive import/upload/validation/commit/TB timings are in dataset.json; checkpoint time on a resumed stage can reflect verification only, so use summed batch timings for generation performance.",
            "load-results.json records10/25/50/100distinct-user bounded HTTP read loads when executed, response-shape checks, p50/p95, wall time and host CPU/memory deltas. Host metrics include other local campaign work. No production throughput capacity is inferred.",
            "Three jobs traversed the actual HTTP API, Redis broker and separate Celery worker, then completed in PostgreSQL and were retrieved through HTTP. Measured elapsed time was 12.81 seconds (0.234 jobs/second) for this small solo-worker analytics sample; worker-results.json contains timestamps and outputs.",
        ],
    )
    markdown(
        "bugs-found-and-fixed.md",
        "Defects and retests",
        [
            "QA-001 MEDIUM — client directory advertised code search but backend searched onlyname. Reproduced by Playwright and search-before.xml. Fixed with escaped ORquery in ResourceService for Clientonly. search-after.xml and browser-controls-final.txt pass.",
            "QA-002 TEST HARNESS — TP fixtures used all tenant journal lines when financial result lacked period_id. In populated databases this selected foreign engagement sources; production correctly rejected422. Fixture now constrains entity+period; original failures and TP reruns retained.",
            "QA-003 TEST HARNESS — sameentity/year scale replacement correctly blocked409. Generator now uses separate historical periods. QA-004 HARNESS — overall tablecount included concurrently executed workflow lines; checkpoint now counts only source-manifest batchIDs.",
            "QA-005 QUALITY LIMITATION — defaults flagged all 200 normal fixture lines. An explicit source configuration (exact near-duplicates, daily velocity 500) flagged zero normal lines and retained all eight directly testable labels. Both runs are retained. This small synthetic calibration is not a production accuracy study.",
            "QA-006 MEDIUM, FIXED — default ledger pagination sorted a million-row tenant population. Migration 0013 adds (tenant_id, created_at, id). With refreshed statistics, measured page query fell from 314.505 ms to 0.332 ms. Completed 100-user workload p95 fell from 22.24 to 9.84 seconds. One intervening transport-disconnect run remains recorded.",
            "QA-007 HIGH, OPEN — the actual three-epoch classifier achieved held-out and OOD precision/recall/F1 of zero. The deterministic baseline scored 1 on this tiny fixture. The model remains experimental, production_validated=false, with no production promotion. Workflow PASS means artifact and authorization assertions passed, not model accuracy acceptance.",
        ],
    )
    markdown(
        "unresolved-blockers.md",
        "Remaining limitations",
        [
            "HIGH: analytics signal calibration/false-positive quality on dense normal fixtures.",
            "HIGH: the trained experimental classifier has held-out F1=0. Training/data/hyperparameter evaluation is required before any production promotion.",
            "HIGH: not every enabled UI action and every role×operation boundary has complete campaign assertion coverage.",
            "HIGH/EXTERNAL: live AI providers, OCR/scanning, external connectors and hosted production security/recovery are not qualified.",
            "MEDIUM: one intermediate 100-user repeat encountered a transport disconnect. The completed repeated workload had zero failed responses, but the original failure is retained for reliability follow-up.",
            "MEDIUM:12non-GLexceptioncategories require richer workflow/evidence datasets; some module tables remain empty. Group/tax-group and consolidation scenarios have backend fixtures but not comprehensive intercompany business coverage.",
            "Two skipped backend tests retain explicit skip reasons inXML. No claim that every test or full campaign acceptance passed.",
            "Open campaign register: 4 HIGH and 1 MEDIUM issues/coverage limitations; no confirmed CRITICAL issue in the executed scope. These counts are not an assurance claim about untested features. See defects.json for categories and individual states.",
        ],
    )
    markdown(
        "final-qa-report.md",
        "AuditOS UAE QA campaign status",
        [
            f"Status: **{summary['readiness']}**.",
            f"Actual clients: {summary['clients']}; journal lines: {summary['journal_lines']} ({summary['scale_journal_lines']} scale records); engagements: {summary['engagements']}; users: {summary['users']}; VAT invoices: {summary['vat_invoices']}. Full record counts are in module-record-counts.json.",
            f"Latest unique backend results: {summary['backend_passed']} passed, {summary['backend_failed']} failed, {summary['backend_skipped']} skipped. Financial fixtures: {summary['financial_passed']} passed. QA workflow scenarios: {summary['workflows_passed']} passed, {summary['workflows_failed']} failed. Roles: {summary['role_logins']}; backend role checks: {summary['role_checks']}; permission failures: {summary['role_failures']}.",
            f"Frontend: {summary['frontend_routes_visited']} routes visited. API: {summary['api_operations_discovered']} operations discovered; {summary['api_contract_checks']} contract probes. This does not establish complete control or business-case coverage.",
            "Fixed client code search with backend/browser reproduction and retest. Corrected populated-database test fixture source scope. Actual TensorFlow fitting/inference executed. See numerical/modelresultsJSONfor actual measured values.",
            "The experimental classifier's held-out precision, recall and F1 were all zero (40 records); OOD scores were also zero (20 records). It remains experimental and is not production validated. Deterministic baseline F1 was 1 on those small fixtures. External model factual accuracy was not measured.",
            "At 100 concurrent synthetic users, the completed post-index read benchmark had zero failed responses and p95 9.84 seconds, compared with 22.24 seconds before optimization. One intermediate transport-disconnect attempt is retained; this is not production capacity certification.",
            "All data is isolated syntheticQA. Existing demo backed up and preserved. No production deployment, no realclientdata sent externally. Source changes are uncommitted for review.",
            f"All {summary['accounting_reconciled_snapshots']} scale snapshots now have source-CSV-derived TB comparisons, persisted reconciliations and deterministic sampling runs. The accounting-workflow-results.json file records each result. Three real broker jobs completed successfully; worker-results.json contains measured throughput.",
            "Remaining work and severity: unresolved-blockers.md. Detailed counts/performance/modelmetrics:summary.json. Raw commands/evidence:commands.md, XML/log/JSONfiles.",
        ],
    )
    manifest = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name != "evidence-manifest.json":
            manifest.append(
                {
                    "path": str(p.relative_to(OUT)).replace("\\", "/"),
                    "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
    (OUT / "evidence-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if not isinstance(v, (list, dict))}
        )
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

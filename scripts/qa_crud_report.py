"""Build evidence-indexed campaign reports without converting gaps into passes."""

import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/qa-crud"


def write(name, title, body):
    (OUT / (name + ".md")).write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf8")


def main():
    cases = {}
    for filename in ["full-backend.xml", "crud-final.xml"]:
        for row in ET.parse(OUT / filename).iter("testcase"):
            identifier = row.get("classname") + "." + row.get("name")
            cases[identifier] = {
                "id": identifier,
                "status": "FAIL"
                if row.find("failure") is not None or row.find("error") is not None
                else "SKIP"
                if row.find("skipped") is not None
                else "PASS",
                "seconds": float(row.get("time", 0)),
                "receipt": filename,
            }
    # The final source-replacement test was parameterized after the full run.
    obsolete = [
        key
        for key in cases
        if "test_ifrs_current_status_invalidates_after_real_import_supersession" in key
        and "[" not in key
    ]
    for key in obsolete:
        del cases[key]
    counts = dict(Counter(row["status"] for row in cases.values()))
    browser = json.loads((OUT / "browser-results.json").read_text(encoding="utf8"))
    roles = json.loads((OUT / "browser-role-results.json").read_text(encoding="utf8"))
    module_groups = [
        (
            "Clients",
            "qa_crud",
            "/clients",
            "clients",
            "Reasoned archive/restore with version conflict protection",
        ),
        (
            "Legal entities",
            "phase2",
            "/clients",
            "legal_entities",
            "Archive/restore after dependent engagement closure; active parent required",
        ),
        (
            "Ownership relationships",
            "phase8.test_relationships",
            "/tp",
            "audit_records",
            "Effective-period reviewed relationship versions; do not hard-delete history",
        ),
        (
            "Financial periods",
            "phase2",
            "/clients",
            "financial_periods",
            "Scoped create/read; immutable source period linkage",
        ),
        (
            "Accounting connections",
            "phase2.test_connectors",
            "/integrations",
            "accounting_connections",
            "Guarded synchronization; no blanket delete",
        ),
        (
            "Imports",
            "phase2.test_pipeline",
            "/imports",
            "import_batches/import_snapshots",
            "Validate/commit/supersede; immutable source receipts",
        ),
        (
            "Journal records",
            "phase2.test_pipeline",
            "/ledger",
            "journal_entries/journal_lines",
            "Immutable imported lines; replace source batch",
        ),
        (
            "Account mappings",
            "qa_crud.test_source_changes",
            "/mappings",
            "account_mappings/accounts",
            "Append mapping versions; existing feature receipts become stale",
        ),
        (
            "Trial balances",
            "phase2",
            "/trial-balance",
            "trial_balance_snapshots/trial_balance_lines",
            "Regenerate from explicit snapshot; preserve prior results",
        ),
        (
            "Reconciliations",
            "phase2",
            "/reconciliation",
            "reconciliation_runs",
            "Immutable runs and exceptions; controlled regeneration",
        ),
        (
            "Audit engagements",
            "phase4",
            "/engagements",
            "engagements",
            "Controlled transitions; direct status PATCH rejected",
        ),
        (
            "Materiality",
            "phase4",
            "/engagements/{eid}/materiality",
            "audit_records",
            "Versioned draft, independent review, reopen/lock",
        ),
        (
            "Risk assessments",
            "phase4",
            "/engagements/{eid}/risks",
            "audit_records",
            "Versioned review; unused draft archive/restore",
        ),
        (
            "Audit programs",
            "phase4",
            "/engagements/{eid}/programs",
            "audit_records",
            "Versioned program/procedure review; unused draft archive/restore",
        ),
        (
            "Working papers",
            "qa_crud.test_lifecycle",
            "/engagements/{eid}/working-papers",
            "audit_records/audit_record_versions",
            "Unused draft archive/restore; approved history protected",
        ),
        (
            "Evidence",
            "phase4",
            "/engagements/{eid}/evidence",
            "audit_evidence_versions",
            "Immutable object versions, hashes, retention; no hard delete",
        ),
        (
            "Review notes",
            "phase4",
            "/engagements/{eid}/review-notes",
            "audit_records/audit_review_decisions",
            "Resolve/clear through review workflow",
        ),
        (
            "IFRS adjustments",
            "phase5.test_reporting",
            "/ifrs/{eid}/adjustments",
            "audit_records",
            "Draft/review/reopen; approved adjustment supersession changes dependencies",
        ),
        (
            "Lease schedules",
            "phase5",
            "/ifrs/{eid}/leases",
            "audit_records/ifrs_calculation_runs",
            "Versioned assumptions and immutable calculations",
        ),
        (
            "ECL schedules",
            "phase5",
            "/ifrs/{eid}/ecl",
            "audit_records/ifrs_calculation_runs",
            "Versioned assumptions and immutable calculations",
        ),
        (
            "Financial statements",
            "phase5.test_reporting",
            "/ifrs",
            "ifrs_calculation_runs",
            "New approved source profile and mapping required after supersession",
        ),
        (
            "Consolidation",
            "phase5.test_reporting",
            "/ifrs",
            "ifrs_calculation_runs",
            "Controlled member/elimination runs, immutable prior outputs",
        ),
        (
            "Corporate Tax",
            "phase6",
            "/tax",
            "ct_computation_runs",
            "Controlled regeneration/release; current financial source required",
        ),
        (
            "QFZP",
            "phase6",
            "/tax",
            "audit_records/ct_computation_runs",
            "Reviewed classification inputs and assessment; not automatic certification",
        ),
        (
            "VAT",
            "phase7",
            "/vat",
            "audit_records/vat_computation_runs",
            "Draft invoice archive/restore; reviewed return source dependency checks",
        ),
        (
            "Transfer Pricing",
            "phase8",
            "/tp",
            "audit_records/tp_calculation_runs",
            "Reviewed source relationships and controlled immutable runs",
        ),
        (
            "Intercompany loans",
            "phase8",
            "/tp",
            "audit_records/tp_calculation_runs",
            "Reviewed economic assumptions; rerun dependent calculations",
        ),
        (
            "Benchmarking",
            "phase8",
            "/tp",
            "audit_records/tp_calculation_runs",
            "Versioned observations; manual assumptions remain disclosed",
        ),
        (
            "DMTT",
            "phase9",
            "/pillar-two",
            "audit_records",
            "Reviewed jurisdiction/financial sources and immutable calculation history",
        ),
        (
            "GRC risks",
            "phase10",
            "/grc",
            "audit_records",
            "Specialist governed review; generic archive is blocked",
        ),
        (
            "Internal controls",
            "phase10",
            "/grc",
            "audit_records",
            "Specialist governed review and source linkage",
        ),
        (
            "Monitoring alerts",
            "phase10",
            "/grc",
            "audit_records",
            "Controlled alert disposition and retained evidence",
        ),
        (
            "Remediation actions",
            "phase10",
            "/grc",
            "audit_records",
            "Owner-scoped controlled transitions",
        ),
        (
            "AI investigations",
            "phase11",
            "/ai",
            "ai_workflow_events",
            "Grounded sources, proposal review, bounded execution",
        ),
        (
            "AI workflows",
            "phase11",
            "/ai",
            "ai_workflow_runs",
            "Cancel/review/execute with exact-payload and target-version checks",
        ),
        (
            "TensorFlow.js predictions",
            "phase9",
            "/ai-lab",
            "ml_registry_events",
            "Append-only artifacts; stale lineage blocks further consequential use",
        ),
        (
            "Users and permissions",
            "phase12",
            "/admin/users",
            "users/tenant_memberships/membership_roles",
            "Versioned admission and access checks; no destructive user-history removal",
        ),
        (
            "Subscriptions and entitlements",
            "phase12",
            "/platform",
            "tenant_subscriptions/platform_operations",
            "Separately authorized platform changes; isolated from client-data permissions",
        ),
    ]
    modules = []
    for name, selector, route, table, policy in module_groups:
        tests = [
            r["id"]
            for r in cases.values()
            if selector in r["id"] and r["status"] == "PASS"
        ]
        modules.append(
            {
                "module": name,
                "status": "PARTIAL" if tests else "NOT TESTED",
                "frontend_route_family": route,
                "database_family": table,
                "policy": policy,
                "passing_related_tests": tests,
                "complete_manual_crud_workflow": name in {"Clients", "Working papers"},
                "remaining": "Every operation under every applicable specialist role has not been exercised through browser forms",
            }
        )
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "readiness": "NO-GO",
        "campaign_status": "PARTIAL",
        "backend_unique_current_tests": counts,
        "browser": browser["stats"],
        "role_login_probes": len(roles),
        "modules": modules,
        "tests": list(cases.values()),
        "superseded_test_name_excluded": obsolete,
        "limitations": [
            "All 38 requested module families have been inventoried; complete manual CRUD coverage across every family and role is not established.",
            "Two live-connector tests are skipped, never counted as passes.",
            "External paid AI/provider calls and representative ML production validation remain unverified.",
            "No automatic retraining or rewriting of approved outputs.",
        ],
    }
    (OUT / "campaign-results.json").write_text(
        json.dumps(summary, indent=2), encoding="utf8"
    )
    detail = "\n".join(
        f"- **{m['module']} — {m['status']}**. {m['policy']}. Related passing tests: {len(m['passing_related_tests'])}; full per-role browser CRUD: {'two representative workflows only' if m['complete_manual_crud_workflow'] else 'not completed'}."
        for m in modules
    )
    write(
        "lifecycle-policy-matrix",
        "Lifecycle policy matrix",
        "There is no universal delete endpoint. Policy coverage is distinct from test coverage. API contracts and the complete 109-kind catalogue are in crud-inventory.json.\n\n"
        + detail,
    )
    write(
        "dependency-graph",
        "Dependency graph",
        """
```mermaid
flowchart TD
Client --> Entity --> Period --> Import --> Snapshot
Snapshot --> GL --> TB --> IFRS --> Tax
IFRS --> Consolidation
GL --> Analytics --> Sampling
GL --> VAT
GL --> TP
GL --> Features --> Model --> Prediction --> AI
Mapping --> TB
Mapping --> Analytics
Mapping --> Features
ReviewedRecords --> IFRS
ReviewedRecords --> VAT
ReviewedRecords --> TP
ReviewedRecords --> GRC
ReviewedRecords --> AI
```

The graph represents dependency families, not evidence that every edge has a complete browser regression. Immutable calculation dependencies capture record id/version/status. ML datasets now capture active source snapshot hashes and chart mapping versions. The permission-filtered `GET /engagements/{eid}/audit/dependencies` registry verifies current receipts synchronously on every read with per-module paging. Source supersession and mapping changes never rewrite approved historical outputs.
""",
    )
    write(
        "dependency-propagation",
        "Dependency propagation",
        """
Source replacement uses actual upload → validation → commit with `supersedes_id`. The regression first demonstrated IFRS `dependencies_current=true` after replacement; it now reports false, preserves the original SHA and blocks recalculation from the superseded profile. A newly reviewed profile and mapping produce a new run. Both small amounts and AED 1,000,000 → 1,100,000 revenue replacement are tested; the latter independently asserts AED 100,000 profit movement.

Read-time checking prevents delayed invalidation gaps. `CURRENT` and `STALE` are emitted by the new registry; stale items require controlled regeneration and independent review. `RECALCULATION_REQUIRED`, `REVIEW_REQUIRED`, `BLOCKED` and `SUPERSEDED` are not falsely claimed as a universal persisted status machine. Existing module transitions enforce review/lock/block states separately. No asynchronous automatic recalculation or automatic retraining was added.

See crud-final.xml and full-backend.xml. Exhaustive ownership, tax-group and monitoring event propagation across all 38 families remains partial.
""",
    )
    write(
        "soft-delete-policy",
        "Soft delete and retention",
        """
Clients and entities use reasoned status archival/restoration with optimistic versions. New children require active parents. Unfinished dependent engagements block archival. Default client/entity lists exclude archived records; explicit status filters retain access to history.

Only working papers, risks, VAT invoices, requests, planning records, programs and procedures support the new unused-draft archive/restore actions. Eligible states are DRAFT/IN_PROGRESS; referenced or previously approved/locked records cannot be archived. The same record id, immutable revisions and actor/reason audit events are retained. Restore revalidates links and owner access. Specialist records outside this allowlist require their own governed workflow. Source snapshots, journals, reviewed adjustments, evidence objects, review decisions, calculation runs and ML artifacts remain protected from generic hard deletion.

Current implementation uses status plus append-only revisions/events rather than new deleted_at/deleted_by columns. Archived draft references remain unique, so archival cannot free identifiers for duplicate history.
""",
    )
    write(
        "restore-test-results",
        "Restore tests",
        "See `crud-final.xml`, `browser-results.json` and screenshots. API assertions cover same-id restoration, version increments, unchanged Unicode client name, duplicate-code conflict, repeated archive/restore conflicts, history retention, meaningful reason validation, linked-source revalidation, read-only/cross-tenant rejection and approved-record protection. Browser workflows separately create/edit/archive/restore clients and working papers. Restore for every eligible record kind is not yet independently exercised.",
    )
    write(
        "manual-browser-tests",
        "Manual-style browser tests",
        f"Actual Next.js forms and FastAPI/PostgreSQL were used at local QA ports 3006/58009. Browser result receipt: `{browser['stats']}`. Thirteen real role logins probe read/create permissions and cross-tenant denial; they do not prove specialist CRUD forms for those roles. Client and working-paper workflows create, search, edit, archive and restore persisted records. A two-tab workflow verifies live cache invalidation and 409 on an older open edit. Screenshots are in screenshots/. Earlier failed harness runs are retained; missing Origin headers, inaccurate case-sensitive labels and row-versus-reference-button selectors were corrected without weakening application checks.",
    )
    write(
        "financial-change-tests",
        "Financial changes",
        "The new source-replacement regression covers immutable historical IFRS SHA, explicit staleness, blocked old-profile reuse and reviewed regeneration with independent Decimal profit deltas, including revenue AED 1m → 1.1m. Existing full-suite regressions cover IFRS adjustment/review/export, leases/ECL, consolidation, corporate tax/QFZP, VAT and TP loan/rate assumptions. Related test names and module references are in campaign-results.json. A green test in one area does not establish all downstream module combinations.",
    )
    write(
        "ai-freshness-tests",
        "AI freshness",
        "AI citation validation now rejects ML events whose source snapshot or mapping receipts are stale. Existing enterprise AI lineage, financial source version, permission, review and exact-payload regressions passed in the full suite. ML feature extraction excludes superseded lines, and old feature receipts are marked STALE after actual replacement or mapping changes. Historical results remain readable. External live LLM provider behavior and every possible stale source combination are not established by this campaign.",
    )
    write(
        "ai-action-tests",
        "AI action controls",
        "The full backend suite exercises enterprise AI proposal approval/rejection, exact payload, target versions, permissions, immutable events and bounded service execution. Consequential changes continue through standard services. Draft archival increments target versions and blocks direct editing, preserving the stale-target conflict mechanism. No autonomous delete or silent approval pathway was introduced. Full manual browser approval testing for every proposed action, deleted target and specialist role remains incomplete; see remaining-blockers.md.",
    )
    write(
        "tensorflowjs-change-tests",
        "TensorFlow.js data changes",
        "The reproduced defect extracted 12 rows after replacing a six-row journal population. Extraction now joins active import batches and returns six. Datasets retain snapshot SHA and chart mapping receipts; both replacement and actual approved chart changes invalidate old receipts. Stale training requests return 409 before enqueue, and train/inference workers recheck lineage after native Node execution. Approval, deployment, explanation and enterprise AI citation paths also validate freshness. Full-suite native TFJS tests remain passing. The real HTTP/Redis/Celery worker probe also produced a 10,000-row dataset with CURRENT snapshot and mapping receipts; worker-results.json retains its job/dataset identifiers. Repeated submission returned the same completed job. Existing production-quality limitations and experimental model status from the earlier campaign remain unchanged; no silent retraining or production validation is claimed.",
    )
    write(
        "concurrency-tests",
        "Concurrency and cache invalidation",
        "The two-tab Playwright workflow opens the same client at version N, saves one editor and verifies the second editor receives 409 with the first value intact. Its grid updates through same-origin BroadcastChannel invalidation without reload. Messages contain only tenant identifiers, never tokens or data. Tenant-scoped api/access query caches are invalidated after successful mutations. Draft records are serialized through engagement/record locks and explicit versions. Fast review actions are disabled while a save is refreshing its version. Broader simultaneous archive/create, deadlock and all-role revocation stress cases remain partial.",
    )
    write(
        "role-permission-tests",
        "Role and permission tests",
        "Thirteen real browser sign-ins cover Platform Administrator, Firm Administrator, Audit Partner / Chartered Accountant, Audit Manager, Auditor, Tax Manager, TP Analyst, VAT Analyst, Internal Auditor, Client Administrator, Client Viewer, Quality Reviewer and Read-only Reviewer. Direct server GET/POST/cross-tenant probes are checked against the source permission catalogue, not button visibility. See browser-role-results.json. The focused API tests also reject draft archival by a read-only reviewer and foreign tenant. Full specialist mutation/review cycles under each role remain incomplete.",
    )
    integrity = json.loads((OUT / "database-integrity.json").read_text())
    write(
        "database-integrity",
        "Database integrity",
        f"Read-only, tenant-scoped SQL assertions use the nonsuperuser application role on `{integrity['database']}`. Actual checks are in database-integrity.json: `{integrity['checks']}`. The original synthetic million-line population was not regenerated. A private pre-campaign pg_dump backup was created before changes. Tests use the separate auditos_qa_crud_test database and Redis database 6; interactive QA uses Redis 4. An accidental overlap of disposable tests caused fixture resets; those runs were retained and superseded by serial runs. No production database is targeted.",
    )
    write(
        "bugs-found-and-fixed",
        "Findings and fixes",
        """
- HIGH, reproduced: IFRS reported current after real source replacement. Active source validation now propagates staleness and blocks old-profile recalculation; historical SHA is unchanged.
- HIGH, reproduced: ML extraction counted superseded and replacement journals (12 instead of 6). Active-batch extraction fixes the row count.
- HIGH, verified regression: ML lacked verifiable snapshot/mapping freshness. Receipts, read-time freshness and use-time guards now prevent stale consequential use. Legacy live-ledger datasets without receipts are conservatively stale.
- MEDIUM, reproduced listing gap: archived clients appeared in default active views. Default list filtering and explicit history filters are implemented. Parent guards and unfinished-engagement protection are tested; the original reason-field 422 probe is not misrepresented as an observed successful bypass.
- MEDIUM, lifecycle gap: safe draft archive/restore was absent. Explicit allowlist, prior-review/reference protection, reasons, permissions and restore revalidation now preserve history.
- MEDIUM, browser integration: a new record-detail read returned 405; a scoped GET endpoint now supplies the current record and is API/browser tested.
- MEDIUM, reproduced fast-action conflict: an action immediately following save could use the old version. Actions remain disabled until save invalidation finishes.
- MEDIUM, cache gap: mutation invalidation was confined to one tab. Tenant-only BroadcastChannel invalidation now refreshes other tabs; stale open forms still receive 409.
- LOW, source mismatch: audit search advertised reference or title but searched title only. Escaped reference/title OR filtering is implemented.

The raw before/after JUnit and browser logs remain available. Selector, missing-Origin and overlapping-fixture failures are harness failures, not additional application defects. Scope-wide residual risks are recorded separately, not marked fixed.
""",
    )
    write(
        "remaining-blockers",
        "Remaining blockers",
        """
**NO-GO for an exhaustive or production-ready certification.**

- Complete create/edit/review/archive/restore browser workflows across all 38 families and every applicable role remain incomplete. The full backend suite is broad regression evidence, not a substitute for that manual matrix.
- Restore has representative API/browser coverage; every allowlisted kind and all dependency/concurrency combinations are not independently exercised.
- External accounting connectors/provider calls lack live credentials; two connector tests remain skipped.
- Production ML quality/calibration and representative out-of-distribution validation from the prior campaign remain unresolved. Experimental fixture scores are not audit conclusions.
- Registry coverage is IFRS/tax/VAT/TP/ML, with existing module guards elsewhere; a universal cross-module notification/outbox and all six requested statuses have not been implemented or claimed.
- Real multi-process concurrent archive/create and every entitlement/permission-revocation propagation scenario remain unverified.

These are explicit incomplete items; this report must not be presented as completion of the full requested campaign.
""",
    )
    focused = [r for r in cases.values() if ".qa_crud." in r["id"]]
    categories = {
        label: [r["id"] for r in focused if any(k in r["id"] for k in keys)]
        for label, keys in {
            "restore": ["restore"],
            "delete_policy": ["archive", "archival"],
            "dependency": ["supersession", "superseded", "dependency"],
            "concurrency": ["conflict", "history"],
            "role": ["role", "tenant"],
        }.items()
    }
    (OUT / "test-counts.json").write_text(
        json.dumps(
            {
                "backend": counts,
                "focused_cases": len(focused),
                "categories_overlap": categories,
                "note": "Counts are executed test cases, not fabricated HTTP-operation counts; shared fixture operations are not double counted as separate tests.",
            },
            indent=2,
        ),
        encoding="utf8",
    )
    write(
        "final-crud-qa-report",
        "Final CRUD QA report",
        f"**Campaign status: PARTIAL. Readiness: NO-GO.**\n\nBackend evidence: {counts.get('PASS', 0)} unique current-source test cases passed; {counts.get('SKIP', 0)} skipped; {counts.get('FAIL', 0)} failed. Full run and focused reruns are combined by test identity; the superseded unparameterized test name is excluded. Focused new cases: {len(focused)}. Frontend unit tests: 25 passed; browser results: {browser['stats']}. Role login/API probe sets: {len(roles)}. Discovery covers all 38 requested families, with 109 typed audit kinds, mapped tables and exact OpenAPI routes in the inventory.\n\nVerified fixes address source staleness, ML double counting, guarded lifecycle/history, scoped record detail, search and multi-tab refresh. The actual source-change test includes AED 1m → 1.1m revenue and AED 100k profit movement. No approved historical result is silently rewritten.\n\nPer-family coverage and policies:\n\n{detail}\n\nActual test identities and receipts are in campaign-results.json. Test categories overlap; test-counts.json avoids false sums. Independent database receipts and browser screenshots are retained. Complete specialist browser CRUD across every role remains open; see remaining-blockers.md. No git commit or push was performed for this campaign.",
    )
    print(
        json.dumps(
            {
                "backend": counts,
                "modules": len(modules),
                "focused": len(focused),
                "status": "PARTIAL",
            }
        )
    )


if __name__ == "__main__":
    main()

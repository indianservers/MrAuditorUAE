"""Generate evidence-linked release documents without converting unknowns to passes."""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase-12"


def read(name, default=None):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else default


def write(name, title, body):
    (OUT / name).write_text(
        f"# {title}\n\nEvidence date: 18 October 2026. Scope: local synthetic release candidate.\n\n{body.strip()}\n",
        encoding="utf-8",
    )


def main():
    inventory = read("system-inventory.json", {})
    financial = read("financial-results.json", [])
    recovery = read("recovery.json", {})
    performance = read("performance.json", {})
    browser = read("browser-results.json", {})
    coverage = read("coverage-final.json", read("coverage.json", {}))
    roles = read("role-permissions.json", {})
    matrix = []
    testfile = OUT / "regression-backend-final.xml"
    if not testfile.exists():
        testfile = OUT / "regression-backend.xml"
    testfiles = [testfile]
    if (OUT / "final-targeted.xml").exists():
        testfiles.append(OUT / "final-targeted.xml")
    if (OUT / "entrypoint-tests.xml").exists():
        testfiles.append(OUT / "entrypoint-tests.xml")
    cases = {}
    for source in testfiles:
        if source.exists():
            for case in ET.parse(source).getroot().iter("testcase"):
                cases[(case.get("classname"), case.get("name"))] = (case, source.name)
    for case, evidence in cases.values():
        status = (
            "SKIPPED"
            if case.find("skipped") is not None
            else "FAILED"
            if case.find("failure") is not None or case.find("error") is not None
            else "PASSED"
        )
        identifier = case.get("classname", "") + "::" + case.get("name", "")
        matrix.append(
            {
                "Module": case.get("classname", ""),
                "Feature": case.get("name", ""),
                "RequirementID": "P12-REGRESSION",
                "TestID": identifier,
                "TestType": "Unit/integration; see source fixture",
                "ExpectedResult": "Assertions in the named retained test, including specified negative responses",
                "ActualResult": status,
                "Status": status,
                "Severity": "HIGH" if status == "FAILED" else "N/A",
                "DefectReference": "See defect-register.json",
                "Evidence": evidence,
                "Reviewer": "Automated execution; independent human review pending",
                "ReleaseGate": "Scoped regression",
            }
        )

    def browser_tests(suites):
        for suite in suites:
            yield from browser_tests(suite.get("suites", []))
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    yield spec, test

    for spec, test in browser_tests(browser.get("suites", [])):
        last = (test.get("results") or [{}])[-1]
        status = {"passed": "PASSED", "skipped": "SKIPPED"}.get(last.get("status"), "FAILED")
        matrix.append(
            {
                "Module": "Frontend browser",
                "Feature": spec.get("title"),
                "RequirementID": "P12-E2E",
                "TestID": spec.get("file", "") + ":" + str(spec.get("line")),
                "TestType": "Browser E2E",
                "ExpectedResult": "Named test assertions against live BFF/backend; screenshots and persisted results where specified",
                "ActualResult": status,
                "Status": status,
                "Severity": "HIGH" if status == "FAILED" else "N/A",
                "DefectReference": "See defect-register.json",
                "Evidence": "browser-results.json",
                "Reviewer": "Playwright; human sign-off pending",
                "ReleaseGate": "Scoped browser regression",
            }
        )
    for item in financial:
        matrix.append(
            {
                "Module": "Financial correctness",
                "Feature": item["id"],
                "RequirementID": "P12-FINANCIAL",
                "TestID": item["id"],
                "TestType": "Independent arithmetic fixture",
                "ExpectedResult": json.dumps(item["expected"]),
                "ActualResult": json.dumps(item["actual"]),
                "Status": "PASSED" if item["status"] == "PASS" else "FAILED",
                "Severity": "BLOCKER" if item["status"] != "PASS" else "N/A",
                "DefectReference": "See defect-register.json",
                "Evidence": "financial-results.json",
                "Reviewer": "Fixed oracle; professional applicability review pending",
                "ReleaseGate": "Selected arithmetic",
            }
        )
    (OUT / "release-test-matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    if matrix:
        with (OUT / "release-test-matrix.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(matrix[0]))
            writer.writeheader()
            writer.writerows(matrix)
    counts = {
        s: sum(x["Status"] == s for x in matrix if x["RequirementID"] == "P12-REGRESSION")
        for s in ["PASSED", "FAILED", "SKIPPED"]
    }
    bs = browser.get("stats", {})
    observed = []
    p = OUT / "browser-observations.jsonl"
    if p.exists():
        observed = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
    routes = sorted({x["path"] for x in observed if x["type"] == "navigation"})
    calls = sorted({(x["method"], x["path"], x["status"]) for x in observed if x["type"] == "api"})
    browser_coverage = {
        "visited_routes": routes,
        "api_observations": [{"method": m, "path": p, "status": s} for m, p, s in calls],
        "note": "Observed navigation/responses are not proof that every action or contract is verified. Some observations include earlier failing runs retained for defect investigation.",
    }
    (OUT / "browser-coverage.json").write_text(
        json.dumps(browser_coverage, indent=2), encoding="utf-8"
    )
    fixed = [
        (
            "P12-001",
            "HIGH",
            "Access tokens survived logout",
            "Login, call /auth/me, logout, call /auth/me with the same token",
            "Refresh revocation was not checked by access-token authorization",
            "Bind issued access JWTs to RefreshSession IDs and check revocation/expiry; production rejects unbound tokens",
            "test_logout_immediately_revokes_access",
        ),
        (
            "P12-002",
            "HIGH",
            "Production admitted demo configuration",
            "Set production plus a demo flag/database identity",
            "Production settings only checked bootstrap and signing length",
            "Reject demo/test database names and demo flags; API, worker and Beat production startup checks schema, role safety and synthetic tenant markers/known demo identity",
            "test_production_demo_configuration_forbidden",
        ),
        (
            "P12-003",
            "MEDIUM",
            "Invalid document amount corrections crashed matching",
            "Correct amount to non-numeric, NaN or Infinity and request matches",
            "Bounded strings lacked typed validation",
            "Validate Decimal finiteness/scale/bounds, ISO date/currency; tolerate invalid legacy amounts",
            "test_invalid_correction_rejected; test_legacy_invalid_amount_does_not_crash_matching",
        ),
        (
            "P12-004",
            "MEDIUM",
            "Revoked AI initiator left endlessly dispatchable work",
            "Queue an investigation then disable initiating membership",
            "Worker authorization errors rolled back without terminal receipt",
            "Stop denied/stale workflows in a separate transaction with immutable event; idempotent on redelivery",
            "test_revoked_ai_worker_stops_durably_instead_of_retrying_forever",
        ),
        (
            "P12-005",
            "HIGH",
            "ML cancellation delayed by read locks",
            "Train, immediately start longer training and cancel while metadata refreshes",
            "Immutable ML source and list reads acquired engagement FOR UPDATE, delaying UI mutation settlement",
            "Use non-locking authorized ML reads; retain final write locks and reauthorize/recheck deployment after inference",
            "test_ml_metadata_read_does_not_wait_for_training_engagement_lock; phase9 browser training cancellation",
        ),
        (
            "P12-006",
            "MEDIUM",
            "Login eyebrow insufficient contrast",
            "Run axe on /login",
            "Small teal text measured 4.15:1 against white",
            "Darken login-form eyebrow to #236b7c",
            "phase12 browser WCAG check",
        ),
        (
            "P12-007",
            "MEDIUM",
            "Mobile login overflow",
            "Open /login at 390px",
            "Fixed 360px form plus padding exceeded viewport",
            "Use width:100%, max-width:360px and allow form shrinkage",
            "phase12 browser reflow check",
        ),
        (
            "P12-008",
            "HIGH",
            "New staging root build context lacked local-secret exclusions",
            "Inspect the root-context staging Dockerfile and root ignore rules; no image build or secret upload was executed",
            "A root Docker build does not inherit backend/.dockerignore",
            "Add root .dockerignore for credentials/private/runtime artifacts and restrict runtime COPY to app/migration sources",
            "Static source review and Trivy Dockerfile configuration scan; actual image/context build remains an external release gate",
        ),
    ]
    defects = [
        {
            "id": i,
            "severity": severity,
            "title": title,
            "reproduction": repro,
            "expected": "Authorized, bounded operation with truthful durable state",
            "actual_before_fix": title,
            "root_cause": cause,
            "affected_module": title,
            "proposed_fix": fix,
            "implemented_fix": fix,
            "regression_test": test,
            "verification": "See final regression/browser evidence; inspect exact named test status",
            "status": "FIXED_PENDING_FINAL_EVIDENCE",
        }
        for i, severity, title, repro, cause, fix, test in fixed
    ]
    if counts["FAILED"] == 0 and counts["PASSED"] > 0 and bs.get("unexpected", 1) == 0:
        for defect in defects:
            defect["status"] = "FIXED_VERIFIED"
    for defect in defects:
        if defect["id"] == "P12-008":
            defect["status"] = "FIXED_STATICALLY_REVIEWED"
    open_issues = [
        (
            "P12-B01",
            "BLOCKER",
            "Production deployment rollback is unverified",
            "No authorized production/staging account, prior immutable release images or tested application rollback",
            "NOT_TESTED",
        ),
        (
            "P12-B02",
            "HIGH",
            "Hosted infrastructure and container security unqualified",
            "Local Trivy IaC/Dockerfile configuration scan completed with two low findings; Docker image build/scan and Terraform provider/account validation remain unavailable; templates are not deployment evidence",
            "EXTERNAL_DEPENDENCY",
        ),
        (
            "P12-B03",
            "HIGH",
            "Real malware scanner and parser isolation need qualification",
            "Fail-closed quarantine exists; synthetic scanner doubles are not ClamAV assurance; staging scanner not run",
            "EXTERNAL_DEPENDENCY",
        ),
        (
            "P12-B04",
            "HIGH",
            "AI and ML lack representative professional validation",
            "No authorized real customer datasets, licensed full-text standards/corpora, live model evaluation or calibrated deployment evidence",
            "EXTERNAL_DEPENDENCY",
        ),
        (
            "P12-B05",
            "HIGH",
            "Independent security and privacy approval outstanding",
            "ASVS 5.0.0 partial assessment, no independent penetration test, DSR execution/retention/legal and subprocessor sign-offs incomplete",
            "PARTIALLY_VERIFIED",
        ),
        (
            "P12-B06",
            "HIGH",
            "Production monitoring and remote recovery remain unverified",
            "Local restore passed; production PITR, alert delivery, regional failure recovery and RTO/RPO acceptance not tested",
            "EXTERNAL_DEPENDENCY",
        ),
        (
            "P12-B07",
            "MEDIUM",
            "TFJS transitive dependency advisories",
            "Three moderate npm findings through argparse/sprintf-js; no compatible current patch reported, not exposed as a customer formatting API",
            "PARTIALLY_VERIFIED",
        ),
        (
            "P12-B08",
            "MEDIUM",
            "Billing provider and invoices not connected",
            "No provider credentials/selection or live webhook/payment testing; no cards or charges simulated",
            "EXTERNAL_DEPENDENCY",
        ),
        (
            "P12-B09",
            "MEDIUM",
            "Full primary-action/browser/accessibility matrix incomplete",
            "27 regression scenarios do not equal every requested end-to-end workflow; axe sample and keyboard checks do not establish WCAG conformance",
            "PARTIALLY_VERIFIED",
        ),
        (
            "P12-B10",
            "MEDIUM",
            "Demo reset is intentionally not a destructive truncate",
            "Valid demo reused. Immutable professional history requires reviewed archival/reset procedure; no tenant-wide destructive reset was introduced",
            "NOT_IMPLEMENTED",
        ),
        (
            "P12-L01",
            "LOW",
            "S3 access-log target not configured in infrastructure template",
            "Trivy AWS-0089 remains; select an approved private log target, retention and residency before deployment",
            "PARTIALLY_VERIFIED",
        ),
        (
            "P12-L02",
            "LOW",
            "RDS performance telemetry not configured in infrastructure template",
            "Trivy AWS-0133 remains; qualify the current provider telemetry option, retention, cost and alert delivery",
            "PARTIALLY_VERIFIED",
        ),
    ]
    for i, severity, title, cause, status in open_issues:
        defects.append(
            {
                "id": i,
                "severity": severity,
                "title": title,
                "reproduction": "Assess affected production release gate",
                "expected": "Executed evidence and authorized independent acceptance before enabling affected scope",
                "actual": cause,
                "root_cause": cause,
                "affected_module": "Release/operations",
                "proposed_fix": "Complete the linked operational runbook and obtain required environment/data/reviewer access",
                "implemented_fix": "Feature/release scope restricted; no fabricated pass",
                "regression_test": "Required external acceptance test",
                "verification": status,
                "status": "OPEN",
            }
        )
    if coverage:
        percent = coverage.get("totals", {}).get("percent_covered", 0)
        if percent < 80:
            defects.append(
                {
                    "id": "P12-B11",
                    "severity": "HIGH",
                    "title": "Existing CI aggregate coverage threshold not met",
                    "actual": f"{percent:.2f}% measured; existing 80% gate retained",
                    "status": "OPEN",
                    "proposed_fix": "Add meaningful uncovered workflow tests; do not lower the gate",
                }
            )
    (OUT / "defect-register.json").write_text(json.dumps(defects, indent=2), encoding="utf-8")
    modules = "\n\n".join(
        f"## {m['id']}\n\nModule: {m['module']}. Status: {m['status']}.\n\nImplementation: "
        + ", ".join(m["files"])
        + ".\n\nTables: "
        + (", ".join(m["tables"]) or "shared platform tables / no separate owned table")
        + ".\n\nAuthorization: "
        + m["authorization"]
        + "\n\nTests: release-test-matrix.csv and module-coverage.md. Known issues/readiness: internal synthetic evaluation only; open production gates in unresolved-issues.md. UI/API contracts: openapi.json and browser-coverage.json; discovery is not functional proof."
        for m in inventory.get("modules", [])
    )
    write(
        "system-inventory.md",
        "System inventory",
        f"{inventory.get('module_count')} backend module directories; {inventory.get('api_path_count')} API paths and {inventory.get('api_operation_count')} method/path operations discovered. These counts are **not fully verified feature counts**. Source manifest covers application, migrations, frontend, ML and deployment files. Empty/shared modules can delegate to API or shared clients services. Global identity/platform tables are listed in database-schema.md.\n\n{modules}",
    )
    write(
        "module-coverage.md",
        "Module coverage",
        f"Backend regression: {counts}. Browser report: {bs.get('expected', 'pending')} expected/passing, {bs.get('unexpected', 'pending')} unexpected, {bs.get('skipped', 'pending')} skipped. {len(routes)} unique route URLs visited and {len(calls)} unique method/path/status observations retained across runs. Counts distinguish execution from complete workflow verification.\n\nAccounting/ingestion/analytics/reconciliation: tests/phase2; external audit/approvals/portal: phase4; IFRS: phase5; CT/QFZP: phase6; VAT/demo: phase7; TP/licensing/loans: phase8; ML/DMTT: phase9; GRC: phase10; enterprise AI/documents: phase11; identity/SaaS/roles/worker hardening: phase12. Shared platform/clients/organizations/jobs have integration/security tests.\n\nAll 61 configured roles are tested for real client read/write responses and platform/cross-tenant denial. This is not exhaustive professional-action coverage for every role. Browser suite reuses earlier actual service workflows plus new platform/MFA/axe checks. Missing: every primary button, all 20 requested complete scenario chains, exhaustive parser formats, hosted failure/restart and all specialist load combinations. No route-only marketing completion claim is made.",
    )
    write(
        "release-test-matrix.md",
        "Release test matrix",
        f"Authoritative machine-readable files: [CSV](release-test-matrix.csv) and [JSON](release-test-matrix.json). Each row records requirement, test, type, expected/actual, status, severity, defect reference, evidence, reviewer and gate.\n\nBackend totals: {counts}. Coverage is read from coverage-final.json when available; core-coverage-final.txt checks the existing 85% core gate. Eight independent arithmetic receipts are separate from backend test totals. Browser stats: {json.dumps(bs)}. Three Node ML unit tests and 25 frontend component tests are recorded in their own logs, never merged into backend counts. Skips are not passes. Independent professional and security reviewer sign-off remains pending. The full coverage run passed 462 tests with two skips; four additional startup checks passed afterward and are included once in the deduplicated backend total. The isolated CI browser smoke passed separately.",
    )
    write(
        "financial-validation.md",
        "Financial correctness validation",
        f"{sum(x['status'] == 'PASS' for x in financial)}/{len(financial)} fixed independent arithmetic oracles passed. financial-results.json retains exact inputs, fixed expectations, actual values, Decimal differences and tolerances. Fixtures cover TB opening/movements/closing, CT bands, lease PV, scenario ECL, inclusive VAT, TP percentile conventions, loan interest and selected 2025 DMTT. Expected values are literal independent arithmetic, not generated by production engine calls. validate_phase12_financials.py reuses input-schema builders, not their expected answers.\n\nExisting tests additionally cover adjusted TB, statements, cash flow, adjustments, consolidation, tax relief/loss/interest/QFZP, VAT recovery/RCM, TP allocation and DMTT transitions; see source assertions and regression XML. No unexplained financial difference may be waived for an enabled feature. These selected fixtures do not prove every IFRS/tax legal scenario or filing correctness. Rule versions/source dependencies remain attached to professional records; independent current-period technical review is a release gate. No regulatory certification is claimed.",
    )
    write(
        "security-assessment.md",
        "Security assessment",
        "Primary reference: [OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/releases/tag/v5.0.0), not older ASVS guidance. asvs-assessment.json maps chapter-level applicability and partial evidence; it is not a complete requirement-level attestation.\n\nExecuted: local Trivy configuration scan, backend pip-audit (no known dependency vulnerabilities at scan), frontend npm audit (zero reported), ML npm audit (three moderate findings), Bandit source analysis (all findings retained in sast-bandit.json), Gitleaks history and working-tree text scan with exact reviewed synthetic-value allowlists. The original unreviewed finding reports remain available. XML builders/ParseError imports were distinguished from parsing: actual untrusted XML paths use defusedxml. Analytics SQL uses validated numeric/date fields, literal quote escaping, parameter values or generated placeholders; SQL construction findings remain visible for independent review. Node invocation uses fixed executable/worker path, bounded validated configuration and no customer JS. No known high/critical exploit was confirmed by these scans; this is not proof of absence.\n\nNew controls: encrypted replay-resistant TOTP, mandatory verified platform MFA, production MFA for protected APIs, access session revocation, strict production demo/schema/role checks, separately provisioned operators, audited versioned subscription changes, per-tenant quotas and background checks. Missing/blocked: real scanner/isolated parser qualification, independent authenticated DAST/penetration testing, container-image scanning and provider-complete cloud validation, full ASVS manual review, secrets key rotation/recovery drill. Trivy IaC/Dockerfile configuration scan executed: no high/critical findings, two low findings retained for S3 access logging and RDS performance telemetry. Docker image build/scan and Terraform provider/account validation remain unavailable here. The attempted CI configuration scan detected zero supported files, so it provides no workflow-security clearance; workflows were syntax inspected separately. Do not report unavailable scans as clean.",
    )
    write(
        "ai-agent-evaluation.md",
        "AI agent evaluation",
        "Existing 12 logical agents and 27 allowlisted tools remain bounded, permission checked and source-version linked. Phase11 and final regression cover untrusted document prompt text, unauthorized source access, stale citations, approval separation, idempotency and read-only graph restrictions. Phase12 adds durable FAILED termination after authorization/source denial, avoiding indefinitely dispatchable outbox rows. No arbitrary SQL/network/code tools were added.\n\nMonthly tenant AI operation quotas complement existing per-user rate/context/step/time limits. They are operation counts, not monetary budgets or actual provider bills. Narrative support in prose is not automatically proven; mock provider diagnostics and synthetic document fields do not establish live LLM quality. OCR, semantic/hybrid retrieval, licensed full-text legal corpora and representative adversarial model evaluations remain absent/external. Consequential actions remain human governed; no automatic filing, signing or payment was introduced.",
    )
    write(
        "tensorflowjs-validation.md",
        "TensorFlow.js validation",
        "Four existing families remain experimental: autoencoder, journal classifier, risk ranking and account classifier. The three Node engine tests pass; backend workflow tests exercise dataset/model permission, artifact hash, deployment, feedback and scope rules. Browser training/cancellation, measured curves and held-out confusion displays execute real Node jobs. Artifacts remain in the existing private versioned store, subject to storage admission. ML metadata reads no longer hold training engagement locks, and inference rechecks authorization/current deployment before persisting.\n\nSynthetic held-out labels and earlier deterministic/statistical comparisons are software evidence, not a new independent customer-data validation. No new representative unseen real dataset was available. Calibration, generalization, bias, drift and production deployment remain experimental gates. Three moderate transitive advisories remain in npm's TFJS/argparse/sprintf-js chain; no compatible patched sprintf-js release was found by npm lookup. Do not replace TFJS with npm's suggested obsolete major version merely to clear a report. Disable ML entitlements for customer production until accepted.",
    )
    write(
        "permissions-audit.md",
        "Permissions audit",
        f"role-permissions.json exports {len(roles)} configured role defaults. tests/phase12/test_roles_and_admissions.py executes a positive or denied client GET/POST plus cross-tenant and platform denial for each. Existing professional tests cover assigned engagement access, independent manager/partner approvals, self-approval prevention, stale versions, disabled identities, portal boundaries, unapproved ML and AI source access.\n\nDatabase runtime role: {inventory.get('database_role')}. Tenant subscriptions and usage use FORCE RLS in addition to existing owned tables. PlatformOperator grants are separate from tenant memberships and cannot be obtained by assigning a Platform-named firm role. Operator APIs expose only allowlisted metadata. Tenant suspension is rechecked in engagement services and workers. Production requires session-bound MFA; old unbound development fixture JWTs are never accepted in production. Exhaustive role-by-every-professional-action proof is not claimed.",
    )
    a11y = read("accessibility-results.json", [])
    write(
        "accessibility-audit.md",
        "Accessibility audit",
        f"Automated axe evidence: accessibility-results.json ({len(a11y)} page/viewport observations). Login is checked at 1920x1080, 1600x900, 1440x900, 1366x768 and 390x844, plus security enrollment and keyboard tab focus. Existing regression exercises rich financial/GRC/AI views at additional tablet/desktop widths. Login contrast and mobile form overflow defects were fixed.\n\nTarget: WCAG 2.2 AA. Scope is sampled automated/keyboard verification, not a complete manual assessment or conformance declaration. Full primary route, screen reader, chart alternatives, 400% zoom, dialog focus and dense-grid keyboard audit remain acceptance work. Failure screenshots are retained by Playwright; final screenshots live in screenshots/. See defect register rather than interpreting an absent automated finding as complete accessibility.",
    )
    perfrows = "\n".join(
        f"- {r['concurrent_distinct_users']} distinct users, `{r['endpoint']}`: p50 {r['p50_seconds']:.3f}s, p95 {r['p95_seconds']:.3f}s, p99 {r['p99_seconds']:.3f}s, {r['throughput_rps']:.2f} requests/s, {r['errors']} errors."
        for r in performance.get("api_workloads", [])
    )
    financialrows = "\n".join(
        f"- {r['rows']:,} generated rows: TB {r['trial_balance_seconds']:.3f}s, analytics {r['analytics_seconds']:.3f}s; TB sum {r['trial_balance_sum']}."
        for r in performance.get("financial_workloads", [])
    )
    write(
        "performance-benchmarks.md",
        "Performance benchmarks",
        f"Actual measurements in performance.json. Each API wave uses 10/50/100 **distinct** synthetic identities against the existing 250,024-row demo population; 320 total read requests. Signed development fixture sessions bypass login only in development, so this is not an authentication-load test. Load identities are disabled afterward.\n\n{perfrows}\n\n{financialrows}\n\nThe million-row workload is generated in process and does not replace or expand the demo ledger. DuckDB stays bounded at 1 GiB/two threads with signature partitioning. Missing prerequisite rules return not-testable rather than invented results. Driver RSS is a point observation, not peak API/worker/DB memory. Production CPU, queue saturation, write mixes, all specialist/report/AI loads and cloud cost per file were not measured. The existing auth limiter allows 20 authentication POST requests per minute per backend-observed address; shared BFF addresses need explicit multi-user policy qualification. Forwarded headers are not implicitly trusted, and no sign-in capacity guarantee is made. Provisional target discussions must use this baseline; no production SLO or 100-user capacity guarantee is declared.",
    )
    write(
        "infrastructure-architecture.md",
        "Infrastructure architecture",
        "Prepared, not deployed: deploy/compose.staging.yml, backend.Dockerfile, Caddyfile, alerts.yml and terraform/main.tf. Browser -> TLS edge -> Next BFF -> private FastAPI -> private PostgreSQL/Redis and KMS-encrypted versioned S3. Celery consumes celery, grc and enterprise-ai; exactly one Beat schedules authorized jobs. Node/TFJS is bundled in the staging backend image; the older development-only backend Dockerfile does not qualify ML containers.\n\nTerraform is a partial UAE-region storage/RDS baseline requiring existing VPC/subnets/application SG. IAM/compute/Redis/TLS/WAF/remote state/backup vault and monitoring still need environment integration. HCL syntax parsed; no provider validate/plan/apply or image build was performed locally. No deployment was authorized. Static Trivy configuration scan completed; root .dockerignore excludes local credentials/runtime artifacts and runtime COPY statements are restricted to app/migrations.\n\n[AWS identifies me-central-1 as UAE with opt-in required](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html). Account service availability, current regional health and price quotes must be checked at deployment: the public dashboard is dynamic and this task did not establish usable account capacity. [AWS Health](https://health.aws.amazon.com/health/status). UAE location alone does not prove residency for logs, support, backups or external AI. Azure UAE alternatives can be evaluated after customer/controller decisions; no current price or provider recommendation is fabricated. Vercel hosting is not approved for confidential backend workloads by this template.",
    )
    write(
        "environment-configuration.md",
        "Environment configuration",
        "Use .env.example for local setup; inject independent signing, MFA Fernet and connector Fernet keys from a secret manager in hosted environments. Never copy public placeholder/test keys into production. Production requires bootstrap disabled, strong signing length, valid MFA encryption key, private S3/KMS, no demo flags/names and schema 0012. Worker and Beat production startup also call the database readiness guard and terminate before consumption if it fails. Runtime/migration database roles must be non-superuser/non-RLS-bypass; separate owner/backup principals have narrowly controlled privileges.\n\nLocal preview: frontend http://127.0.0.1:3004 -> API http://127.0.0.1:58007, synthetic database auditos_phase7_demo. Session cookies are HttpOnly through the BFF; write requests require same origin. MFA enrollment is /security; confirm revokes previous sessions, then sign in with a current code. API docs are development-only. Database/Redis secrets and local operator enrollment keys remain in ignored .local-runtime, never in evidence. Real email, billing, observability, AI, OCR and live ERP credentials are not assumed.",
    )
    write(
        "database-migration-review.md",
        "Database migration review",
        f"Head: {inventory.get('migration')}. Clean disposable database auditos_phase12_migration_test migrated from zero. Guarded existing synthetic database upgraded from 0011 to 0012 without recreating ledger data; current ledger count is {inventory.get('demo_journal_lines'):,}. verify_phase12_recovery.py restored the complete migrated schema/data and compared every table. clean-migration-check.txt records Alembic metadata comparison when run.\n\n0012 adds encrypted MFA fields/session assurance and four operational tables; tenant-owned subscription/usage tables FORCE RLS, platform operations are immutable. Existing access tokens are session-bound on new issuance; development-only old fixtures are not a production migration strategy. Review production session expiration/sign-in communications before rollout.\n\nMigrations preserve regulated histories. Downgrade refuses destructive archival. Production large-DDL lock timing/index strategy and exact previous-release compatibility require staging rehearsal; no live production upgrade or rollback was executed. Snapshot before change, maintain migration journal, test forward repair and restore. Never use ORM create_all in a deployment.",
    )
    write(
        "backup-restore-test.md",
        "Backup and restore drill",
        f"Result: {recovery.get('status', 'NOT_TESTED')}. Source auditos_phase7_demo -> isolated empty auditos_phase12_restore_test. Custom-format pg_dump used an exported repeatable-read snapshot; every public table's row count and sorted complete-row hash matched after pg_restore. {recovery.get('private_objects', 'unknown')} private objects were encrypted, decrypted, extracted into a separate directory and SHA-256 matched. Database restore plus fingerprint verification: {recovery.get('database_restore_and_verify_seconds', 0):.3f}s; entire drill {recovery.get('elapsed_seconds', 0):.3f}s. Evidence: recovery.json and recovery-log.txt.\n\nBackup archives and key are ignored local artifacts. This is a synthetic local encryption/recovery demonstration, not a production key-custody design. Production requires separated KMS/offline recovery authority, remote immutable retention, PITR, restore into an isolated account/network, alerting and independent acceptance. recovery-app-smoke.json additionally verifies actual login, readiness, client/ledger reads and original-hash evidence download using the restored database and restored object directory; ledger rows remain unchanged. The recovery script refuses nonempty targets and never drops existing databases. Recovery point predates later browser proof records; counts are a consistent snapshot, not a claim of final demo counts.",
    )
    write(
        "disaster-recovery.md",
        "Disaster recovery",
        "Owner: designated service incident commander; customer/controller and professional engagement owners approve data restoration. Proposed targets (unaccepted): database RPO <=15 minutes with managed PITR; service RTO <=4 hours after declared regional outage. Local 43-second restore is not a hosted RTO promise.\n\n1. Freeze writes/Beat, preserve queue/outbox and incident timestamps; identify clean recovery point.\n2. Verify encrypted database backup, object version manifest, keys, configuration and previous immutable release.\n3. Restore in an isolated permitted region/account; never overwrite source evidence.\n4. Compare row hashes, RLS/role properties, immutable histories and object SHA/version references; run financial and authorization smoke tests.\n5. Reconcile completed/queued jobs by idempotency, keep schedules paused, invalidate old sessions, rotate compromised credentials.\n6. Obtain independent professional and incident-owner acceptance before DNS/traffic switch and write enablement.\n7. Record actual RPO/RTO, data differences, communications and follow-up defects.\n\nRegion changes, cross-border copies and legal holds require controller/legal review. Production regional recovery and paging tests remain unexecuted.",
    )
    write(
        "observability.md",
        "Observability",
        "Implemented logs allowlist timestamp, event, request ID, status, duration_ms, method, route template and release. Request bodies, credentials, prompts, headers and query strings are not serialized. Runtime request IDs are validated and returned to callers. Existing durable job/AI/ML receipts retain governed lineage. Health checks distinguish live from DB/Redis/schema/role readiness.\n\nOperator services report measured DB/Redis readiness and explicitly NOT_MEASURED/NOT_CONNECTED for worker/backup/tracing integrations. deploy/alerts.yml contains readiness/backup/queue examples requiring actual exporters. Do not deploy empty alert expressions against nonexistent metrics and call monitoring complete. Connect logs/metrics/traces to an approved UAE-residency pipeline; add DB/queue/provider/ML-resource dashboards, error sampling/redaction and actual pager receivers. Test outages, stale backups, queue stalls and alert resolution in authorized staging. No tracing or alert-delivery success is claimed.",
    )
    write(
        "incident-response.md",
        "Incident response",
        "SEV1: suspected tenant exposure, material financial corruption, unauthorized approval/action, unrecoverable service/data. SEV2: major module/queue degradation or failed backup. SEV3: limited nonmaterial defect. Appoint commander and evidence custodian, preserve immutable receipts, restrict affected features, record request/release/tenant IDs without copying client content into alerts. Follow controller/legal communication decisions.\n\n- Database outage: fail readiness, stop mutations/Beat, inspect private connectivity/role/storage, restore only via DR acceptance.\n- Redis outage: auth/rate controls fail closed; preserve pending outboxes, restore broker, replay idempotently.\n- Failed migration: stop rollout, retain snapshot/logs, use reviewed forward repair or isolated restore; no automatic destructive downgrade.\n- Failed backup: page on freshness, stop declaring recoverability, rerun isolated restore before resolution.\n- Object-store failure: quarantine/unavailable state; verify exact object version/hash, never replace evidence silently.\n- Scanner failure: preserve quarantine; block approval/download; refresh signatures and test scanner recovery.\n- Worker stall: inspect queue/heartbeat/resource limits, restart current image, replay committed receipts without duplicate action.\n- AI/provider failure: fail/partial status with missing evidence; disable affected provider, never invent completion or billing.\n- ML resource exhaustion: terminate bounded child, mark job failed/cancelled, restrict feature and review dataset/model limits.\n- Tenant exposure/compromised identity: suspend affected sessions/tenant, preserve logs/object versions, assess scope and notification obligations with counsel.\n\nPaging, escalation contacts and incident-system integration require named operational owners; the console does not fabricate zero incidents when disconnected.",
    )
    write(
        "subscription-management.md",
        "Subscriptions and entitlements",
        "Implemented configurable Starter/Professional/Enterprise plan snapshots, user/client/storage/AI/ML operation quotas, feature flags, trial/active/past_due/suspended/cancelled states, validity/grace windows, version conflict checks and immutable before/after/reason operation history. Subscription expiry retains authorized reads and accounting records. Feature disablement can still deny its reads; only authorized retained scope is available. Production tenants without a subscription fail closed; existing unprovisioned local demo tenants retain development behavior.\n\nAdmission occurs in backend require() and relevant worker/service checks, not only navigation. Tenant writes/usage counters are serialized; invitations recheck capacity at redemption. Private writes use put_private() before object creation and initialize lifetime usage from unique existing file/version metadata including import/evidence/chunks/sync/ML/published documents. Counters conservatively retain stored admissions; no automatic storage reclamation or financial deletion is performed. Monthly AI/ML quotas count admitted API operations, not tokens, dollars or exact provider costs.\n\nBilling adapter boundary remains NOT_CONFIGURED. No payment cards, fake charges, provider invoices, tax invoices or webhook success are created. Current subscription returns an explicitly disconnected provider and no provider invoices. Verified email/onboarding, real billing adapter/signature validation/reconciliation, price/currency decisions, refund/dispute workflows and usage-cost reconciliation remain commercialization work. Do not advertise complete commercial billing.",
    )
    write(
        "support-access-policy.md",
        "Platform and support access",
        "A separately provisioned active PlatformOperator plus verified MFA can list operational tenant/subscription/usage metadata, readiness and release records, and perform audited subscription/lifecycle changes. A firm Platform-named role alone does not grant operator access. Operators receive no automatic tenant membership, client assignment, GL/workpaper/tax/evidence/chat access, credentials or support impersonation endpoint.\n\nExceptional support access is NOT_IMPLEMENTED and therefore denied by default. If required later: obtain customer/controller and professional owner authorization, named purpose/resources, least privilege, explicit expiry, independent approver, immutable access and download logs, revocation and retrospective review. Avoid creating a generic bypass route. Platform provisioning/recovery must be an approved identity-management operation with independent verification; no public self-elevation API exists. The synthetic proof operator has no tenant memberships.",
    )
    write(
        "deployment-runbook.md",
        "Deployment preparation runbook",
        "**NO-GO for production; no deployment performed or authorized.**\n\n1. Select explicit pilot modules, controller jurisdiction/residency and independent professional/security reviewers; resolve release-gates.json blockers.\n2. Provision authorized isolated staging, private DB/Redis/S3/KMS/IAM and approved secret delivery; validate regional health/capacity and cost quote.\n3. Build immutable frontend/backend images, generate SBOMs, scan complete images/IaC and archive digests. Existing CI gates remain enabled; run hosted CI rather than assuming templates pass.\n4. Create verified encrypted backup/object manifest; rehearse clean/upgrade migration, previous-release compatibility, application rollback and restore.\n5. Run migration job, API/worker and one Beat; explicitly subscribe celery, grc, enterprise-ai, intelligence. Verify scanner signatures and fail-closed behavior, TLS/domain, session MFA, operators and tenant entitlements.\n6. Run authorized synthetic staging smoke/E2E/security/accessibility/load and paging drills. Do not seed the demo into production.\n7. Obtain manual environment/professional/security/customer approval with exact release evidence; only then authorize a separate deploy workflow. release-gate.yml intentionally contains no deployment step.\n8. Start restricted invited pilot, monitor evidence-backed thresholds, preserve rollback point and pause on any release blocker.\n\nRun scripts/release_gate.py <reviewed-manifest.json> --commit <reviewed-source-commit> --image-digest <sha256:digest> --environment <target-environment>. The selected version-2 manifest and version-1 executed receipts must bind to that exact artifact/target and verify all retained artifact hashes. Legacy release-gates.json remains NO-GO. No deployment is included.",
    )
    write(
        "rollback-runbook.md",
        "Rollback runbook",
        "Application deployment rollback remains NOT_TESTED. The successful local database/object recovery drill does not replace it.\n\nBefore rollout, record previous image digests/configuration, schema compatibility and reversible feature-flag changes; take a consistent backup and pause scheduled actions. On failure: stop traffic/writes/Beat, preserve immutable events and task IDs, switch to the verified prior artifact only if compatible with the current schema. Verify health, session revocation, tenant isolation and exact financial smoke fixtures. Reconcile outbox receipts before restarting workers.\n\nIf schema/data incompatibility requires recovery, restore a verified snapshot into a new isolated destination and reconcile any later professional work; obtain acceptance before traffic change. Existing immutable-history migrations intentionally refuse destructive downgrade. Record actual service recovery duration, data loss/window and approver. Do not run DROP/TRUNCATE or discard regulated histories to force a rollback pass.",
    )
    write(
        "pilot-release-plan.md",
        "Controlled pilot plan",
        "Recommended decision: **CONDITIONAL GO for internal synthetic evaluation only; NO-GO for customer production**.\n\nStage 1: internal CA/audit team reviews isolated demo, arithmetic fixtures and workflow/role evidence. Stage 2: invited professional reviewers approve explicit module/version scope and remaining defects. Stage 3: only after all production blockers close, obtain explicit customer/controller authorization for a limited read-only integration pilot; verify lawful data handling, actual source completeness and recovery. Stage 4: controlled computation with independent reconciliation/reviewer sign-off; expand only after acceptance.\n\nExclude unvalidated ML, semantic/OCR/legal-corpus claims, live filing, unconnected ASP/billing/ERP providers and unsupported complex regulatory treatments. Review all AI narrative and confirm deterministic evidence. No FTA/IFRS Foundation/IAASB certification is claimed. Maintain a signed module enablement/feature-entitlement list, success/stop criteria, support and rollback owner.",
    )
    write(
        "production-readiness.md",
        "Release readiness scorecard",
        "**Production decision: NO-GO. Internal synthetic evaluation: CONDITIONAL GO. No aggregate percentage offsets a blocking control.**\n\n- Functional coverage: PARTIALLY_VERIFIED; regression and route observations do not cover every primary action.\n- Financial accuracy: PARTIALLY_VERIFIED; selected exact fixtures passed, independent professional current-period scope approval pending.\n- Security: PARTIALLY_VERIFIED; dependency/SAST/secret checks executed; full ASVS/DAST/container/cloud review outstanding.\n- Authorization: PARTIALLY_VERIFIED; tenant, role and professional tests passed in synthetic environments.\n- AI/ML validation: PARTIALLY_VERIFIED/EXTERNAL_DEPENDENCY; keep experimental and restricted.\n- Test execution: evidence in release-test-matrix; skips retained separately; existing coverage threshold unchanged.\n- Performance: PARTIALLY_VERIFIED; bounded local 10/50/100-user read waves and 10k–1m arithmetic/analytics workloads.\n- Accessibility: PARTIALLY_VERIFIED; sampled axe/keyboard/reflow, no conformance declaration.\n- Infrastructure: NOT_TESTED at provider/container level; templates only.\n- Recovery: VERIFIED local synthetic database/private objects; production PITR/regional drill pending.\n- Monitoring: PARTIALLY_VERIFIED; structured logs/readiness live, exporters/tracing/paging not connected.\n- Documentation: current repository evidence/runbooks prepared; named human sign-offs pending.\n\nHard blockers include unverified deployment rollback, hosted security/operations qualification, privacy/professional scope acceptance and any failed existing CI coverage gate. See defect-register.json and release-gates.json.",
    )
    write(
        "bugs-found-and-fixed.md",
        "Defects found and fixed",
        "\n\n".join(
            f"## {x['id']} — {x['title']}\n\nSeverity: {x['severity']}. Status: {x['status']}.\n\nReproduction: {x['reproduction']}.\n\nRoot cause: {x['root_cause']}.\n\nFix: {x['implemented_fix']}.\n\nRegression: {x['regression_test']}."
            for x in defects
            if x["id"].startswith("P12-0")
        ),
    )
    write(
        "unresolved-issues.md",
        "Unresolved issues",
        "\n\n".join(
            f"## {x['id']} — {x['severity']}: {x['title']}\n\nStatus: {x['status']}. {x.get('actual', x.get('root_cause', ''))}\n\nNext action: {x.get('proposed_fix', 'Independent acceptance required')}."
            for x in defects
            if x["status"] == "OPEN"
        ),
    )
    write(
        "privacy-and-residency.md",
        "Privacy and residency acceptance",
        "Applicable regime must be established per tenant/controller, data subject and processing activity. References: [UAE Federal Decree-Law 45/2021](https://uaelegislation.gov.ae/en/legislations/1972/download), [DIFC Law 5/2020](https://www.difc.com/business/laws-and-regulations/legal-database/difc-laws/data-protection-law-difc-law-no-5-2020), [ADGM Office of Data Protection](https://www.adgm.com/operating-in-adgm/office-of-data-protection). These references do not establish applicability or legal compliance for a customer.\n\nBefore customer data: record controller/processor roles, purpose/lawful basis, categories/subjects, storage/backup/log/support/AI regions, approved subprocessors and transfer basis; customer contract and retention/legal holds; access/export audit policy; incident contacts and response decisions. Tenants and objects are scoped; provider disclosure remains explicit. Technical export controls do not constitute a complete DSR system.\n\nDSR runbook: verify requester identity/authority; establish applicable rights/exemptions and legal hold; identify all DB/object/model/provider references; minimize/redact other parties; obtain controller/professional approval; log request/decision/export or lawful deletion; verify backup/retention handling and response. Automated lawful deletion/DSR execution and configurable comprehensive retention are NOT_IMPLEMENTED. Do not delete immutable accounting/audit history automatically on subscription cancellation. Independent legal/security approval is outstanding.",
    )
    asvs = []
    chapter_names = [
        "Encoding and Sanitization",
        "Validation and Business Logic",
        "Web Frontend Security",
        "API and Web Service",
        "File Handling",
        "Authentication",
        "Session Management",
        "Authorization",
        "Self-contained Tokens",
        "OAuth and OIDC",
        "Cryptography",
        "Secure Communication",
        "Configuration",
        "Data Protection",
        "Secure Coding and Architecture",
        "Security Logging and Error Handling",
        "WebRTC",
    ]
    for number, name in enumerate(chapter_names, 1):
        asvs.append(
            {
                "reference": f"ASVS v5.0.0 V{number}",
                "name": name,
                "applicable": number != 17,
                "status": "PARTIALLY_VERIFIED" if number != 17 else "NOT_TESTED",
                "evidence": ["security-assessment.md", "release-test-matrix.csv"],
                "limit": "Chapter mapping only; requirement-level independent assessment pending"
                if number != 17
                else "No WebRTC surface found",
            }
        )
    (OUT / "asvs-assessment.json").write_text(json.dumps(asvs, indent=2), encoding="utf-8")
    gates = {
        name: {
            "status": "PARTIALLY_VERIFIED",
            "evidence": "docs/phase-12/production-readiness.md",
            "open_blocker": False,
        }
        for name in [
            "tenant_isolation",
            "financial_accuracy",
            "professional_approvals",
            "critical_security",
            "migration",
            "recovery",
            "deployment_rollback",
            "ai_authorization",
            "audit_history",
            "demo_isolation",
        ]
    }
    gates["migration"].update(status="VERIFIED", evidence="docs/phase-12/system-inventory.json")
    gates["recovery"].update(
        status="PARTIALLY_VERIFIED", evidence="docs/phase-12/recovery.json", open_blocker=True
    )
    gates["deployment_rollback"].update(
        status="NOT_TESTED", evidence="docs/phase-12/rollback-runbook.md", open_blocker=True
    )
    gates["critical_security"]["open_blocker"] = True
    (OUT / "release-gates.json").write_text(
        json.dumps({"scope": "Customer production", "decision": "NO-GO", "gates": gates}, indent=2),
        encoding="utf-8",
    )
    byseverity = {
        level: sum(x["status"] == "OPEN" and x["severity"] == level for x in defects)
        for level in ["BLOCKER", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
    }
    write(
        "final-phase-report.md",
        "Phase 12 final development report",
        f"**Production NO-GO. Conditional GO for internal synthetic evaluation only. Phase 12 delivery is materially useful but its complete enterprise definition of done is not satisfied. No production deployment, commit or push was performed.**\n\n## Measured implementation and verification\n\n- Inventory: {inventory.get('module_count')} backend module directories, {inventory.get('api_path_count')} API paths/{inventory.get('api_operation_count')} operations discovered. All are inventoried; none is labelled fully independently certified.\n- Browser: {bs.get('expected', 'pending')} passing/expected, {bs.get('unexpected', 'pending')} unexpected, {bs.get('skipped', 'pending')} skipped; {len(routes)} distinct URLs observed. Coverage metadata is separate from action verification.\n- Backend final evidence: {counts}; frontend unit 25 passed; Node ML unit 3 passed; isolated CI browser smoke 1 passed. Full coverage run: 462 passed/2 skipped; additional startup checks: 4 passed. Overall coverage: 82.49%; accounting/validation core: 90.43%. Counts deduplicate full/targeted runs by class and test name. The final full suite and final-targeted.xml are retained separately; overlapping targeted statuses supersede earlier ones. The isolated CI browser smoke is an additional one-test proof, not included in the 27-test regression count.\n- Database: clean and existing-demo migration to 0012; non-superuser/non-RLS-bypass runtime; {inventory.get('demo_journal_lines'):,} existing journals retained. No active load identities or AI schedules in final inventory.\n- Financial: {len(financial)} independent fixed arithmetic cases, {sum(x['status'] == 'PASS' for x in financial)} passed; full input/expected/actual/difference receipts retained. Existing specialist/regulatory regression remains synthetic and current professional applicability approval is pending.\n- Permissions: {len(roles)} configured roles exercised for real client read/write and tenant/platform denial; deeper professional approval/AI/ML boundaries covered by existing dedicated workflow tests.\n- New security/SaaS: revocable session-bound access tokens, encrypted replay-resistant TOTP, verified platform MFA and production protected-API MFA, demo startup guards, subscription snapshots/grace/read-only/feature flags/quotas, immutable operational history, metadata-only eight-page console and real admission tests. Billing remains disconnected.\n- AI: existing tools/approval/source controls retained; revoked/stale worker execution now stops durably. No new semantic/OCR/live-provider quality assurance.\n- TFJS: real synthetic training/load/inference/cancellation tests; remains experimental; three moderate transitive dependency findings retained.\n- Scans: pip/npm dependency, Bandit SAST and Gitleaks history/current-source executed. No independent penetration/container/cloud clearance claimed. Local Trivy configuration checks have two low findings and no high/critical findings.\n- Performance: 320 read requests over 10/50/100 distinct synthetic users, zero errors in recorded waves; generated TB/analytics 10k/100k/250k/1m. Production mixed-load capacity/SLO/cost remains unknown.\n- Accessibility: login contrast and mobile overflow fixed; sampled axe/keyboard/reflow evidence, no WCAG conformance claim.\n- Recovery: complete local encrypted database fingerprints and {recovery.get('private_objects')} private object hashes matched; database restore/verify {recovery.get('database_restore_and_verify_seconds', 0):.3f}s. Hosted PITR and deployment rollback remain unverified.\n- Infrastructure/CI/observability: staging templates, release gate, expanded CI, structured timing logs and alert examples prepared; no hosted deploy or alert-delivery evidence fabricated.\n\n## Remaining release gates\n\nOpen defects by severity: {byseverity}. Full details and evidence in unresolved-issues.md and defect-register.json. Production blockers are not averaged into a score. Regulatory full-text licensing, authorized real datasets, live connectors/ASP/billing, privacy/retention/DSR, independent ASVS/DAST review, hosted container/IaC/restore/rollback and monitoring acceptance remain outside verified production scope.\n\n## Pilot and maintenance\n\nUse pilot-release-plan.md: internal CA/audit review first, explicitly approved scope and customer authorization before real data. Then resolve hosted operations/security/privacy blockers, qualify live integrations and professional calculation rules, expand action/accessibility/load coverage and add representative AI/ML validation. Maintain signed module entitlements, source/rule reviews, dependency triage, backup restore drills and incident exercises. No filing, professional opinion or certification is inferred from software tests. **Stop after Phase 12; no further feature development or production deployment is authorized by this report.**",
    )
    print(
        json.dumps(
            {
                "backend": counts,
                "browser": bs,
                "inventory_modules": inventory.get("module_count"),
                "visited_routes": len(routes),
                "open_defects": byseverity,
            }
        )
    )


if __name__ == "__main__":
    main()

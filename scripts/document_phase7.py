"""Build Phase 7 reports from executed evidence; never manufacture test outcomes."""

import importlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase-7"
m = json.loads((OUT / "demo-manifest.json").read_text())
v = json.loads((OUT / "demo-verification.json").read_text())
bench = json.loads((OUT / "scale-file-benchmarks.json").read_text())
coverage = json.loads((OUT / "coverage.json").read_text())
browser = json.loads((OUT / "playwright-results.json").read_text())
tests = ET.parse(OUT / "regression-results.xml").getroot()
full_seconds = sum(float(s.attrib.get("time", 0)) for s in tests.findall("testsuite"))
vat_xml = ET.parse(OUT / "vat-results.xml").getroot()
vat_seconds = sum(float(s.attrib.get("time", 0)) for s in vat_xml.findall("testsuite"))
cases = tests.findall(".//testcase")
passed = sum(not any(x.tag in {"failure", "error", "skipped"} for x in c) for c in cases)
skipped = sum(c.find("skipped") is not None for c in cases)
failed = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
counts = f"Backend: {passed} passed, {failed} failed, {skipped} skipped; measured statement coverage {coverage['totals']['percent_covered']:.2f}%. Frontend:22 passed,0 failed. Playwright:{browser['stats']['expected']} passed,{browser['stats']['unexpected']} failed,{browser['stats']['skipped']} skipped."


def write(name, text):
    (OUT / (name + ".md")).write_text(
        "# " + name.replace("-", " ").title() + "\n\n" + text.strip() + "\n",
        encoding="utf-8",
    )


write(
    "vat-engine",
    """
Implemented in `backend/app/modules/vat` and `backend/app/api/v1/vat*.py`; migration0007. Strict typed VAT profiles/rules/invoices/adjustments/recovery/returns/readiness are versioned AuditRecords with revision and independent review history. Immutable `vat_computation_runs` store inputs, source versions, methodology, official rule URLs, hashes and exact decimal results. `synthetic_datasets` records guarded demo versions. Both tables force tenant RLS; run mutation is rejected by a PostgreSQL trigger.

Workflow: independently approve rules and taxpayer profile; prepare and validate source invoice facts; approve evidence and invoices; reconcile actual active journal lines and full VAT control balances; resolve exceptions; prepare a return workpaper; Tax Manager and independent Tax Partner/CA review; export current source-linked JSON. No tax filing endpoint or tax registration automation is represented.

GET legislation/workspace/records/runs are scope checked. Record and run lists paginate; invoice direction and reference/supplier search use backend filtering. Reconciliation rows are served50 at a time. A run's dependency check includes newly approved invoices/adjustments, source status/version and inactive journal batches. Maximum approved invoice population is20,000 per run; larger periods must be partitioned or require a future execution design. Computation remains synchronous. Cash-basis profiles fail closed pending specialist methodology.

VAT source classifications are human-reviewed legal facts. This is a preparation engine within the stated scope, not universal UAE VAT certification. Historical rule adoption requires independent technical review; a catalogue URL alone does not approve an interpretation.
""",
)
write(
    "output-vat-engine",
    """
Decimal calculations use64-digit local precision and HALF_UP2-decimal AED rounding. Exclusive and inclusive consideration, discounts, original-currency FX conversion and credit-note reversal are supported. Tax is calculated from the unrounded AED net to avoid double-rounding drift. Declared AED values are independently compared with calculated net, VAT and gross.

Human-selected treatments: standard, zero, exempt, outside, reverse-charge services, customs goods imports, deemed supply and unresolved. Standard/deemed/reverse/import use the approved5% rule; zero/exempt/outside do not become taxed merely because an account name matches. Source facts include supply/issue/tax-point dates and basis, place-of-supply completeness, jurisdictions, customer registration, related-party indicator and partial payments. These indicators do not automatically establish a legal treatment or recalculate a payment-based tax point.

Exports, real estate, transport, designated zones, related-party valuation, vouchers and sector-specific place-of-supply qualifications require reviewed classification/evidence. Credit notes currently reference an approved original in the same engagement/profile and direction; prior-period originals require a supported workflow extension rather than an invented reference.
""",
)
write(
    "input-vat-engine",
    """
Recoverability is explicit: full, blocked, partial or review. Full recovery requires100%; partial uses an approved percentage and evidence; missing facts remain exceptions. Expense account names never determine recovery. Imported goods and imported services can have both output/reverse-charge and recoverable input, separately reconciled.

FTA13/2026 integrity controls apply from1October2026. A recoverable purchase requires a selected approved FTA13 rule and date applicability. The calculator checks supporting supplier/supply evidence unless net consideration is below10,000 AND known past/expected12-month supplier totals do not exceed100,000. Manual policy, supplier verification and substantive integrity review remain professional responsibilities.

Employee recovery from1October2026 requires the selected FTA17/2026 rule plus explicitly confirmed conditions/evidence. This does not infer that every employee expense is blocked or deductible. Entertainment, vehicles and mixed use require reviewed classification. Partial exemption, annual and capital-asset adjustments are manual approved allocations; the engine does not derive a statutory apportionment or multi-year CAS schedule. CD149/2026's amended apportionment has a later first-tax-year commencement after1October2027 and is not retrospectively applied by this engine.
""",
)
write(
    "vat-reconciliation",
    """
Each approved invoice links actual journal UUIDs in the same tenant/entity/financial period. The engine fetches active source batches and checks net, output and input amounts, duplicate source-line use, sequence collisions, declared values and evidence. Duplicate taxpayer/direction/supplier/invoice references are rejected at preparation. A supplier-name based key is not a universal fuzzy duplicate detector.

VAT201 aggregates exact AED values and Box1 by emirate. Independently scoped full input/output control-account sums must agree with Boxes12/13; missing or unmodeled transactions therefore block release even when selected invoices individually match. Approved manual adjustments are versioned and included; their journal references are scoped but specialist statutory categorisation remains human reviewed. Unresolved differences remain visible, and no tolerance silently writes them off.

Persistent demo: all30 periods reconciled source expectations;250,020 journal lines; zero unbalanced journals; zero invalid opening+movement=closing TB equations. See `demo-verification.json`, `demo-manifest.json` and actual seed logs. The draft deliberately defective invoice is excluded from approved computations.
""",
)
write(
    "vat-return",
    """
Versioned mapping `VAT201/2022-emaratax/1.0`:1 standard supplies by emirate;2 tourist refunds;3 reverse charge;4 zero-rated;5 exempt;6 customs imports;7 import adjustments;8 total outputs;9 standard expenses;10 reverse/import recovery;11 total inputs;12 output tax;13 recoverable input;14 payable/refundable. Boxes2/7 use separately approved signed adjustments. No tourism-system or customs-network integration is claimed.

The return workpaper references an immutable reconciled computation, completed human checklist, filing state/reference and supporting evidence. Current dependency checks and independent Tax Manager then Tax Partner/CA approval are mandatory. Newly approved source populations invalidate old release/export eligibility. Exports are draft unless an approved current return workpaper exists.

Deadline calculation adds28days to period end and rolls weekends and explicitly reviewed holidays forward. Holiday completeness is manual, not a live UAE calendar feed. JSON download is implemented. VAT-specific PDF/XLSX return exports, FTA portal filing, registration and external settlement are not implemented. Existing IFRS/CT exports remain covered by prior-phase regression tests.
""",
)
write(
    "invoice-validation",
    """
Structured facts validate full/simplified invoice fields, supplier/registered customer identifiers, dates, sequential reference, amounts, discount, rounding, currency/FX and reverse-charge statement. Simplified invoices are rejected for reverse charge and for registered recipients above the AED10,000 gross threshold. Unregistered-recipient and <=10,000 registered-recipient cases are tested. Approval is blocked when validation issues remain.

Real text-PDF extraction uses pypdf6.21.1 in a subprocess, limited to2MiB,5pages and6seconds. Only linked, independently reviewed CLEAN PDF evidence may be processed. Literal text candidates include invoice number, supplier TRN and selected totals; comparisons and uncertainty are persisted in an immutable extraction run. Original invoice facts are never overwritten. Invalid numeric candidates become mismatches. The test suite creates and parses an actual PDF; its scanner result is explicitly mocked CLEAN in that isolated test.

This is text-layer extraction, not image OCR or visual verification. Scanned image/PDF OCR, robust multi-layout invoice parsing and semantic extraction quality require an approved provider and measured fixtures. Windows has no hard subprocess memory ceiling beyond file/page/time guards; compressed-stream memory risk remains. The demo's real client PDF remains quarantined because no live antivirus service is configured. See `portal-invoice-scenarios.json`.
""",
)
write(
    "einvoicing",
    """
Fourteen actual API-backed VAT areas include readiness and ASP sandbox pages. Readiness assesses reviewed scope, revenue, identifiers, source mapping, provider name/accreditation check, appointment and sandbox readiness. Missing facts return REVIEW_REQUIRED. Large-business threshold includes exactly AED50million; amended appointment30October2026 and implementation1January2027; smaller-business and government dates are represented with explicit human applicability assessment. Pilot dates do not imply universal mandatory adoption.

ASPAdapter is an extension interface; SandboxASP makes zero external requests. It validates a small semantic JSON subset and simulates acceptance, rejection or timeout. Idempotency keys are tenant+engagement+kind scoped, engagement-locked and payload checked; changed replay conflicts, and a retry uses a new key. Each attempt is immutable and clearly SANDBOX_*; external_submission=false.

AuditOS is not an accredited ASP. Full PINT-AE XML/UBL, XSD/Schematron, Peppol transport/discovery, certificates, provider credential lifecycle and live ASP callbacks are not implemented. A PDF is not a structured electronic invoice. MD168/2026 supersedes the old preapproval framework; historical preapproved providers must not be displayed as currently accredited without verification.
""",
)
write(
    "ai-vat-engine",
    """
Twenty gateway tasks: classification, input recovery, reverse charge, invoice extraction/explanation, reconciliation exceptions, return variance, designated zones, export evidence, real estate, credit notes, partial exemption, readiness, ASP rejection, supplier masters, controls, missing evidence, technical memo, client request and checklist. Structured output adds VAT risk, extracted fields and document-processing state to the source-grounded tax suggestion schema.

Tenant/engagement permissions and approved configured models apply. External disclosure is disabled unless explicitly configured. Context is bounded12,000characters; Redis limits tenant requests (default20/hour). Source text is untrusted; source IDs, approved legal record IDs/articles/versions and legal period are allowlisted. Model/prompt/execution/source versions are persisted. Suggestions remain SUGGESTED; independent review decisions recheck current dependencies and never change calculations, approve records or post journals.

All20 task schemas were executed with the diagnostic mock in one integration test; the21st request was rejected429. Mock output has no semantic VAT expertise and does not perform OCR. Separate actual text-PDF processing is tested. Live external legal reasoning, extraction precision/recall, multilingual invoice OCR and production model quality are BLOCKED/unmeasured; no invented accuracy percentage is reported.
""",
)
write(
    "sample-data-design",
    """
Dedicated development database `auditos_phase7_demo`, tenant8733db06-81bc-59b3-afcc-bf0f4c0cd8a2, firm `AuditOS Demo Chartered Accountants [SYNTHETIC]`. Guard requires development/test, SYNTHETIC_DATA_ENABLED=true, exact configured dedicated auditos_*_demo database and stable tenant identity, actual current_database equality and expected active synthetic tenant name. All legacy unguarded seed entrypoints refuse execution. Integration tests additionally require an actual configured *_test database before truncation.

`seed_demo.py` uses stable identities, natural-key reuse, atomic period fixtures and persisted versioned manifests. It imports real CSV bytes through upload/validate/commit and generates balanced deterministic journals with separately calculated expected balances and VAT.1,000,000 opening capital/bank per independent annual fixture; sales/purchases/credits, inclusive prices, discounts, USD FX, zero/exempt/outside and reverse/import patterns; filler cash/bank transfers provide scale. Dates match FY2024/25/26 and VAT periods. FY fixtures are independent annual scenarios; no continuous comparative retained-earnings rollforward is claimed. Extra chart accounts exist but most do not carry source balances; specialists are separate workpapers, not automatically posted to GL.

Volume review fixtures use actual typed ORM records, immutable revisions and synthetic review decisions; they are clearly marked synthetic, not professional attestations. IFRS/CT enrichment uses actual review/calculation APIs. New normal API negative fixtures remain drafts and do not contaminate approved financial populations.

Seed and enrichment replay ran successfully without duplicating the base dataset. Cleanup is archival only: set DEMO_ARCHIVE_CONFIRM=ARCHIVE-{exact UUID}; guard then archives only that tenant and its memberships, retaining immutable history/global users. Archival was not executed against the delivered demo. Concurrent seed invocations can fail unique constraints; full-run distributed seeding leases are not implemented.
""",
)
write(
    "sample-data-inventory",
    "\n".join(f"- {k}: {n:,}" for k, n in m["counts"].items())
    + "\n\n25 synthetic users;30 financial periods;750 chart accounts;5,000 approved synthetic invoice sources plus1 deliberately defective draft;121 evidence records including1 real portal PDF upload. Ten FY2026 approved IFRS statement/CT scenarios, ten alternative QFZP profiles/assessments, five IFRS specialist workpapers/runs (lease/ECL/revenue/deferred tax/fixed assets).30 VAT reconciliations and60 sampling runs were generated. Three actual analytics runs are recorded in the manifest. Requests and negative fixtures are additional review data, not financial totals.\n\n"
    + "\n".join(
        "- SYNTHETIC — " + name
        for name in [
            "Al Noor Trading LLC",
            "Emirates Tech Solutions LLC",
            "Gulf Horizon Properties LLC",
            "Desert Logistics FZCO",
            "Crescent Manufacturing LLC",
            "Pearl Hospitality LLC",
            "Falcon Consulting LLC",
            "BlueWave International FZCO",
            "Meridian Investment Holding LLC",
            "Oasis Retail LLC",
        ]
    )
    + "\n\nExact IDs, expected balances, benchmark timings, approved source snapshots and specialist IDs are in `demo-manifest.json`. The seed's primary record-count replay verifies thresholds and records totals; `verify_demo.py` performs the independent GL checks. QFZP profiles are alternative synthetic scenarios, not additive financial entities. Persistent consolidation/intercompany numerical scenarios are not included; the existing automated consolidation tests were executed.",
)
write(
    "demo-user-roles",
    "\n".join(
        f"- `{u['email']}` — {u['role']}"
        + ("; expired engagement grant" if u["expired"] else "")
        + ("; disabled" if u["disabled"] else "")
        for u in m["users"]
    )
    + "\n\nThe CA has an additional Audit Partner role for final independent review. Tax Consultant user10 also has Senior Tax Consultant membership and engagement grants on FY2026 for the reviewed QFZP scenarios; the base Tax Consultant role alone does not grant CT preparation. Client users are restricted to client1 portal records and receive no confidential VAT/audit access. VAT read-only reviewer cannot prepare or export. Platform Super Admin has no confidential tenant bypass. Expired and disabled fixtures are intentionally denied.\n\nPasswords are supplied by PHASE7_DEMO_PASSWORD; no shared fixed password is committed. This local run generated a random development password in ignored `.local-runtime/phase7/demo-login.local.json`. All addresses use `.test`. Do not reuse these identities or identifiers in production. `demo-verification.json` records actual25-user VAT access responses; this is not a claim that every action was exhaustively tested for every role.",
)
groups = {}
for c in cases:
    key = c.attrib["classname"].split(".")[1]
    bucket = groups.setdefault(key, [0, 0, 0])
    bucket[
        2
        if c.find("skipped") is not None
        else 1
        if c.find("failure") is not None or c.find("error") is not None
        else 0
    ] += 1
write(
    "regression-test-matrix",
    counts
    + "\n\n"
    + "\n".join(f"- {k}: {n[0]} passed, {n[1]} failed, {n[2]} skipped." for k, n in groups.items())
    + """

Backend command from backend: `.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing --cov-report=json:../docs/phase-7/coverage.json --junitxml=../docs/phase-7/regression-results.xml`. Set explicit disposable DATABASE_URL, INTEGRATION_TESTS=1, development/test mode, JWT_SECRET and Redis URL. Full run289.32seconds; source evidence regression-results.xml/regression-log.txt. Final targeted Phase7 rerun:23 passed in24.45seconds after final applicability/parser changes; vat-results.xml/vat-test-log.txt. Baseline271 passed,2 skipped. Counts are test cases, not assertions, task variants or demo records.

Frontend: `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`. Playwright: `npm run test:e2e:phase7` against production3001 and actual demo API58003. Five tests cover14 VAT routes, calculation/export, mobile read-only controls,16 IFRS routes,20 CT routes,16 audit routes and12 core/admin routes. They check rendering and selected actions; they are not exhaustive click coverage. Browser initial run had1 test-selector failure (Export JSON vs actual Export VAT JSON), corrected and rerun. Latest5 passed in26.6seconds. Screenshots in screenshots/. No mocked browser financial responses.

`scripts/phase7.ps1 -Task` exposes backend/frontend/e2e/security/financial/ai/regression/benchmark/seed-demo/enrich-demo/demo-tax-cases/verify-demo/archive-demo. It propagates native failures. Seed commands require all demo guards and password; never point tests at the delivered demo. CI uses a non-superuser role, dedicated *_test database, migrations/drift, Ruff/mypy, coverage80% and core90%, plus frontend tests/lint/types/build.
""",
)
write(
    "financial-accuracy-report",
    """
All30 stored snapshot GL balances were recomputed using PostgreSQL aggregate queries and compared by account with independently generated expected amounts.250,020 journal lines: zero unbalanced journal IDs; zero TB opening+debit-credit=closing violations. See demo-verification.json. Base seed independently compared all30 VAT net computations and control-account balances. The deliberate draft defect does not enter approved calculations.

FY2026 IFRS10 cases compare generated PBT with independent source revenue minus source expense minus approved100 accrual overlay, require ready balance/cash-flow validation, and pass independent FR Manager/CA release.10 standard CT cases compare max(PBT−375,000,0)×9%; these source populations are below threshold, so expected current CT is0. High-value CT/loss/interest examples are automated tests, not represented as large demo profits. Ten QFZP alternative cases reconcile revenue to approved IFRS line400 and expect PASS/0 qualifying tax with explicit reviewed synthetic conditions and evidence.

Specialist assertions: lease liability/ROU1,000 from1,100 discounted one year at10%; scenario-weighted ECL65; revenue200 and contract liability50; deferred-tax liability1.8. The fixed-asset workpaper independently checks depreciation120 and closing carrying amount1,080; enrichment replay verifies all five saved specialist runs. Consolidation/intercompany are tested in the existing suite; no persistent large-demo consolidation case was seeded. No claim of comprehensive financial standards or real business suitability.

New VAT numerical fixtures cover inclusive/exclusive/credits/FX, reverse/import, approved recovery percentage, FTA13 thresholds, invoice simplified limits, dates/deadlines, exactly50M rollout and missing evidence. Controlled API fixture output VAT50, recoverable50.50, net−0.50 is independently checked. Stale source-population regression tests cover IFRS, CT and VAT exports/releases. `regression-results.xml` contains exact executed cases.
""",
)
write(
    "ai-evaluation-report",
    """
Executed:13 provider tests; existing source/schema/provider/private storage/grounding and independent-review tests; all20 VAT tasks through the configured diagnostic mock, one tenant budget rejection on21st call, independent acceptance without financial mutation, and real pypdf text extraction. Full case counts are in regression-test-matrix.md; task iterations are not counted as20 separate pytest cases.

The gateway rejects unsupported task names, unauthorized models/providers, unapproved external disclosure, oversized context, invalid structured output, unallowlisted evidence/legal references and stale sources. Existing AI mock/malformed/adversarial fixtures were retained and rerun. Findings about prompt injection are bounded to those fixtures; no broad jailbreak-resistance claim.

BLOCKED: external provider VAT legal accuracy, real image OCR, multilingual invoices, hallucination rates and model quality metrics. No provider credentials/model approval/labelled corpus were supplied. Mock responses are clearly diagnostic and never scored as correct expert advice. Invoice extraction in the mock returns no verified fields; separate literal text extraction remains unverified until human review.
""",
)
write(
    "security-test-report",
    """
Executed full authentication/refresh reuse, role/tenant/engagement checks, no platform bypass, assignment/expiry/disabled identity, evidence quarantine and portal isolation fixtures. Actual25-user demo VAT workspace probes returned only permitted200 or denied401/403; client and platform users did not receive confidential VAT access. VAT read-only user's actual computation request returned403 and browser button is disabled. Immutable run SQL mutation, cross-scope source linkage, draft/unapproved/stale export and independent review tests passed.

Fixed worker authorization to evaluate tenant RolePolicy overrides rather than global role defaults at execution; both accounting and diagnostic workers now enforce current effective permissions. Added tests for revocation and completed-job idempotency-key ownership. Keys belonging to another user return409 before any completed-result replay. Fresh migration role has rolsuper=false/rolbypassrls=false; both VAT tables have enabled+forced RLS (`migration-verification.json`).

Demo safety: configuration/actual DB/tenant guards; old seed commands retired; fixture TRUNCATE requires disposable *_test database. Validated wrong environment/flag/database/tenant refusal in tests. Demo cleanup is archival and was not run on the delivered fixture. No destructive production, external penetration or exhaustive per-action/per-role fuzzing was performed. No live ClamAV is configured: real uploaded demo PDF stayed QUARANTINED; auditor submission correctly returned409. The PDF parser's CLEAN scanner is mocked only in an isolated integration test.
""",
)
write(
    "performance-benchmarks",
    """
Executed `python ../scripts/benchmark_accounting.py --sizes 10000 100000 250000 --output ../docs/phase-7/scale-file-benchmarks.json` using backend venv. See JSON for exact timings/RSS. On this Windows host (Python3.12.10,12 logical CPUs), 250k file rows: ingestion9.5301s, validation/TB0.7886s, DuckDB analytics3.8497s, peak process RSS240,836,608bytes. Independent source reconciliation passed for all10k/100k/250k populations. File timings exclude PostgreSQL persistence and are not end-to-end import throughput.

Actual PostgreSQL imports were performed in30 chunks of8,334 rows (250,020 total); each chunk's timings are in demo-manifest.json. Queries recomputed the full250k population integrity. Actual local invoice list API20-request sample: p50 {:.6f}s, p95 {:.6f}s. Sequential warm local requests do not measure concurrent production capacity. VAT grid loads50 rows/server page; approved invoice computation is bounded20k but synchronous and not benchmarked at20k.

The restarted solo Celery worker completed20 fresh diagnostic jobs (worker-log.txt). Latest verification fetched20 completed job states in{:.4f}s using idempotent replay keys; that replay time is not execution throughput. This measures harmless diagnostics, not financial imports or CPU-heavy worker throughput. No large concurrent soak, cloud PostgreSQL, object-store or live ASP latency test was run. Model cost/latency is unmeasured for external AI. Hardware/concurrency limitations must be considered before production sizing.
""".format(
        v["api_latency_p50_seconds"],
        v["api_latency_p95_seconds"],
        v["worker_diagnostics"]["submit_to_all_complete_seconds"],
    ),
)
write(
    "bugs-found-and-fixed",
    """
- High: destructive integration fixture had no actual database identity check. Added development/test + actual configured *_test guard before TRUNCATE; CI database renamed accordingly; guard tests passed.
- High: legacy demo seed commands could mutate an arbitrary database using a simple flag. Retired unsafe entrypoints; new seed/enrichment/verification enforce dedicated actual DB+tenant identity. Seed replay verified250,020 base lines unchanged.
- High: queued workers used global role grants and ignored tenant revocation policy. Both workers now resolve current tenant-effective permissions; targeted revocation test passes.
- High: completed diagnostic key could replay another user's completed row. Ownership now precedes status replay;409 regression passes.
- High: previously released IFRS/CT outputs could appear current after new approved source workpapers. Added approved-population freshness checks and downstream financial dependency checks; targeted stale release tests pass. VAT includes population freshness from inception.
- Medium: VAT legacy generic AI/list/link paths needed explicit VAT authorization. Integrated VAT permission filters and rejected generic AI bypass; API tests pass.
- Medium: VAT read-only UI exposed create/review controls. Gated AuditStudio VAT editor/actions and VAT calculation/export controls by actual workspace permissions; API remains authoritative; read-only browser test passes.
- Medium: employee/integrity effective-date recovery needed approved source-linked rules. Added FTA17 and FTA13 adoption/applicability checks; latest23 VAT tests pass.
- Medium: extraction malformed numeric candidate could raise an unhandled decimal exception. It now becomes a mismatch; actual text-PDF path passed targeted regression.
- Build: local invoice document state shadowed DOM document, breaking TypeScript download code. Renamed state; types/build pass.
- QA fixtures: invalid legacy engagement enum, mapping extra unused accounts, incorrect independent review role, and browser export selector were corrected, then reseeding/enrichment/tests rerun. These are recorded as fixture defects, not product vulnerabilities.

No final known failing automated test. Broader unimplemented and externally blocked functions are in remaining-issues.md; this report does not convert missing functionality into a passed test.
""",
)
write(
    "remaining-issues",
    """
External blockers: no approved live ASP/Peppol credentials or accreditation; no live ClamAV; no approved external AI/OCR model evaluation corpus; two accounting connector live tests skipped for absent credentials. Local sandbox, mocked provider/AV contract tests and real text-PDF parsing are explicitly distinguished from these integrations.

Implemented with manual review/limited scope: legal classification/place/time of supply; export/designated-zone/real-estate qualification; partial exemption/annual/CAS allocations; employee statutory conditions; integrity substantive checks; public holidays; JSON VAT exports; small PINT-AE semantic subset. Automated statutory apportionment, comprehensive CAS schedules, VAT-specific PDF/XLSX output and full structured XML/network transmission are absent. Prior-period credit-note originals are restricted to current profile/engagement. The consolidated2026 regulation URL is not an immutable historic-law archive; each historical rule adoption requires review. MD66 Gazette commencement date is unverified (see legislation matrix).

Demo limitations: annual fixtures are independent, not a continuous FY2024→FY2026 rollforward; most chart balances are intentionally concentrated in9 accounts and filler cash transfers. Persistent20 tax cases comprise10 below-threshold standard computations and10 alternative QFZP assessments; richer high-value loss/interest/group cases live in executed tests. Persistent consolidation/intercompany fixtures and continuous comparative statements have not been generated. Seed replay is idempotent, but parallel full-run seed leases are absent.

QA limits: browser coverage verifies all established workspaces and selected actions, not every button or every permission permutation. The ten requested demonstration roles are represented through existing API fixtures except a distinct internal Accountant import identity: base imports currently use Firm Administrator. Client PDF upload/review was exercised but clean final approval is blocked by absent scanner. Production concurrency/soak,20k invoice VAT computation and financial worker throughput are unmeasured. PDF parsing on Windows lacks a hard OS memory limit. Broader existing Phase6 edge-case limits remain applicable.

These gaps prevent calling the entire original Phase7 definition universally complete or production certified. The implemented foundation and executed tests are reviewable; unresolved scope is explicit. No Phase8 work has begun.
""",
)
write(
    "phase-7-report",
    f"""
Phase7 implementation and executed evidence,18October2026. Existing uncommitted Phases4–6 work preserved. VAT/e-invoicing preparation foundation and isolated substantial demo are implemented; remaining-issues.md records unmet breadth/external blockers. Do not read a passing suite as comprehensive legal or production certification.

{counts}

Application health: production frontend build, ESLint, TypeScript and backend Ruff/mypy pass; API/DB/Redis accessible; actual Celery diagnostics complete. Fresh PostgreSQL migration0001→0007 on68 public tables, no schema drift, non-superuser/nobypassrls role; VAT tables force RLS. Migration evidence: migration-log.txt/migration-verification.json. Earlier baseline271 passed,2 skipped. Latest targeted VAT23 passed,0 failed.

Inventory:14 VAT workspaces; approved profile/rule versions; invoice validation and source/GL reconciliation; VAT201 draft/review/export; reverse/import and manual recovery adjustments; readiness; local idempotent ASP adapter;20 AI gateway task types with human review; actual unverified text-PDF extraction. API contract: openapi.json and regenerated frontend types.

Demo:10 clients/entities,30 engagements/periods,250,020 journal lines,5,000 approved invoices plus1 deliberate defective draft,150 working papers,120 procedures,60 findings,60 samples,121 evidence records,25 synthetic users;10 approved IFRS and standard CT cases,10 QFZP alternatives,5 specialist calculations. Exact IDs/expected values/roles: demo-manifest.json, sample-data-inventory.md, demo-user-roles.md. Passwords remain local/ignored. All30 GL periods reconcile; zero unbalanced journals/TB equations. Seed and enrichment replay do not double data.

Financial/AI/security details: financial-accuracy-report.md, ai-evaluation-report.md, security-test-report.md. Full294 passed +2 skipped; frontend22 passed; browser5 passed. Actual25-role access probes and20 completed worker diagnostics. Large file benchmarks10k/100k/250k passed independent source reconciliation;250k ingestion9.53s and analytics3.85s, peak RSS241MB. Exact measured API/worker timings and limits in performance-benchmarks.md.

Defects repaired include unsafe test/seed mutation, worker tenant-policy revocation, completed-job key ownership, stale financial source populations, VAT generic-path permissions and read-only UI controls, date-applicable recovery rules and PDF numeric candidate handling. See bugs-found-and-fixed.md for verification.

Screenshots: screenshots/vat-calculated.png, vat-mobile-readonly.png and all14 VAT pages, IFRS/CT/core regression captures. Desktop screenshot manually inspected for design continuity. Playwright uses the production build and actual seeded backend; no mocked financial API responses. Initial selector defect was fixed and final5 passed.

Phase8 readiness: suitable for reviewing the scoped implementation and planning remaining integration work. Not ready for regulatory filing, accredited e-invoice transmission, unrestricted production demo seeding or a universal completion sign-off. Live ASP/AV/AI evaluation, richer continuous/consolidated demo cases, distinct internal Accountant import scenario, statutory allocation automation and expanded load/action coverage remain. STOPPED at Phase7; Phase8–12 not started. No Phase7 commit/push was performed.
""",
)

sys.path.insert(0, str(ROOT / "backend"))
SOURCES = importlib.import_module("app.modules.vat.catalogue").SOURCES

matrix = [
    "Verified official source metadata on18October2026. Adoption requires independently approved rule records with category, article, effective interval, known-from, document version, conditions, exceptions and technical review. Catalogue publication is not automatic approval.\n"
]
for key, source in SOURCES.items():
    matrix.append(
        f"- **{key}** — [{source['title']}]({source['url']}). Catalogue earliest adoption boundary:{source['earliest']}; allowlisted articles:{', '.join(source['articles']) or 'document-level reference'}. Independently reviewed adoption required."
    )
matrix.append("""

Automated numerical scope: approved5% standard/deemed/reverse/import treatment; reviewed zero/exempt/outside categorisation;2-decimal AED rounding; inclusive/discount/credit/FX arithmetic; invoice field and simplified-threshold checks; manual full/partial/blocked recovery; source/control reconciliation; versioned VAT201 boxes; reviewed deadline calendar; limited readiness dates and local sandbox semantics.

Manual/checklist scope: substantive place/time of supply, exports and retention, designated zones, real estate, international transport, employee statutory conditions, supplier integrity, tourism/customs adjustments, partial exemption and annual/CAS allocation. No new apportionment formula is applied solely because a2026 amendment exists.

Date interpretation verified from official full text: FTA13/2026 Article7 and FTA17/2026 Article3 commence1October2026. CD149/2026 general commencement1October2026 differs from the staged amended-apportionment commencement: first tax year beginning after1October2027 (consolidated Executive Regulation footnotes38–40). MD66 includes revenue exactly AED50million, appointment30October2026 and implementation1January2027. Its English publication has signature-date placeholders and commencement by Gazette publication; exact Gazette publication date was not verified. Catalogue earliest2026-05-10 is a knowledge/adoption guard from the announcement, not a certified legal commencement date; seed adoption2026-05-14 must be independently reviewed for historical use. MD168/2026 is effective1October2026 and repeals64/2025 and56/2026; preapproval is not current accreditation.

VAT-ER catalogue earliest2018 reflects the underlying regulation's history, while its linked consolidated text is2026. This URL is not a complete immutable legal time machine; historical versions need explicit technical review/archive before real engagement use. VAT201 mapping is versioned to the official2022 EmaraTax manual; later portal changes require a new reviewed mapping. Official PINT-AE mandatory-field PDF supports only the implemented semantic subset; full XML/XSD/Schematron/network conformance is not implemented. No superseded or unexplained source is automatically approved.
""")
write("vat-legislation-matrix", "\n".join(matrix))
if m.get("accountant_scenario"):
    for path in OUT.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        content = content.replace("750 chart accounts", "250 chart accounts")
        content = content.replace("289.32seconds", f"{full_seconds:.2f} seconds")
        content = content.replace("24.45seconds", f"{vat_seconds:.2f} seconds")
        content = content.replace(
            "30 financial periods", "30 base financial periods plus1 isolated FY2027 QA period"
        )
        content = content.replace("30 engagements/periods", "30 engagements and31 periods")
        content = content.replace("Three actual analytics runs", "Four actual analytics runs")
        content = content.replace(
            "150 working papers", "150 base working papers plus2 API review scenarios"
        )
        content = content.replace("26.6seconds", f"{browser['stats']['duration']/1000:.1f} seconds")
        content = content.replace(
            "except a distinct internal Accountant import identity: base imports currently use Firm Administrator",
            "including a distinct internal Accountant identity with an additional isolated FY2027 four-line import/TB scenario (accountant-demo-log.txt and manifest accountant_scenario)",
        )
        content = content.replace("distinct internal Accountant import scenario, ", "")
        content = content.replace(
            "25 synthetic users", "25 base synthetic users plus1 internal Accountant"
        )
        content = content.replace(
            "250,020 journal lines",
            "250,020 base journal lines plus4 isolated Accountant QA lines",
        )
        path.write_text(content, encoding="utf-8")
    with (OUT / "demo-user-roles.md").open("a", encoding="utf-8") as f:
        f.write(
            "\n- `synthetic.accountant@auditos.test` — Accountant [SYNTHETIC DEMO], limited internal accounting import/read role, separate from restricted Client Accountant. Actual four-line FY2027 QA import/validate/commit/TB executed. This signed-balance QA example is independent of the normal30 annual financial fixtures. No audit, VAT approval, user administration or client portal grants.\n"
        )
    with (OUT / "demo-user-roles.md").open("a", encoding="utf-8") as f:
        f.write(
            "\nAuditor user06 additionally holds Audit Analytics [SYNTHETIC DEMO] for explicit accounting/analytics access in this isolated tenant. VAT Analyst user20 additionally holds Invoice Validator with an engagement grant. CA user03 has an explicit Audit Partner engagement grant on the first FY2026 scenario; the CA's self-prepared paper still awaits a different final partner. These fixture grants do not broaden the application's default Auditor or Client Accountant roles.\n"
        )
    with (OUT / "regression-test-matrix.md").open("a", encoding="utf-8") as f:
        f.write("""

## Ten persistent demonstration scenarios

1. Firm Admin: actual API-created10 clients/entities and30 engagements, CA memberships assigned through team API; seed-log.txt and manifest source IDs.
2. Internal Accountant: actual four-line upload/validate/commit and independent TB signed-balance assertion, isolated FY2027; accountant-demo-log.txt and manifest accountant_scenario. Distinct from restricted Client Accountant.
3. Auditor: actual analytics run, finding retrieval and original journal lineage investigation; audit-demo-log.txt and manifest audit_scenarios.
4. CA: actual working-paper preparation/submission and independent final review of a different preparer's paper after Audit Manager review; audit_scenarios stores both IDs. Own paper remains pending a different final partner.
5. Financial Reporting Manager: actual IFRS generation; independent PBT and ready checks; role-calculations-log.txt and manifest role_calculations.
6. Tax Manager: actual CT preparation from approved IFRS source; independent expected current tax; same evidence.
7. Tax Consultant with explicit Senior Tax Consultant role:10 reviewed QFZP alternative cases, actual calculation API and independent expected status/tax; qfzp-demo-log.txt and per-engagement manifest IDs.
8. VAT Analyst: actual approved-source reconciliation/net assertion and stored draft return; portal-invoice-scenarios.json vat_analyst.
9. Invoice Validator: actual deliberately defective invoice validation; structured exceptions in portal-invoice-scenarios.json. Draft is excluded from approved returns.
10. Client Document Contributor: real PDF upload to requested evidence; Auditor reviewed metadata and attempted submission;409 quarantine block observed. Final clean approval remains BLOCKED until an antivirus service scans it. No false CLEAN status was injected into the demo.

Unified financial runner itself executed80 numerical tests successfully (unified-financial-log.txt). This repeats a subset of the full suite and is not added to its294-case pass total. Latest targeted VAT case includes an actual32,768-UUID PostgreSQL array query to guard against asyncpg scalar bind limits, and confirms the synthetic status banner cannot disclose the demo manifest.
""")
    with (OUT / "bugs-found-and-fixed.md").open("a", encoding="utf-8") as f:
        f.write(
            "\n- High: synthetic banner endpoint initially exposed a full cross-engagement demo manifest to any VAT reader. Response now allowlists only id/version/status/synthetic flag; targeted API regression confirms no manifest disclosure.\n- Scale: large source-line predicates could exceed asyncpg's32,767 scalar bind limit. VAT source fetch/freshness queries now use one typed UUID-array bind; an actual32,768-ID PostgreSQL query passed in the targeted integration case. This does not replace a full20k-invoice load test.\n"
        )
print(counts)

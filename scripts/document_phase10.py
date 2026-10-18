"""Write implementation-specific handover documentation from recorded evidence."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase-10"


def write(name, title, text):
    (OUT / name).write_text("# " + title + "\n\n" + text.strip() + "\n", encoding="utf-8")


def main():
    demo = json.loads((OUT / "demo-verification.json").read_text(encoding="utf-8"))
    performance = json.loads((OUT / "performance.json").read_text(encoding="utf-8"))
    backend = (OUT / "regression-backend.txt").read_text(encoding="utf-8")
    tests = re.search(r"(\d+) passed, (\d+) skipped in ([^\n]+)", backend)
    result = tests.group(0) if tests else "Final regression running; inspect regression-backend.txt"
    write(
        "pre-implementation-audit.md",
        "Phase 10 pre-implementation audit",
        """
The baseline was run before GRC implementation: 353 backend tests passed and two integration tests were skipped; 22 frontend tests passed. Raw evidence is in baseline-backend.txt and baseline-frontend.txt. The existing checkout contained uncommitted Phases 4–9 in addition to committed Phases 1–3; those changes were preserved. This delivery was neither committed nor pushed.

FastAPI, non-superuser PostgreSQL with forced RLS, Redis/Celery, Next.js, the private source object store, typed audit records, optimistic revisions, review separation, evidence scanning, the Phase 2 Decimal/DuckDB engine and the Phase 9 TensorFlow.js registry were available. The synthetic database contained 250,024 immutable journal lines. Existing statutory, IFRS, tax, VAT, TP and DMTT modules were reused without replacing their financial facts.

The implementation reuses typed AuditRecord workpapers instead of duplicating identity, evidence, reviews and 45 parallel registers. Three new tenant-scoped tables hold immutable execution snapshots, immutable deduplicated alerts and mutable versioned schedules. Public standards metadata was checked against primary publisher pages. No proprietary standard text was copied. Phase 11 was excluded.
""",
    )
    documents = {
        "architecture.md": (
            "Architecture",
            """GRC workpapers are strict Pydantic bodies registered under 24 grc-* kinds in the existing audit execution service. They retain immutable revisions, optimistic versions, preparer history and independent review. New tables are grc_execution_snapshots, grc_monitor_alerts and grc_monitor_schedules. Migration 0010 contains frozen PostgreSQL DDL, composite tenant foreign keys, FORCE RLS policies, immutable update/delete triggers on snapshots and alerts, and role permission additions.

GRCRun hashes canonical inputs, results and dependency versions. Approved assessment calculations freeze the methodology used; later source changes flag stale assessments instead of changing historical scores. Monitoring jobs use approved rule versions, current identity/grant checks, existing Decimal analytics and optional actual TensorFlow.js inference. Alerts retain separate deterministic, ML and human-review fields. Schedules and import triggers use a transactional job outbox and dispatch only after commit. Board publication has a distinct redacted read model and audience checks.

The shared typed editor supports nested arrays, maps and source references. Distinct planning, heatmap, graph, KRI, investigation, deadline, remediation and governance interactions sit above it. Some source references still require manual selection/paste; this is a limited enterprise workflow, not a claim of complete product polish.""",
        ),
        "standards-registry.md": (
            "Framework and standards registry",
            """The registry contains public metadata, version, publisher, authority, source URL and effective date. GIAS 2024 applies from 9 January 2025; the cybersecurity topical requirement applies from 5 February 2026 and the third-party topical requirement from 15 September 2026. COSO framework publication years are not treated as universal legal commencement dates. ISO 31000 is guidance; ISO 27001 mapping requires authorized licensed material. A framework record includes applicability, technical review, validity and supersession.

Primary sources checked on 18 October 2026: [IIA Standards](https://www.theiia.org/en/standards/2024-standards/), [IIA topical requirements](https://www.theiia.org/en/standards/2024-standards/topical-requirements/), [COSO internal control](https://www.coso.org/guidance-on-ic), [COSO ERM](https://www.coso.org/guidance-erm), [ISO 31000](https://www.iso.org/standard/65694.html), [ISO 27001](https://www.iso.org/standard/27001).

Original descriptions and user-authorized mappings are supported. No complete licensed GIAS/COSO/ISO requirement corpus or automatic conformance certification is included. New or revised requirements require professional verification and a reviewed version.""",
        ),
        "audit-universe.md": (
            "Audit universe",
            """Universe workpapers identify entity, owner, unit type, objective, exposure, inherent ordinal rating, maturity, previous audit, frequency, assigned auditor and parent. Parent and assigned-auditor references are checked within the engagement. Ten fictional processes cover procure-to-pay, order-to-cash, payroll, treasury, close, tax, cyber, onboarding, inventory and continuity.

The universe page provides the searchable register and applicable framework editor. Revision and approval are real API operations. A fully navigable hierarchical organization browser and automated enterprise discovery are not included; hierarchy remains a governed reference.""",
        ),
        "annual-audit-planning.md": (
            "Risk-based annual audit planning",
            """An approved scoring model supplies exact Decimal criterion weights summing to one, rating scale and appetite. Plans contain year, auditable area, auditor, dates, budget, actual hours, criterion values, documented deferral and committee evidence. Approval rejects over-capacity plans, incomplete criteria and out-of-year dates. Deferred items retain rationale and do not consume scheduled capacity. Priority ranking is deterministic, with stable tie-breaking.

The synthetic plan has ten engagements and 800 budgeted hours against 1,600 available hours. The UI exposes commitments and structured plan/scoring editors. Internal audit scope must use a non-deferred universe item in an approved plan. Resource optimization and forecasting are not claimed.""",
        ),
        "erm-risk-engine.md": (
            "ERM and risk calculations",
            """Risks capture objective, cause, consequence, owner, category, treatment and review date. Assessments use an approved 3×3 or 5×5 product or explicit lookup matrix, separate inherent/residual coordinates, velocity, rationale and approved evidence. These are qualitative ordinal ratings, never probabilities. KRI observations require distinct dates and reviewed evidence.

Approved assessment calculations retain source record versions and exact methodology results. Reusing a frozen calculation after a dependency changes is rejected; the assessment must be reopened and independently reviewed. Heatmaps use frozen scores, expose stale-source status and separate scoring methodologies. Approval and snapshot immutability are covered by real database tests. The dashboard uses the latest approved dated assessment per risk; no automatic residual-effectiveness inference is performed.""",
        ),
        "risk-control-matrix.md": (
            "Risk-control matrix",
            """Reviewed links join actual risk and control workpapers within one engagement. The RCM endpoint provides bounded joined rows and source review status; the synthetic dataset has 300 mappings between 100 risks and 200 controls. Deficiencies require a matching approved risk-control mapping.

The UI offers a dense grid with loaded-page filtering and saved views plus a ReactFlow relationship graph. Graph focus limits visible relationships to a risk or the first 30 mappings for readability. Graph layout changes do not alter professional mappings. Specialized cross-entity process mining is outside this implementation.""",
        ),
        "control-testing.md": (
            "Control design and effectiveness testing",
            """Control definitions retain type, frequency, preventive/detective approach, manual/automated/hybrid operation, key-control flag, procedure, framework, accounts and policy. Tests distinguish design, implementation, operating effectiveness and retesting. An approved document alone is not treated as proof of operating effectiveness.

Operating and retest approval requires a frozen same-entity/period population and sample, one outcome per selected item, approved evidence per item and a human conclusion. Duplicate or non-sampled items are rejected. Exceptions cannot be silently concluded effective. Existing random, systematic, MUS, high-value and judgmental sampling is reused; GRC tests are bounded to 1,000 items per sample. The verified chain uses a selected original journal line and an independently approved retest. Synthetic financial-note references are software fixtures only, not actual control evidence.""",
        ),
        "sod-analysis.md": (
            "Segregation of duties",
            """SoD evaluates incompatible ERP permission pairs for the same principal and same entity/system scope, using access validity windows at a stated assessment date. Application roles are not inferred as ERP permissions. Expired permissions and different scopes do not create conflicts. Compensating-control verification remains a separate professional assessment.

Manual typed populations and bounded CSV import are available. CSV columns are principal, permission, scope, valid_from and optional valid_to; maximum 4 MiB and 10,000 rows. Imported content must match the latest clean, independently approved evidence version by SHA-256. Duplicate assignments, invalid dates and unknown columns are rejected. There is no live ERP directory connector or automatic access revocation.""",
        ),
        "continuous-monitoring.md": (
            "Continuous monitoring",
            """Thirty governed rule definitions state their required source adapter. Available GL rules reuse the actual Phase 2 engine. Workpaper rules inspect approved controls/tests, unresolved deficiencies, reviewed deadlines and reconciliation obligations. Missing vendor, inventory, payment, e-invoice or access inputs return NOT_TESTABLE instead of fabricated results. Duplicate-payment candidates are generic journal-signature candidates; they do not establish confirmed duplicate bank payments.

Executions freeze rule version, source snapshot, parameters, results and dependencies. Alerts deduplicate by rule key/version and stable economic signature; insertion statistics live in separate immutable receipts. Runs bound populations to one million lines and alert insertion to 10,000 candidates per rule; larger scopes require partitioning. The analytics engine retains a 1 GB memory limit and partitions whole-journal ordered aggregates on large populations.

The Celery scheduler checks daily/weekly/monthly/quarterly due dates with timezone-aware timestamps, locks due schedules, advances missed intervals once and creates pending jobs before dispatch. Original membership, grants and rule versions are rechecked by the worker. Import activation creates a recoverable pending job in the same transaction for approved opt-in rules; callers cannot inject a snapshot override through the public execution schema. Use a worker consuming grc and a separately supervised Celery Beat process. Local verification ran an actual worker and scheduler tick; a continuously supervised production Beat deployment was not installed.""",
        ),
        "tensorflowjs-integration.md": (
            "TensorFlow.js monitoring integration",
            """Optional monitoring inference uses the current deployed same-engagement Phase 9 model family and actual Node/TensorFlow.js CPU inference. It retains model/deployment IDs, feature schema, calibration, input snapshot, raw score, drift, experimental status and reviewer state. Financial arithmetic remains Decimal; floating point is confined to ML features/scores. Classification suggestions are not fraud findings.

The bounded scored slice is registered as a private immutable dataset with unknown labels and test-only splits, then linked to a standard ML inference event. Existing evidence-backed feedback and independent curation can consume that event; original test split assignments are preserved, with no automatic retraining or deployment. Models remain experimental and validated only on the Phase 9 controlled synthetic task. Real-world fraud detection accuracy and calibrated probabilities are not claimed.""",
        ),
        "alert-investigation.md": (
            "Alert investigation",
            """The investigation grid pages persisted alerts; the drawer separates deterministic rule facts, TensorFlow.js predictions and original source journals/workpapers. Reviewers can assign an investigator, record a proposed false-positive/exception/insufficient-evidence decision and attach approved evidence. Human decisions are independently reviewed workpapers linked to the immutable alert; no score is overwritten.

The verified scenario opens the original source, records an investigation, links the RCM control, performs a frozen sampled test, raises a deficiency, records management response and closes only after approved retesting. Feedback remains distinct from an approved professional finding. Bulk investigation disposition, payment-system provenance adapters and a complete source-reference picker remain limited.""",
        ),
        "deficiencies.md": (
            "Control deficiencies and root cause",
            """A deficiency requires an approved control test for the same control, an approved risk-control mapping, evidence, affected period, owner, root-cause method, proposed cause, consequence, severity and severity methodology. An alert may be linked but is not sufficient by itself to create an approved conclusion.

The synthetic dataset includes 50 base design deficiencies plus the independently reviewed proof scenario. Five-whys, fishbone and process/human/system/policy/monitoring classifications are available as documented human analyses. AI may suggest hypotheses only. No automatic causal inference or system-generated assurance rating is claimed.""",
        ),
        "remediation.md": (
            "Remediation and verified closure",
            """Management actions retain an accountable owner, corrective action, response, due date and management status. Reported completion does not close a finding. An independently reviewed closure must reference an approved effective retest of the original deficient control and original test, supported by evidence and a management completion response.

The tracker exposes management lanes, overdue actions and separate closure workpapers. Approval generates an internal owner assignment notification. No email or external messages are sent. A full automated reminder/escalation service is not implemented. Internal-audit lifecycle closure conservatively checks all approved deficiencies/actions in the parent engagement; finer sub-engagement closure scoping remains limited.""",
        ),
        "compliance-obligations.md": (
            "Compliance obligations",
            """Obligations identify legal entity, source URL, jurisdiction, source module, effective date, deadline, required evidence, responsible owner and human assessment. Supported compliance requires reviewed evidence; a calendar completion is not a legal-compliance conclusion. Optional statutory record links retain existing tax/VAT/TP/DMTT/IFRS module permission checks.

The UI provides a dated obligation register and editable evidence requirements. The demo contains original fictional governance obligations, not a fabricated UAE legal catalogue. Live regulatory monitoring, automatic legal interpretation and government filing integration are not implemented.""",
        ),
        "policies.md": (
            "Policies and procedures",
            """Policies retain owner, increasing version, effective/review dates, text, supersession and obligation links. Policy ownership is checked at approval and the owner cannot approve their own prepared or edited revision. Acknowledgments are immutable events linked to the exact approved policy version and acknowledging user, after the effective date.

The library exposes reviewed policy text and an acknowledgment action. Approved policy workpapers remain immutable until authorized reopening. Enterprise distribution campaigns, acknowledgment reminders and full document comparison are not included.""",
        ),
        "third-party-risk.md": (
            "Third-party risk",
            """Assessments capture fictional vendor/service, source key, criticality, geography, dependency, security assessment, renewal, SLA exceptions and approved evidence. The dedicated view groups vendors by criticality and exposes renewal dates. Risk remains a documented professional assessment rather than an invented external credit/security score.

Ten fictional vendor fixtures were approved through the existing review workflow. Live vendor intelligence, contractual document extraction and external cybersecurity feeds are not connected; specialized monitor rules requiring these sources remain NOT_TESTABLE.""",
        ),
        "board-reporting.md": (
            "Internal audit and board reporting",
            """Reports have governed narrative chapters, scope, methodology, assessment, recommendations, management response, appendices and approved deficiencies. An independently approved board package explicitly chooses audit committee, board or both audiences and a validity date. Publication freezes whitelisted report/deficiency narratives in a separate immutable snapshot; board users receive no generic working-paper access.

Every read and export checks current engagement permission, intended audience, expiry and dependency version/status. Reopening or changing a published source invalidates access until republication. PDF and DOCX exports reproduce the published package with its hash and conspicuous synthetic marking. Rendered PDFs and Word documents were visually inspected; the Word title is plain black without inherited decorative borders. The designer is a typed chapter editor, not a full WYSIWYG publication suite. Board professional commentary and unrelated evidence are not automatically included.""",
        ),
        "qaip.md": (
            "Internal audit quality assurance",
            """QAIP records identify an approved effective framework, owner, assessment type/date, conformance assessment, findings, improvement actions, training needs and evidence. Ongoing, periodic internal, engagement quality and external-assessment request types remain separate. A future-effective framework is rejected for an earlier assessment date.

External certification claims are explicitly false in the schema. The demo is an original synthetic internal self-assessment; it does not establish full GIAS conformance or an external quality certification. External assessor workflows and exhaustive licensed requirement checklists remain outside the implemented scope.""",
        ),
        "ai-grc-copilot.md": (
            "AI GRC Copilot",
            """Thirty task types cover universe suggestions, plan coverage, scope, risks, control mapping/design/testing, walkthroughs, SoD, exceptions, root causes, remediation, period/KRI comparison, ML explanations, alerts, management questions, missing evidence, policy/vendor review, reports, overdue actions, committee briefings, quality improvements and technical memoranda.

Retrieval accepts only approved same-engagement records authorized for the caller, with bounded source count and payload size. Sensitive owner/team fields are omitted. The existing approved-model gateway enforces external-disclosure configuration and per-user hourly limits; strict Pydantic output requires citations confined to supplied records, mandatory human review and no opinion/evidence-sufficiency conclusion. Suggestions are immutable and cannot close findings, sign reports, retrain models or change calculations.

All 30 diagnostic task paths were exercised in the real API test. The configured local provider explicitly returns MOCK DIAGNOSTIC output; no live semantic GRC reasoning or fabricated legal research is claimed. An approved external provider and separate evaluation are needed before production generative use.""",
        ),
        "roles-and-permissions.md": (
            "Roles and permissions",
            """New roles include Chief Audit Executive, Head of Internal Audit, Internal Audit Manager, Senior/Internal Auditor, Risk Manager/Owner, Control/Process/Remediation Owner, Compliance Officer, Audit Committee Member, Board Viewer and Internal Audit Quality Reviewer. Permission categories separate universe, planning, scope, risk/appetite, control tests, SoD, monitoring execution/review, remediation, obligations, policies, governance, AI and quality.

Services recheck active membership and engagement grants rather than trusting a supplied Context. Owner-only identities can access assigned/prepared GRC records, with shared approved framework/policy/scoring metadata; they cannot read professional execution models. Board roles have only published governance access, without grc.read. Preparer/editor separation, version checks and module evidence permissions apply to review. The synthetic CAE also has an explicit Financial Reporting Manager assignment solely to read the demo IFRS-note fixture; that grant is not added to the CAE role globally.

Real tests cover self-approval rejection, owner isolation, board denial, immutable database history and FORCE RLS. The retained Phase 1–9 suite covers tenant isolation, IDOR, revoked roles, source authorization and other platform controls. A new external penetration test and exhaustive custom-role combinations have not been performed.""",
        ),
    }
    for name, (title, text) in documents.items():
        write(name, title, text)
    counts = "\n".join("- " + k + ": " + str(v) for k, v in sorted(demo["counts"].items()))
    write(
        "sample-data-inventory.md",
        "Guarded synthetic inventory",
        f"""Guard conditions require development mode, explicit synthetic enablement, the exact demo database, the fixed synthetic tenant and its marker. Scripts fail closed before mutation. No production tenant data was used. Scripts/enrich_phase10.py is idempotent by stable P10 references and uses actual create/submit/approve endpoints. Original journal count remains {demo["journal_lines_after"]:,}; all original financial facts are retained.

{counts}

- Actual immutable alerts: {demo["alerts"]:,}.
- Annual plan commitments / internal audit scopes: 10.
- Reviewed management action workpapers: 100 base plus proof scenario.
- Base rule definitions: 30, with additional worker and configured SoD proof rules recorded separately.

Proof records and browser-created scoring drafts can increase these values on later reruns. Counts are evidence from demo-verification.json, not hardcoded UI values. Evidence references are explicitly synthetic software fixtures, never real control assurance or market/legal evidence.""",
    )
    write(
        "api-inventory.md",
        "API inventory",
        """Canonical GRC routes are under /api/v1/grc/engagements/{eid}. Typed schema metadata is available from /workspace; /api/v1/grc/frameworks supplies public standards metadata, rule source requirements and task names. The same engagement/team infrastructure is retained.

- GET /workspace, /dashboard, /records/{kind}, /records/{id}/history.
- POST /records/{kind}; PATCH /records/{id}; POST /records/{id}/actions.
- POST /records/{id}/calculate; POST /internal-audits/{id}/transitions.
- GET /rcm, /runs, /alerts, /alerts/{id}/source.
- POST /monitoring/{id}/execute; POST/GET /schedules; PATCH /schedules/{id}.
- POST /samples; POST /sod/import (bounded evidence-matched multipart CSV).
- POST /policies/{id}/acknowledgments; GET /notifications.
- POST /ai; POST /board/{id}/publish.
- GET /board/packages, /board/packages/{id}, /board/packages/{id}/export/{pdf|docx}.
- Existing /api/v1/ml/predictions/{id}/feedback and /datasets/{id}/curation consume registered monitoring inference.

Frontend routes are /grc/{engagementId}/{area} for all 24 grcAreas in grc-studio.tsx and /board for restricted recipients. /grc is the engagement chooser. Access uses the existing cookie-protected BFF and tenant header; bearer tokens are not exposed to browser storage.""",
    )
    write(
        "regression-results.md",
        "Regression and security evidence",
        f"""Baseline: 353 backend passed / 2 skipped; 22 frontend passed. Latest full backend result: {result}. Frontend: 24 tests passed; see frontend-tests.txt and frontend-build.txt. Browser: see browser-results.json and browser-run.txt; four scenarios cover all 24 routes, typed draft persistence, four viewport widths and board access. Twelve focused Phase 10 tests (plus the retained calculation suite: 47 focused checks passed) include all 30 diagnostic AI task paths, import-triggered worker execution, source-version staleness, independent approval, owner isolation, immutable history and CSV/SoD/scoring/calendar/large-signature behavior.

Fresh migration from zero to 0010 succeeded in auditos_phase10_migration_test as auditos_phase4_app, which remains a non-superuser without BYPASSRLS. End-to-end-verification.json records actual Redis/Celery jobs, deduplication replay, source investigation, evidence-backed ML feedback and approved test/deficiency/action/retest/closure chain. The two inherited optional smoke tests are live Zoho (explicit opt-in and authorized OAuth credentials) and live Tally (explicit opt-in and an authorized local installation); these remain skipped.

No claim of production penetration-test certification, live ERP integration, live LLM semantic accuracy or professional standards conformance is made. Export QA used actual PDF/DOCX output, LibreOffice rendering and visual page inspection.""",
    )
    write(
        "bugs-found-and-fixed.md",
        "Bugs found and fixed",
        """1. Review metadata cleanup incorrectly stripped business review_date fields. Cleanup now removes only review_stage, review_cycle and review_approvers. Backend and editor regression tests preserve business review dates.
2. Phase 2 flag evidence can be plain text. Monitoring now preserves the source evidence rather than attempting unconditional JSON decoding.
3. Missing ERP access inputs caused a key error. Access monitoring now reports NOT_TESTABLE; workpaper parameters are bounded and approved access references checked.
4. Versioned schedule mutation exposed expired ORM timestamps to synchronous serialization. The API refreshes the row after flush.
5. UI review statuses/monitoring paths were aligned with actual IN_PROGRESS/REVIEW_REQUIRED and canonical endpoints. The scoring form’s dictionary buttons now have distinct accessible names, numeric matrix options retain integer values, conclusions require explicit selection, and revised drafts remain submittable. The browser test creates, edits and submits an actual draft.
6. Grid parent sizing could collapse the grid body. GRC grids now have explicit container height; overdue and management lanes are bounded scroll regions.
7. Approved risk assessments could be reinterpreted after a scoring change. Approval freezes calculation sources; later changes mark stale and require reassessment. Heatmaps separate methodologies and use actual appetite breaches.
8. A full 250,024-line engine benchmark exhausted the 1 GB ordered-aggregate budget. Whole-journal hash partitions now bound live aggregate states without splitting journals or changing canonical signatures. A >25,000-row regression checks exact signatures.

9. Unrelated owner roles could view unapproved shared policy/scoring/framework drafts. Shared owner access now requires an approved record; assigned/prepared drafts retain their intended access. A real API regression covers policy listing and revision-history denial. Owner scoping also uses the actual engagement grants: an unrelated or ungranted firm-level professional role cannot widen resource visibility.
10. Early immutable alerts used a per-request synthetic flag. New monitoring derives synthetic provenance from the demo tenant; read models expose authoritative tenant provenance alongside the retained legacy flag. Existing immutable history is not rewritten.
11. Repeated synthetic mapping pairs were corrected through recorded reopen/edit/submit/independent-approval cycles. The fixture now contains 300 distinct same-process risk-control pairs; fresh seeds generate the corrected relationships directly.

Harness issues were also corrected: the preview needed its explicit public origin for CSRF protection, tests must ignore Next’s empty global live region, and the new test folder needed a package marker. These are distinguished from product defects. Remaining limitations are recorded in phase-10-report.md.""",
    )
    population = performance["retained_population"]
    write(
        "performance.md",
        "Measured performance",
        """These are local synthetic measurements, not production SLAs. Five in-process ASGI samples were taken for each read endpoint; no network latency or peak RSS claim is made.

"""
        + "\n".join(
            "- "
            + key
            + ": median "
            + str(value["p50_ms"])
            + " ms; max "
            + str(value["max_ms"])
            + " ms."
            for key, value in performance["api"].items()
            if isinstance(value, dict)
        )
        + f"""

500 alerts were read in ten bounded pages in {performance["api"]["500_alerts_paged_seconds"]} seconds. The retained population benchmark covered {population["rows"]:,} actual original synthetic lines: extraction {population["extract_seconds"]} seconds, DuckDB load/signatures {population["duckdb_load_seconds"]} seconds and 25 rules {population["rules_seconds"]} seconds. The engine retained a 1 GB limit and two threads. Cross-period journal identifiers were qualified to prevent collisions; this benchmark is not an engagement conclusion.

Monitoring timings and explicit unavailable-source statuses are in performance.json. Actual model scoring is bounded to 10,000 rows per call; the demonstration uses 1,000-row and 100-row slices with frozen source snapshots. Production concurrency, long-running Beat uptime and peak process memory need separate operational qualification.""",
    )
    write(
        "phase-10-report.md",
        "Phase 10 implementation and verification report",
        f"""Phase 10 is delivered with **IMPLEMENTED WITH LIMITED SCOPE** status. Core governed workpapers and the demonstrated workflows run; this is not a claim that every enterprise integration or professional certification requirement is complete. Phase 11 was not started. Changes remain uncommitted and unpushed.

## Delivered modules and migration

Twenty-four typed workpaper kinds cover applicable frameworks, universe, scoring/appetite, annual planning, internal audit scopes, risks/assessments/KRIs, controls/RCM/tests/SoD, monitoring, investigation decisions, deficiencies/actions/closure, obligations, policies, vendors, reports/board packages and QAIP. Migration 0010 adds immutable execution/alert tables and versioned schedules, forced tenant RLS and role permissions. Existing identity, evidence, revisions, review separation, financial engines, ML registry and BFF are retained. See architecture.md and api-inventory.md for contracts and all new routes.

## Actual evidence

- Backend baseline: 353 passed, 2 skipped. Latest full run: {result}.
- Frontend: production build, TypeScript, lint and tests recorded in the accompanying logs; four browser scenarios cover all 24 workspaces, real draft persistence, 1920/1440/1024/768 widths and board restrictions.
- Original financial facts preserved: {demo["journal_lines_after"]:,} journal lines.
- Synthetic inventory: 100 risks, 200 controls, 300 mappings, 100 base tests, 50 base deficiencies, 100 base actions, 20 KRIs, 30 base rules and ten planned internal audits. Additional proof records are listed in sample-data-inventory.md.
- Persisted review candidates: {demo["alerts"]:,}. Rule findings, ML signals and human conclusions remain separate; unavailable source adapters report NOT_TESTABLE.
- Real worker and scheduler jobs completed; replay deduplication and an approved sampled test → deficiency → action → retest → independent closure chain are recorded in end-to-end-verification.json. Import-triggered outbox execution is also covered in the disposable-database integration test.
- Actual TensorFlow.js inference uses deployed Phase 9 models, with private registered holdout datasets, calibration/schema/snapshot lineage and evidence-backed feedback. No automatic retraining occurs.
- All 30 AI task paths pass diagnostic gateway tests. No live generative semantic analysis is claimed.
- Actual published report exports are in exports/; screenshots of every route and responsive layouts are in screenshots/.
- The 250,024-line bounded engine benchmark loaded in {population["duckdb_load_seconds"]} seconds and evaluated 25 rules in {population["rules_seconds"]} seconds after extraction. Detailed read timings are in performance.md.

## Capability classification

**FULLY IMPLEMENTED & TESTED within the stated contracts:** Decimal ordinal matrix/lookup and resource calculations; permission-pair SoD by dated scope; immutable execution/alert snapshots; independent approval and owner/board restrictions; source-version staleness protection; CSV parser bounds; transactional import outbox and worker authorization; the documented synthetic worker/remediation/retest/closure scenario.

**IMPLEMENTED WITH LIMITED SCOPE:** 24 frontend workspaces and structured editors; universe/planning; ERM/KRIs; RCM graph; control testing; continuous monitoring with available GL/workpaper adapters; compliance/policy/vendor/QAIP registers; report/board publication and PDF/DOCX export; real experimental ML integration; internal assignment notifications. Evidence is synthetic; these do not establish real operating effectiveness, complete standards conformance or production service levels.

**PARTIALLY IMPLEMENTED:** advanced source pickers, organization hierarchy navigation, richer report design, sub-engagement-specific closure aggregation, management distribution/reminder campaigns, exhaustive role combinations, long-running scheduler operations and full enterprise connector coverage. Some structured editors still use explicit source references.

**NOT IMPLEMENTED:** live ERP/payment/inventory/vendor intelligence connectors, automatic access remediation, regulator submission, exhaustive licensed standards corpora, external quality certification, automated reminder/escalation delivery and production deployment/operational qualification.

**BLOCKED for live semantic evaluation:** no approved external generative provider was exercised in this environment. The existing configurable gateway and disclosure safeguards are wired; mock transport output is explicitly diagnostic. Models remain experimental and are not validated real-world fraud detectors.

## Security, fixes and handover

Fresh 0010 migration succeeded using the existing non-superuser/no-BYPASSRLS application role. Tests cover preparer separation, ownership, board restrictions, immutable database history, input bounds, source changes and public snapshot-override rejection, alongside retained platform regressions. Read bugs-found-and-fixed.md for reproducible corrections, including the large-population ordered-aggregate memory defect. PDF and DOCX pages were rendered and visually checked.

Start backend/Celery using existing configuration, with a worker consuming grc and a supervised Beat process for recurring dispatch. Keep synthetic database guards explicit when running enrich_phase10.py, verify_phase10.py, export_phase10.py and benchmark_phase10.py. Production readiness still depends on approved evidence, licensed methodology where required, operational monitoring, connector authorization, live model/provider evaluation and the limitations above. These are handover dependencies only; no Phase 11 work was begun.
""",
    )
    print("Wrote", len(list(OUT.glob("*.md"))), "Phase 10 documents")


if __name__ == "__main__":
    main()

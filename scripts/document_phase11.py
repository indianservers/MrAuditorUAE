"""Build a factual handover from retained verification evidence."""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "docs/phase-11"


def read(name):
    return (
        (D / name).read_text(encoding="utf-8")
        if (D / name).exists()
        else "Not recorded"
    )


def main():
    demo = json.loads(read("demo-verification.json"))
    proof = json.loads(read("verification.json"))
    backend = re.findall(
        r"\d+ passed, \d+ skipped[^\n]*", read("regression-backend.txt")
    )
    frontend = re.findall(r"Tests\s+([^\n]+)", read("frontend-tests.txt"))
    browser = re.findall(r"\d+ passed[^\n]*", read("browser-run.txt"))
    status_counts = Counter(
        step["status"] for run in demo["investigations"] for step in run["steps"]
    )
    docs = {
        "agent-registry.md": """# Specialist registry

Twelve logical agents: Audit Orchestrator; Financial Data; External Audit; IFRS Reporting; UAE Corporate Tax; UAE VAT; Transfer Pricing; Pillar Two and DMTT; Internal Audit and GRC; Document Intelligence; TensorFlow.js ML Investigation; Quality and Professional Review.

The registry in `backend/app/modules/enterprise_ai/catalogue.py` defines identifiers, task recipes, allowlisted tools, required permissions, versioned contract names, prompt version, call/time/context/token limits, error handling and approval policy. Tools run in-process within the existing API/worker stack. This is typed deterministic delegation; no uncontrolled agent conversation or autonomous specialist legal reasoning is claimed. Quality checks source contracts and cannot grant professional approval.

`GET /api/v1/ai/agents` and `/ai/tools` expose safe metadata. Tool input/output contracts use strict Pydantic models. Twelve calls, depth one, parallelism one and 90 seconds per tool are the implementation limits. Explicit narrative generation uses the existing AI gateway and its token limits; the orchestrator has no model-controlled SQL, code, shell, network, training or deployment tool.
""",
        "orchestration.md": """# Planning and delegation

Fifteen reviewed recipes support revenue, CT, QFZP, TP, Pillar Two, document/ledger, GRC, planning, anomalies, reconciliation, evidence requests, workpaper review, VAT, loan interest and IFRS disclosure work. Explicit task selection is authoritative. Optional natural language routing uses deterministic keyword aliases and rejects ambiguous or unsupported requests; it is not a general semantic planner.

A command resolves scope from the authorized engagement and checks every required specialist permission before collecting any source. A mismatch denies the whole initial command. Individual source reads enforce domain service policies. A missing input becomes MISSING rather than generated content. Some bounded data becomes LIMITED. Validation or execution errors become FAILED receipts; later independent steps can still run. The overall result is PARTIALLY_COMPLETED when coverage is incomplete.

Template versions are immutable read-only graphs saved by an authorized AI configurator. Starting a template creates a separate workflow with its exact tool list. Source permissions are rechecked at execution. Custom financial mutation, communications and code nodes are not supported.
""",
        "tool-security.md": """# Tool security

Authentication and tenant membership come from the existing bearer-token dependency. Services recheck active user, active tenant, tenant role policies and current engagement grants. Explicit tenant and engagement filters accompany forced PostgreSQL tenant RLS. Platform administration and AI configuration roles do not imply confidential engagement access. Investigation results are private to their initiator; approval reviewers receive only proposals they are authorized to review and source dependencies they can still read.

Financial tools derive entity and period from the engagement, and client from the entity. Journal, trial-balance and stored analytics/reconciliation citations require the current active import snapshot. Snapshot hashes and scope are rechecked on subsequent reads; superseding a financial import invalidates the old investigation. Calculation tools call existing current-dependency validators; IFRS financial packages additionally require their independent adoption approval. Specialist records require approved/locked status. TP transitive source graphs recheck dataset AI disclosure licenses. GRC owner restrictions remain in the existing GRC service.

Every executed tool has a durable hashed receipt with permission, timing, status, bounded output and sources. Execution denials stop the run with a redacted category. HTTP authorization failures before invocation retain the existing redacted request log. Source text and credentials are not logged. Nested private ML object locators are removed. No general-purpose model tool can issue SQL, Python, shell commands or outbound network requests.
""",
        "workflow-state-machine.md": """# Durable execution

CREATED leads to RUNNING and then COMPLETED or PARTIALLY_COMPLETED. PAUSED, RESUMING, FAILED and CANCELLED are supported. Template configuration has a separate TEMPLATE_ACTIVE marker. Approval request state is stored separately. WAITING_FOR_DATA and an embedded graph approval node are not implemented.

Workflow state, immutable step events and hashes live in PostgreSQL. An advisory lock serializes each run. Every worker step commits independently. A crash before a step commit permits retry; committed steps are counted and not repeated. Redelivery reauthorizes the initiating user and validates source versions. Changing a source invalidates retrieval and continuation; start a new investigation rather than combine versions.

Explicit dispatch creates a queued event before Redis dispatch. Broker failure retains recoverable state. The scheduler outbox redispatches only explicitly queued work. Cancellation and pause are checked between steps, not inside an executing provider call. A worker is bounded to twelve steps; provider work remains in the existing gateway. The real worker and replay proof is in verification.json.
""",
        "human-approvals.md": """# Human approval gateway

The implemented action is create-draft-workpaper. A completed source collection proposes a title and editable narrative linked to collected approved record IDs. Its exact before value (no record), after values, requesting user, agent and source versions are hashed. An independent reviewer needs both AI decision and workpaper approval permissions. Decisions preserve reviewer, timestamp, comments and exact payload hash.

The requester executes only the approved exact payload. Both requester and reviewer permissions and dependencies are checked again. Execution creates an IN_PROGRESS workpaper through the existing audit service, verifies that state and stores one execution receipt. Retrying returns the same created record. Source reopening rejects the prior approval. The new workpaper still follows the original independent professional review chain.

There are no AI executors for financial posting, tax-treatment adoption, risk approval, approved note changes, finding closure, final publication, rule interpretation, ML deployment or external messaging. These remain governed domain workflows. Proposal inbox decisions are not substitutes for those approvals. Database step/extraction/match history is immutable; mutable proposal lifecycle is exposed only through controlled service operations.
""",
        "document-intelligence.md": """# Document intelligence scope

Evidence binaries remain in the existing private versioned object store. Extraction requires approved current evidence, CLEAN scan status and a matching source hash. Without available ClamAV, ordinary upload remains QUARANTINED and cannot be submitted or indexed. The synthetic demo alone uses a hash-allowlisted scanner test double inside its guarded seed process; that is not malware-scanning assurance.

Supported extraction: unencrypted text PDFs up to 100 pages; UTF-8 CSV; bounded XLSX sheets with cached values; DOCX paragraphs and bounded tables. Input is limited to 16 MiB, extracted text to 250000 characters. Office archive validation remains in the existing uploader. CSV/XLSX/DOCX provide structured tables; PDF text extraction does not infer table layout. Scanned/image pages return OCR_REQUIRED or a clear warning; OCR is not configured.

Classification is selected by an authorized user. Explicit-label regex extraction supports reference, date, currency, amount, counterparty and tax amount. It does not understand arbitrary invoice or contract layouts. Fields preserve page/section, extraction method and unverified quality. Missing fields are explicit. A human correction creates a new extraction and new chunks; old citations become stale. The UI supports amount correction; the API accepts bounded supported fields with existing page references. Corrections are not professional evidence confirmation.

Approved workpapers, IFRS notes, GRC policies and adopted engagement technical rules may be indexed directly from their authorized database bodies. Their references are sections, not physical pages. No second binary store is created. Repeated approved-source indexing preserves immutable history; only the latest extraction is served. Global duplicate-content search and automated semantic classification are not implemented.
""",
        "document-ledger-matching.md": """# Evidence matching

Invoice or bank-style extracted fields can be compared with authorized active journal lines. Signals are exact Decimal amount, currency, posting date, counterparty and reference substring. Weights are 4, 2, 1, 1 and 2 out of ten. Missing information lowers the score. The score is rule agreement, not a calibrated probability and not a confirmed accounting match.

The general UI compares the first fifty active ledger lines; the API can evaluate a specifically authorized journal ID. This is bounded candidate comparison, not a full-population fuzzy search. Accept/reject decisions require evidence-review permission, an exact signals hash and current extraction/ledger sources; immutable decision records preserve rationale and lineage. Accounting records never change.

The fifty synthetic matching cases have independently specified agreement/mismatch amounts. Acceptance is a recorded reviewer judgment, separate from an unconfirmed machine suggestion. Loan-master, lease schedule, credit-note, asset-master and VAT-claim specialized matching adapters are not implemented.
""",
        "rag-architecture.md": """# Source-linked retrieval

The implemented backend is PostgreSQL keyword search over bounded chunks, with source authorization and current-version checks both before content is returned and on subsequent citation reads. Tenant, client, entity, period, engagement, document version, extraction identity, page/section, confidentiality, source reference and hash are preserved. Current implementation permits confidential/restricted labels but does not define a second classification-based clearance hierarchy beyond existing resource access.

Reopening evidence, changing versions or correcting an extraction invalidates earlier chunks. Reindex current approved sources. Prompt instructions are never the authorization boundary. The explicit narrative endpoint uses only validated supplied citations through the existing AI gateway, with a 11000-character context cap, 30 requests per user/hour and approved external disclosure required for non-mock providers.

Semantic embeddings, pgvector indexing, hybrid reranking, legal effective-date filtering and shared prior-engagement retrieval are not implemented. Metadata effective_date is currently null for extraction chunks. Do not call keyword retrieval hybrid semantic RAG. A generated citation being valid proves source identity/access, not that the model's interpretation is supported; live semantic grounding evaluation remains required.
""",
        "regulatory-knowledge.md": """# Regulatory knowledge boundary

The research workspace shows inherited official publication metadata from VAT, TP and DMTT registries and GRC framework metadata. This is source discovery, not an automatically current full-text legal corpus. DMTT registry lifecycle flags retain repealed MD88 and replacement metadata from prior phases. Users must verify original publication, knowledge date, fiscal applicability and adopted rule version in the professional module.

Client evidence and engagement-adopted technical rules remain distinguishable from authoritative law. No IFRS/ISA licensed text, private commercial comparable corpus or external legal content is copied automatically. No invented article, paragraph, quotation, tax result or legal conclusion is generated by a tool. Effective-date retrieval, corpus ingestion/licensing administration and substantive technical research remain limited/missing.

Security design consulted the OWASP GenAI project and NIST AI 600-1. Links are in pre-implementation-audit.md. This is not a NIST/OWASP compliance certification.
""",
        "ml-integration.md": """# TensorFlow.js integration

The two ML investigation tools retrieve existing Phase 9 immutable inference/model events through ML resource authorization. Payloads are bounded and private object locators are stripped recursively. Large historical payloads may be LIMITED; newer retrieval bounds nested samples to five elements. Original events are never rewritten.

This phase retrieves stored predictions/evaluations; it does not run training or deployment from ordinary investigations. Those governed Phase 9 workflows remain separate. A historical inference is evidence of the stored model's output on its original snapshot, not a new live inference on the latest ledger. Stored drift/calibration and evaluation metadata remain part of the source. Experimental synthetic validation does not establish real-world fraud detection.

The workspace and outputs keep deterministic receipt, ML signal, draft AI explanation and auditor conclusion separate. Anomaly scores cannot prove fraud. General inference latency/training benchmarks remain in Phase 9; Phase 11 measurements concern bounded retrieval and orchestration.
""",
        "ai-command-center.md": """# AI command center

Sixteen workspaces live under /ai: command-center, agents, investigations, designer, monitor, approvals, documents, matching, knowledge, research, citations, evaluations, providers, usage, security and schedules. They use the existing Precision visual system and authenticated BFF.

The command center selects an authorized engagement, reviews a typed recipe, creates a durable investigation, executes a next step or dispatches a real worker, polls actual state, pauses/resumes/cancels at step boundaries and opens real receipts. Library/context panels collapse. Missing sources and errors remain visible. Draft narrative is explicit, source-linked and marked diagnostic for mock output. Editable recommendations become exact-payload proposals, not financial changes.

Citation Explorer verifies and opens authorized original record/journal/snapshot/chunk/ML/calculation sources. PDF/DOCX exports are drafts, reauthorized on every request, with original numeric ledger excerpts only when supplied by deterministic receipts. Provider administration shows safe approved-model inventory independently of engagement selection, so technical administrators need no confidential record grant. Credential changes remain in existing controlled configuration. Saved-run directory is bounded to the latest hundred in the UI; API pagination exists. There is no generic unrestricted chatbot.
""",
        "workflow-designer.md": """# Read-only workflow designer

React Flow displays ordered tool graphs with draggable nodes. Users can select a reviewed recipe, add distinct allowlisted retrieval tools, remove or move tools, validate the graph and save an immutable explicitly active read-only version with AI configuration permission. A separate command creates a run from that version. Templates cannot themselves be dispatched or stepped as runs.

Graph validation rejects unknown tools, duplicates, cycles/backwards edges, out-of-range indices and disconnected nodes. Every template node is permission-checked at save and again on execution. Maximum twelve nodes. Only ordered acyclic retrieval graphs are supported; arbitrary code, unbounded branching, mutation nodes and visual embedded professional approval/notification nodes are not implemented. Approval proposals use the separate controlled inbox.
""",
        "role-permissions.md": """# Authorization and role grants

Existing professional roles with audit.read receive investigation/read/run/proposal/index permissions. Roles with workingpaper.approve also receive AI review/schedule/usage/audit-log/evaluation/knowledge permissions. Firm Administrator receives AI technical configuration. AI Administrator receives technical administration and usage/evaluation/audit-log permission names but no automatic engagement or professional source access. Platform Administrator receives no confidential data grants.

Effective rights still come from active engagement grants and tenant role-policy overrides. Resource services recheck permissions even if a caller constructs a Context with forged permission bits. Client roles are not automatically granted investigation tools. Board and narrow GRC owner roles remain limited. Investigations are private to their initiator. Reviewers independently require source and approval permissions. No credentials or hidden prompt content is exposed in metadata APIs.

Migration 0011 freezes schema/grants; runtime ROLE_PERMISSIONS provisions future installations. Inspect role-permissions.json and OpenAPI for exact current contracts. Provider inventory has its own ai.provider.manage dependency so technical administration need not be granted investigation read.
""",
        "synthetic-scenarios.md": f"""# Guarded synthetic scenarios

`scripts/enrich_phase11.py` requires the existing guarded development demo DB, fixed synthetic tenant and explicit local demo password. It provisions an independent synthetic reviewer and creates evidence through the actual upload/review APIs. The scanner test double accepts only generated fixture hashes within that process; all fixture bodies explicitly disclose its synthetic status.

Recorded inventory: {json.dumps(demo["inventory"])}. Fifty fixtures have independent amount/page oracles; fifty actual journal comparisons have accept/reject decisions. There are 105 stored investigations spanning all fifteen recipes, and 100 independent approved/rejected proposal examples. No original accounting fact is replaced. Recipe executions are test workflows; this is not a claim of thirty distinct production automation templates.

Original receipt statuses across the 105 seeded investigations: {dict(status_counts)}. MISSING and LIMITED receipts are deliberately retained. Eight requested scenario families are exercised by real source-collection code, document comparison/proposals and client denial. End-to-end final accounting/tax treatment approval is not automated by this phase. The demo does not establish substantive legal, economic or audit conclusions.
""",
        "evaluation-methodology.md": f"""# Evaluation methodology

The built-in reproducible evaluator uses six independently authored explicit-label text fixtures: invoice, loan, lease, bank statement, financial statement and contract. It measures exact field precision/recall, invented fields and page references. It also checks unsupported intent rejection and deterministic amount/currency mismatch. Expected values are authored independently of extractor output; no model grades its own work.

The synthetic document oracle independently specifies amount and page for fifty generated evidence records: {proof["amount_and_page_oracle"]}. The fixture evaluator results are in demo-verification.json under evaluation. Strong results here apply only to these simple labeled layouts. PDF visual layout/OCR/table semantic accuracy, real model hallucination and subjective synthesis quality are NOT_EVALUATED. The external provider was not used.

Approval, authorization, source freshness, immutable history, exact payload, retry, cancellation and graph controls are tested with actual PostgreSQL/FastAPI services. Browser results measure real UI actions and worker execution. Do not infer general AI completion accuracy from transport tests or page rendering.
""",
        "ai-security-tests.md": """# Security verification

Tests cover strict unknown input rejection; unsupported SQL/shell/exfiltration/training intents; unknown/cyclic/disconnected tool graphs; client-role denial; unrelated engagement denial; self-approval denial; changed hash/stale approval denial; execution before approval; duplicate execution; immutable event history; quarantined uploads; source reopen; extraction correction and stale citation rejection. Indirect injection text in a synthetic CSV remains literal source content and cannot select executable tools.

Hard authorization and typed-plan boundaries provide the deterministic protection. They do not prove a live LLM will never produce misleading narrative. The mock gateway's strict output and supplied-citation enforcement are tested; live model red-teaming remains outstanding. AI tools cannot perform unrestricted network requests, arbitrary SQL, code execution, external communication or training.

The application does not claim comprehensive malicious PDF parser isolation or malware-scanner validation. Clean real-world files require a working scanner. Resource limits reduce extraction exposure but do not replace sandboxed document-processing operations in production. A malicious file/parser corpus and multiple-user production load tests remain required.
""",
        "performance-report.md": f"""# Measured performance

Population: {proof["financial_lines"]} existing journal lines; {proof["indexed_documents"]} indexed synthetic documents; {proof["chunks"]} chunks. The tests use targeted retrieval rather than sending the ledger to a model.

Five-sample measurements in seconds: {json.dumps(proof["latency"])}. Concurrent request measurement: {json.dumps(proof["concurrent_requests"])}. RSS before {proof["rss_before_bytes"]} bytes; after {proof["rss_after_bytes"]} bytes. This is verification-process RSS before/after, not sampled peak API/worker memory. No database CPU/load or multi-identity production saturation benchmark is claimed.

Real worker: {json.dumps(proof["real_worker"])}. Actual scheduled run: {json.dumps(proof["scheduled_run"])}. Queue recovery is durable and scheduled processing was explicitly enabled then paused. Semantic retrieval, OCR throughput, external model tokens/cost and real legal corpus performance could not be measured. Existing gateway usage retains provider-vs-mock provenance; no monetary price is invented when pricing is absent.
""",
        "regression-results.md": f"""# Regression results

Before implementation: backend 365 passed, 2 optional live-connector skips; frontend 24 passed. Migration baseline 0010.

Latest retained backend result: {backend[-1] if backend else "Final run still in progress; inspect regression-backend.txt"}. Latest frontend result: {frontend[-1] if frontend else "Not recorded"}. Browser result: {browser[-1] if browser else "Not recorded"}. See the corresponding raw output and browser-results.json. Backend uses a fresh migrated disposable PostgreSQL database and Redis; demo remains separate.

Production build, TypeScript, ESLint, Ruff and mypy are checked separately and raw outputs retained. Migration 0001 through 0011 was applied to a fresh database, and 0011 was applied to the guarded existing demo. Two skips require real authorized Zoho OAuth / Tally installations; they are not passes. Prior-phase evidence files modified by their tests are restored from HEAD before final handover.
""",
        "bugs-found-and-fixed.md": """# Defects found and fixed

- Initial frozen permission DDL referred to a nonexistent description column. Corrected before successful fresh migration; no schema application was claimed from the failed attempt.
- Serializing an updated workflow could lazily load expired server timestamps in async SQLAlchemy. Explicit refresh now precedes serialization of changed runs/proposals/control state.
- The first test fixture incorrectly assumed the same approval chain for evidence and workpapers. Corrected the fixture to obey the existing real chains; no domain review assertions were weakened.
- Match fixture target IDs were outside the generic first-fifty ledger excerpt. Added explicitly authorized journal-ID comparison and retained the general UI's bounded coverage disclosure.
- Browser task-selection lookup included option text in a label. Used an accessible combobox role selector; real worker E2E then passed.
- Added strict prohibition on executing template configuration as a run and froze each configured version into a new run.
- TP study tool now uses the actual study kind and traverses source graph AI licenses. IFRS financial package retrieval requires independent adoption approval. ML nested samples are bounded to preserve useful metadata without private locators.
- Trial-balance and stored analytical receipts now carry current snapshot/hash citations. A dedicated test proves that superseding the import invalidates both subsequent read and continuation.
- The 768px library now scrolls within a compact panel, and provider inventory no longer requires engagement selection or confidential directory queries.

Known limitations are documented in phase-11-report.md. They are not relabeled as fixed defects.
""",
    }
    for name, content in docs.items():
        (D / name).write_text(content.strip() + "\n", encoding="utf-8")
    report = f"""# Phase 11 implementation report

Status: **IMPLEMENTED WITH LIMITED SCOPE; overall enterprise definition of done remains PARTIAL.** This phase delivers a working permission-controlled investigation foundation, not an autonomous accountant or production-qualified general AI system.

## Delivered and verified

- Twelve logical specialist agents, 27 typed allowlisted tools and fifteen reviewed recipes. Optional deterministic intent routing; explicit task selection; configured read-only graphs with immutable versions.
- Durable PostgreSQL workflow state and hashed immutable step events; Redis/Celery execution, explicit outbox dispatch, pause/resume/cancel, current permission/source rechecks and idempotent retry.
- Exact-payload independent human approval for draft workpaper creation through the existing audit engine. Stale and self approvals rejected; execution retry returns the original unapproved draft.
- Private source extraction/indexing, human correction versions, page/section references, keyword retrieval, citation freshness, deterministic journal comparison and immutable accept/reject decisions.
- Source-linked explicit narrative via the existing provider gateway; mock output is diagnostic and requires human review. PDF/DOCX draft exports were rendered and visually inspected.
- Sixteen frontend workspaces; real API actions, React Flow validation/configuration, evidence/approval/citation views, usage provenance and audit receipts.
- Guarded demo inventory: {json.dumps(demo["inventory"])}. Original {proof["financial_lines"]} journal lines preserved. Real worker and schedule proof, zero duplicate retry receipts.

## Verification

Backend: {backend[-1] if backend else "Final run pending"}. Frontend: {frontend[-1] if frontend else "Not recorded"}. Browser: {browser[-1] if browser else "Not recorded"}.

Fifty labeled amount/page oracle cases: {proof["amount_and_page_oracle"]}. Six explicit-label fixture families achieved the values recorded in demo-verification.json. These are synthetic label/transport checks, not general OCR, semantic reasoning or fraud-detection accuracy.

The retained 105-investigation demo has {dict(status_counts)} step receipts. Incomplete sources stay visible. The eight requested scenario families run actual code, but final professional treatment remains in existing governed domain workflows; missing evidence and licensed material are not fabricated.

## Limits and external dependencies

- **Not implemented:** semantic embeddings/pgvector/hybrid reranking; automatic OCR; general document-layout understanding; legal effective-date retrieval; shared cross-engagement knowledge; arbitrary workflow branching/mutation nodes; broad contract-to-master/schedule matching; global duplicate-content workflow; client communications; autonomous downstream financial/tax/report/model actions.
- **Limited:** selected document classification, six explicit-label fields, keyword retrieval and fifty-line/targeted matching; sequential specialist tool delegation; metadata-only legal source discovery; read-only workflow editor; draft workpaper proposals; provider inventory and fixed execution/rate limits. Tenant-specific monetary budgets and price administration are not implemented.
- **Requires external credentials and evaluation:** actual semantic LLM quality, provider billing/cost fidelity and adversarial model testing. Mock outputs must never be described as professional AI analysis.
- **Narrative limitation:** citation identity/access is validated, but semantic support and numeric claims embedded in prose are not automatically proven. Reviewers must verify all generated narrative against original deterministic sources; no external semantic quality result is claimed.
- **Requires licensed sources:** IFRS/ISA full text and authorized comparable content. TP source graph licensing checks fail closed. Regulatory source metadata does not establish current legal applicability.
- **Requires production operations:** real ClamAV/OCR integration, isolated parser processing, tested Beat deployment, multiple-identity load/restart/drill coverage and reviewed retention/backup policies. The demo fixture scanner is a disclosed test double, never scanner assurance.

## Evidence and operation

See architecture.md, agent-registry.md, tool-security.md, human-approvals.md, document-intelligence.md, rag-architecture.md, evaluation-methodology.md, ai-security-tests.md and performance-report.md. OpenAPI and role JSON describe actual contracts. Screenshots are in screenshots/. Application-generated sample draft exports are in exports/.

Run a current worker with `celery -A app.workers.celery_app:celery_app worker --pool=solo -Q enterprise-ai`. The scheduler task is auditos.enterprise_ai.tick; only explicitly active schedules and explicitly queued runs dispatch. The proof schedule was paused. Preview: frontend port 3003, API port 58006. Development previews are not a production deployment.

## Phase 12 readiness

Core authorization, durable execution and source lineage are available for review. The outstanding capabilities and operational qualifications above must remain explicit readiness gates. **Phase 12 has not started.** Work remains uncommitted; prior-phase work was preserved.
"""
    (D / "phase-11-report.md").write_text(report, encoding="utf-8")
    print("Wrote", len(docs) + 1, "Phase 11 handover documents")


if __name__ == "__main__":
    main()

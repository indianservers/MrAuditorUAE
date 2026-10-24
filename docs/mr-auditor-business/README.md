# Mr Auditor: connected UAE business workstreams

Release status: **partial specialist coverage, with explicit limitations**. This is a working implementation in the existing application, not 100 newly built calculation engines or a claim of full professional acceptance. It preserves cases 01–50 and adds the exact new 51–100 catalogue; the earlier audit-use-case catalogue and local ML foundation remain separate and intact.

Open `/ai/uae-use-cases`, select an authorized engagement, then choose the business question. Entity, financial period and reviewed jurisdiction come from that engagement. UAE case APIs reject other approved jurisdiction packages; changing a browser country selector does not establish legal applicability.

## What changed

- Added 100 explicit, typed UAE case definitions, source requirements, engine mappings and bounded assistant recipes. Existing working engines are called rather than relabelled as new numeric capabilities.
- Added a case workspace with search, contextual questions, automatic read-only collection, progress/pause, specialist source selection, governed calculations, source inspection, primary-source locators, and source-linked draft papers.
- Added a closed action registry for shared calculations, existing background country workflows, workpapers, evidence requests, client-query drafts, review tasks, structured findings, proposed adjustments, connected readiness packs and approved-export authorization. No arbitrary URLs/functions/SQL or model-authored executable plans are accepted.
- Added Decimal registration-exposure arithmetic using an independently approved effective VAT rule; historical source amounts/dates must match authorized AED ledger lines. Duplicate observation IDs and multiple journal legs are rejected to avoid obvious double counting. The supplied population is not certified complete; residence, exclusions, effective registration and filing decisions remain unresolved professional questions.
- Added reviewed historical VAT difference schedules, with distinct period increases/decreases, overlap rejection and no assumed cross-period netting or automatic correction-route conclusion.
- Added monetary closing-rate FX arithmetic with explicit ISO currencies, one functional currency per schedule, reviewed classification, controlled Decimal rounding and separate unposted balance adjustments. It does not claim automated GL tie-out, realized FX or group presentation/CTA calculations.
- Added typed property transaction facts and a guard preventing unresolved property facts from being marked complete for treatment. This supports reviewed classification; it is not an automatic property-law decision engine.
- Added structured condition/criteria/cause/effect/recommendation fields for findings and a case action that requires approved records or independently reviewed engine exceptions.
- Consolidated VAT readiness/recovery assessment into `vat.service.assess_record`, shared by the specialist API and assistant adapter. The source review found the MoF MD197/2026 notice; an explicit amendment adoption/evidence gate now prevents rollout dates alone from implying current readiness.
- Added scoped connector health collection without credentials/configuration secrets, plus jurisdiction, catalogue and connector-status receipts. Source/context changes invalidate retained results instead of silently changing an approved calculation.
- Generated business workpapers inherit specialist source permissions on every read, including linked engine evidence. Generic edits cannot remove protected links or disable inheritance. A request-local cycle/depth guard prevents recursive authorization loops. Generic AML paper copying is blocked pending a qualified restricted case/document adapter.
- Active result views refresh retained freshness. Stale or inaccessible financial output is hidden, and preparing a workpaper from a stale result is blocked. The existing application action invalidation/broadcast mechanism is retained.

## Architecture and typed boundaries

`capability-matrix.json`, `.csv`, `.html` describe every case as UI → API → engine → source → approval → evidence → tests. `engine-connection-map.json` maps all 22 requested logical responsibilities to repository services; `engine-connection-map.mmd` shows their shared flow.

The UAE catalogue, registration and historical-error rules live in `backend/app/modules/jurisdictions/ae/`. Shared orchestration lives in `enterprise_ai/business.py`. General monetary arithmetic stays in `ifrs/fx.py`, rather than being duplicated as UAE tax law. Existing `RecordInput`, specialist `BODIES`, `JobInput`, `WorkflowInput`, `ToolInput`, `ToolResult`, approved engine input records and immutable calculation models remain authoritative boundaries.

Financial amounts remain Decimal/string values. Registration and historical-error schedules use a 64-digit local Decimal context. FX rounding precision is an explicit reviewed policy input. Existing specialist engines retain their own published rounding contracts. Calculations, observed facts, missing information, source confidence, assumptions, model signals and final professional conclusions are kept distinct.

The language gateway is separate. The verified browser path uses deterministic tool collection and real engines; it makes no external LLM call and needs no model credentials. Optional language explanations remain explicit, with the existing provider/disclosure controls. Source text cannot add tools, bypass permissions, execute code, post journals, send messages or submit filings.

## APIs and controlled actions

- `GET /api/v1/ai/engagements/{eid}/use-cases`: scoped catalogue, logical connections and source register.
- `GET .../use-cases/{id}/inputs`: authorized input metadata and required facts. A checklist does not assert that facts have been supplied or proved.
- `GET .../use-cases/{id}/source-records/{record_id}`: specialist-authorized source detail.
- `POST /api/v1/ai/command` with task `uae-01` through `uae-100`: create the existing immutable investigation plan. The UI advances its read-only steps automatically and can pause after the current step; every step rechecks access and prior source receipts.
- `POST .../use-cases/{id}/actions`: validated `Execute` request, explicit action, idempotency key, selected record and typed specialist payload. `GET /api/v1/ai/tools` publishes this action schema separately from read-only tools.

Actions include `calculate`, `workflow`, `registration-exposure`, `historical-vat-errors`, `fx-review`, `draft-workpaper`, `draft-finding`, `draft-evidence-request`, `draft-client-query`, `draft-review-task`, `propose-adjustment`, `prepare-readiness-pack`, and `request-approved-export`.

Calculation actions require the expected approved input kind. They call existing VAT/CT/IFRS/TP/DMTT services, preserving professional rules and source freshness. Shared reconciliations are dispatched through the existing recoverable intelligence job queue and its source-role schemas. Draft actions reuse normal record validation/ownership/reviewer controls. A proposed adjustment remains a draft; no posting endpoint is included. Export authorization requires a current independently reviewed result, and the existing download endpoint rechecks access. An export is not an accepted filing.

Idempotency is tenant/user scoped and payload checked. Retrying a changed payload or a stale source is rejected rather than silently producing another result. Existing job recovery/cancellation and period/engagement controls remain authoritative. No new business table was required: existing `AuditRecord`, revisions, `IntelligenceEvent`, `IntelligenceJob`, `Workflow` and approval models persist the work.

## Source register and legal qualification

`legal-source-register.json` records the sources actually consulted, their authority/type, URL, provision locator, available publication/effective dates, retrieval date, version and adoption status. Unknown dates are null. Existing source registries are identified separately and are not represented as comprehensively reverified.

The [FTA registration page](https://tax.gov.ae/en/taxes/Vat/vat.topics/registration.for.vat.aspx) and the [FTA-hosted consolidated Executive Regulation](https://tax.gov.ae/Datafolder/Files/Legislation/2026/Law-No-8-of-2017-and-its-amendments--09-2026.pdf) were consulted. The latter's content was checked rather than inferring its identity from the filename; it labels the English text an unofficial translation. Candidate registration parameters in the source register do not become an approved application rule automatically.

The [MoF e-invoicing portal](https://mof.gov.ae/en/about-us/initiatives/einvoicing/) and [MD197/2026 announcement](https://mof.gov.ae/en/news/ministry-of-finance-amends-electronic-invoicing-regulations-to-ease-the-burden-on-businesses/) were consulted. The identified original decision PDF could not be opened through the research tool. The announcement date is not substituted for legal commencement. Applicable original text, operative dates and professional adoption remain pending; the assessment reports `REVIEW_REQUIRED` without adoption evidence.

## Verification and remaining scope

Actual machine-readable receipts are in `evidence/` and summarized in `verification.json`. Runs overlap and are not added as unique coverage.

- All 50 entries were exercised through real PostgreSQL-backed HTTP scope, command and first collection-step paths. This checks entry/authorization/recipe behavior, not 50 complete numeric/legal acceptance scenarios.
- Lease calculations through the assistant action and specialist API were compared exactly. Reopening an input invalidated the retained action. An audit reader lacking IFRS permission could read an ordinary paper but was denied the generated IFRS-source paper; protected source removal was rejected.
- Deterministic tests cover policy-driven registration thresholds/windows, malformed/duplicate records, unresolved property facts, exact period differences, currency separation, FX arithmetic, and closed action dispatch.
- The real-browser synthetic path covers the ingestion/approved-input fixture, assistant collection, calculation, source inspection and unposted draft workpaper. Scanner and broker boundaries used by fixture preparation are documented test doubles; no live government, bank, screening, ASP or language-provider integration was claimed.

The per-case matrix deliberately retains scope limits. In particular, full scope remains **Blocked** for case 46 (unified obligation inference and preference-based notification delivery), case 48 (qualified restricted AML case/document storage and associated raw-file confidentiality), and case 49 (current amendment adoption and full certified/live e-invoicing qualification). Their supported collection/assessment workstreams remain visible with explicit blockers.

Other limitations include manual legal classifications, complete export authenticity, complex contract cut-off matching, every consolidation/acquisition/actuarial scenario, automatic sensitivity over all disputed transactions, complete semantic disclosure review, official UBO/identity verification, licensed live comparables, realized/presentation FX and automatic recomputation of every downstream engine after source changes. These are not hidden behind an app-wide compliant badge or counted as complete because a page exists.

The six-sector synthetic sources already in the repository are reusable inputs, not proof that all 50 cases have passed complete six-sector browser acceptance. Real-client data qualification, operational load/recovery acceptance and professional legal-content adoption remain release gates.

## Run and reproduce

Apply the existing Alembic head; there is no new SQL migration for these JSON-contract and adapter changes. Configure the normal private PostgreSQL, Redis, source storage, signing and scanner settings. Never enable synthetic bootstrap or test doubles in production.

Backend, from `backend`: `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.

Frontend, from `frontend`: configure `AUDITOS_API_ORIGIN=http://127.0.0.1:8000` and the exact `AUDITOS_WEB_ORIGIN=http://127.0.0.1:3000`, then `npm run dev`. The public origin must match the browser origin for CSRF protection.

Worker, from `backend`: `.venv/Scripts/celery.exe -A app.workers.celery_app:celery_app worker --pool=solo -Q celery,accounting,intelligence,enterprise-ai,grc`. Run the existing beat scheduler for enabled schedules/recovery. Source collection can also advance through the existing step API; large reconciliation/OCR jobs require the actual configured worker/broker.

Disposable verification uses `scripts/audit_gap_test_run.py`, which targets only the named `auditos_audit_gap_test` database, separate Redis DB and private object directory. Integration fixtures reset that disposable database; do not run them against a live firm or concurrently on the same test database.

For the browser receipt: run `scripts/mr_auditor_business_preview.py` through that test wrapper after integration tests, start its isolated API on port 8047 and the frontend on 3047 with matching API/public origins and `AUDITOS_NEXT_DIST_DIR=.next-mr-auditor-business`, then run `node node_modules/@playwright/test/cli.js test --config playwright.uae-business.config.ts` from `frontend`. Only synthetic IDs are saved in the private fixture; production credentials are never documented.

Rebuild artifacts with `backend/.venv/Scripts/python.exe scripts/build_mr_auditor_business_report.py`.

The four previously reported shared type errors were fixed with explicit dictionary/model annotations; current scoped typechecking is recorded in evidence/advanced-mypy.txt.


## Incremental phases 5–8: cases 51–100

All 50 new cases are **Implemented with limitations** at the bounded schedule/review level. This does not certify complete legal conclusions, all-sector acceptance, automatic extraction or live government integrations. Case 97 now also has a real original-XLSX scanner; cases 99–100 also inspect the actual authorized engagement file rather than relying only on entered counts. The 01–50 blocked scopes remain separately recorded.

`advanced_specs.py` defines 50 distinct closed row contracts. `advanced.py` validates each with a generated Pydantic model, explicit evidence IDs, reporting dates, ISO currency, approved policy/contract locator and version, effective-date coverage, assumptions and unresolved questions. Unexpected fields, nonfinite/binary-float money, duplicate references, invalid fractions, fractional counts and unsupported policy types are rejected. Tax classification cases require legislative/official-guidance adoption, rather than a firm-policy label. Periods spanning policy changes must be split. Amounts are unrounded Decimal schedule intermediates; production journals/returns retain specialist rounding and approval rules.

Store a schedule in `WorkingPaper.advanced_input` with every row/policy linked through `sources`. The normal manager/partner review chain applies. `advanced-review` accepts only the approved paper ID and no runtime amount/rule overrides. It rechecks case identity, specialist reads/calculation permissions, current approved dependencies and mutable engagement controls. Its retained result includes source/input versions, entity/period IDs, preparer, unresolved assumptions, no final professional conclusion, and no posting/sending/submission. Generated workpapers continue to inherit protected source permissions. Reviewed findings and remediation/evidence-request drafts reuse the existing actions; result review/export uses existing intelligence controls.

Incremental mathematical work includes residual VAT allocation, bad-debt candidate/recovery schedules, hospitality/gateway bridges, reviewed per-unit excise, foreign-tax credit caps, election/realization roll-forwards, asset/liability deferred-tax bridges, royalty/cash-pool arithmetic, cost-plus true-ups, segment allocations, minimum-tax movement validation, subsequent-event cut-offs, confirmation differences, unrecorded-liability candidates, provision expected values, contractual covenants, provisional acquisition/equity bridges, a bounded cash-flow valuation model, property/restatement bridges, cumulative three-way matching, count roll-forwards, trade finance, restricted cash, refunds and access conflicts. These are reviewed-input schedules, not autonomous eligibility/pricing/valuation opinions.

`workbook-integrity` (case 97) reads the original approved clean XLSX object, verifies its hash and retains the exact evidence-version receipt. It finds broken references, missing sheets, static circular formula dependencies, adjacent formula differences, hidden numeric inputs and possible hardcoded overrides. It never evaluates formulas/macros, follows external links or modifies the original. Bounds: 16 MiB compressed / 64 MiB expanded, 20 sheets, 100,000 populated cells, 5,000 formula cells and 100,000 dependency edges. Named/dynamic/structured references are not completely traversed; numeric-model recalculation remains unqualified.

`file-readiness` (cases 99–100) reuses `audit.completion` and its actual misstatement register, checks authorized file sources and stale papers, and binds the retained result to the file population and completion-policy snapshot. New/changed records, sign-offs or policy checks invalidate it. It does not select/sign an audit opinion, seal a file or execute retention.

Record-linked advanced schedules have transactional deduplicated **in-app source-change alerts** for recorded preparers, owners and review approvers. `GET .../use-cases/{id}/alerts` rechecks recipient identity and target-paper specialist permissions. Previous approved revisions are preserved. Transitive record-source paths are bounded to 100 levels / 2,000 papers; larger scans fail closed. This inbox does not send email/push. Event-only/unlinked outside-source changes and every specialist engine's automatic draft recomputation are not comprehensively implemented. Stale factual assumptions must be corrected and independently reapproved; a rerun then produces a new immutable output rather than silently changing the approved version.

The new browser flow creates a real draft input paper, executes independently approved allocation inputs and verifies AED250 recoverable / AED10 period adjustment, then checks procurement quantity exceptions. The database loop executes all 50 new approved schedules, compares exact retained outputs, tests unapproved/self-approval denials, duplicate processing, changed-payload rejection, tenant isolation, source invalidation, reviewer inbox and actual file-population invalidation. Those checks do not replace legal-content or six-sector production acceptance. The XLSX HTTP test uses an explicitly marked disposable malware-scanner boundary; the production scan gate remains enforced.

No database migration is needed: the typed optional body field, immutable event kinds and alerts use existing versioned JSONB records. Apply the existing Alembic head. This is an additive engine/API contract extension, not an unpersisted UI-only catalogue.

Exact remaining dependencies: professional adoption of applicable sector/legal rules (and post-September-2025 apportionment amendments), official excise product/laboratory data, licensed comparables/valuations, complete authorized source populations, real gateway/bank/confirmation/FTA connections, privileged legal-source qualification, complete Excel recalculation/dynamic-reference support, automated inter-engine source remapping/recalculation, and full file-assembly/retention acceptance. Each row records its narrower limitation in the matrix.

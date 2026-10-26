# Country workflows — first implementation increment

Later additions, verification receipts and remaining native-format gaps are documented in [Native adapters](native-adapters.md), including [India split withholding bank settlement](native-adapters.md#india-withholding-records-to-split-bank-settlement), [India document series and cancellation counts](native-adapters.md#india-gstr-1-document-series-and-cancellation-counts), [reviewed account links for reconciliation and settlements](native-adapters.md#reviewed-account-links-for-bank-reconciliation-and-settlements), [bank account identity and owner evidence](native-adapters.md#bank-account-identity-and-owner-evidence--uae-and-india), [GSTR-1 outward invoice/note sections](native-adapters.md#india-gstr-1-outward-invoicenote-sections), [GSTR-1 summary metric reconciliation](native-adapters.md#india-gstr-1-summary-metric-reconciliation), [GSTR-2B document import](gstr2b.md) and [reviewed payroll contribution rules](payroll-rules.md). The original twelve-workflow/142-scenario and delivery receipts below describe the first increment, rather than all subsequent workspace changes.

UAE first, then India. This increment adds twelve operational workflows and 142 named synthetic reference scenarios. It does **not** complete the entire regulatory roadmap or qualify the application for production statutory reporting.

## Consolidated browser follow-up — 25 October 2026

The current 26-test UAE/India browser campaign exercised the running API and real Redis/Celery worker after the invoice/register addition. `browser-results.json` preserves the first run: 23 passed and three timed out while selecting original fixture events outside the first loaded history page. `browser-history-intermediate-results.json` preserves the intermediate run: two passed and the combined smoke test reached its overall two-minute bound. The final `browser-history-regression-results.json` records all three affected tests passing, without a database reset between attempts. This is passing coverage across the full campaign plus a focused rerun, not a single green 26-test execution.

Source preparation and workflow forms now offer **Load older source choices** next to their action controls, reusing the same cursor history as the existing saved-event loading button. Older sources remain subject to the original review, freshness, country and role filters. The affected browser tests explicitly load the known multi-page fixture history through the UI and wait for the initial pagination state. The combined multi-operation smoke test has a five-minute overall bound; individual response and job checks retain their existing bounds. Its final execution took 3.1 minutes. The other focused flows cover both countries' credit residuals and original CSV/reviewed XLSX bank and payable sources.

`consolidated-api-regression-results.xml` records 68 passing API tests across 29 selected country-workflow and regulatory test files in 236.11 seconds. These exercise the real disposable PostgreSQL database, API, private object storage and job processor with explicit scanner/broker test doubles. `history-controls-frontend-results.xml` records 152 passing frontend tests. Production build, typecheck, scoped ESLint and source UTF-8 preflight pass. These runs remain synthetic verification. Full-return composition, amendment resolution and filing context, professionally qualified country packs, real client pilots and the existing production release gates remain open. The pilot folders and 148 labelled synthetic examples are described in [pilot-data/README.txt](../../pilot-data/README.txt).

## Implemented

- Account-level bank BRS: four opening/closing controls, an arithmetic bridge, bounded matching, unresolved amounts, candidate causes, aging and stale items. Arabic/Unicode counterparties retain distinct identities. Matching tolerance cannot hide a nonzero bridge residual.
- UAE VAT: separate document reconciliation and a VAT201 return-box bridge. Taxable amounts, tax and adjustments compare independently by registration and assigned tax period; required-but-absent boxes remain missing. Book allocations are explicit canonical inputs, not a fabricated UAE supplier portal.
- India GST: canonical invoice/credit-note/debit-note comparison, registration/component/currency separation, timing differences and rejected/pending source status. The first increment used canonical sources; subsequent work adds the bounded GSTR-2B profile linked above. Input-credit eligibility and IMS action execution remain open.
- Payroll settlement, statutory dues and Indian withholding: separate expected/book, return/channel and payment/bank populations; partial settlement aggregation, missing employee/registration/month/component partitions, declared due dates and actual payment dates. A payment source cannot extend its own expected due date.
- Inventory: item/site/UOM quantity differences, separately declared ownership and condition, count-date gaps, potential NRV write-downs and explicitly bounded monetary coverage.
- Controls, vendor diligence, nonprofit diligence and tax close: explicit subject populations and requirement scope, missing/expired evidence, documented exceptions and justified non-applicability. Country starter checklists are scope prompts, not assertions that all local law is covered.
- Country safeguards: UAE domestic workflows reject Indian statutory components; India-only reconciliation is unavailable for UAE engagements; historical TCS 206C(1H) is rejected for periods from April 2025; tax-audit form guidance requires an explicit tax-year start. An October 2026 review can still concern a legacy 2025–26 tax year.
- Controlled nil populations: an empty population requires an explicit rationale and zero controls. Missing evidence is never automatically treated as zero activity.

## Reused infrastructure

The existing intelligence jobs, tenant/engagement authorization, clean private evidence, immutable result versions, independent review, stale-input propagation, exports and working-paper dependency graph remain the system of record. No new database tables or migration are introduced by this increment; the checkout's existing migrations still need to be applied.

Bank books can come directly from a committed GL/journal snapshot, selecting one account, explicit date range and functional currency. Opening postings are excluded from movement. Trial-balance-only snapshots cannot establish a transaction population. The source retains snapshot and original source-record links. Other source types currently use the documented canonical UTF-8 CSV contracts.

## Use the workflows

1. Open Accounting Intelligence, select an engagement and choose **Country workflows**.
2. Choose **Prepare sources**. Select retained clean CSV evidence, declare its row count and currency totals, or select **Committed bank ledger**. The field contract and CSV header download describe the selected source type. Examples are in `sample-inputs/` and are synthetic only.
3. Independently review each prepared source. Approval creates a new immutable source version; select that reviewed version for downstream work.
4. Choose **Run workflows**, select independent sources, the reconciliation date and the explicit scope/controls. VAT201 requires required-box scope; diligence requires both a subject population and requirement list.
5. Open a completed job, investigate exceptions and document their dispositions. Balance-control failures, expired evidence and missing mandatory checks require correction and regeneration. An independent authorized reviewer approves the result. Sources changed after preparation make dependent results stale.
6. Export XLSX or use the existing working-paper actions. Exports preserve source receipts, unqualified statutory status, limitations and review state. Working-paper generation requires a reviewed current result and still produces a draft for actual audit procedures and conclusions.

The source/result picker starts with the latest 100 events and offers cursor-based loading of older sources/results. Jobs show the latest 50, and result rows paginate by 100. XLSX includes the full bounded result. Each uploaded source is limited to 5,000 rows and 10 MiB; no unbounded performance claim is made.

## Coverage evidence

- `scenario-matrix.json`: every named scenario, workflow, country exercised and expected behavior. The same fixtures execute through CSV parsing, typed input validation and deterministic calculations. This is 142 operational scenarios, not 142 independently qualified laws or integrations.
- `unit-results.xml`: backend unit-suite receipt.
- `integration-results.xml`: real PostgreSQL/HTTP/private-object/job execution, source review, independent approval, quarantine, identical-content rejection, country boundaries, exports, lineage, native ledger extraction and staleness regressions.
- `frontend-results.json`: frontend suite receipt.
- `browser-results.json` and `screenshots/`: real UI flows, country isolation, VAT201/GST review, export and browser-to-Redis-to-Celery result publication.
- `performance.json`: synthetic in-process matching only; excludes database, parsing, queueing and worst-case ambiguous populations.
- `delivery.json`: scope, remaining gaps and verified counts, generated from the receipts.

Verification uses the separately named, disposable `auditos_country_workflows_test` database, private local objects and Redis database 10. Integration tests use explicit scanner and broker-dispatch test doubles; they do not establish malware scanner qualification. Browser fixture preparation uses the same clearly marked synthetic scanner double. The final browser queue check uses a real Redis/Celery worker and the retained synthetic evidence.

## Repeat verification

From the repository root, using the existing local QA secrets:

```powershell
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py prepare
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py .venv/Scripts/python.exe -m pytest tests/qa_crud/test_country_workflows.py tests/qa_crud/test_accounting_intelligence.py tests/qa_crud/test_regulatory_workflows.py tests/qa_crud/test_statutory_reporting.py -q
backend/.venv/Scripts/python.exe scripts/country_workflows_catalogue.py
backend/.venv/Scripts/python.exe scripts/country_workflows_benchmark.py
```

Run the backend unit suite from `backend`, not the repository root. Run frontend lint, typecheck, tests and build from `frontend`. Browser verification uses `playwright.country-workflows.config.ts`, API port 58014, web port 3010 and a worker consuming `intelligence` in the isolated environment. `country_workflows_preview.py` resets only the owned disposable test database and prepares synthetic fixtures; run it only after integration tests, never against demo or live data.

## Gaps that remain

Priority order remains UAE followed by India:

1. Qualify native UAE bank formats and VAT201/customs adapters, WPS/SIF schemas, employment/pension cohorts and end-of-service calculations. Extend existing UAE VAT/CT/IFRS engines rather than maintaining duplicate tax arithmetic.
2. Add native, versioned India GSTR/IMS, 26AS/AIS/TRACES and withholding return adapters, then ECR/ESIC/state PT. Rates, ceilings, membership, certificates, exemptions and calendars require approved source-bound rule versions and independent professional expected results.
3. Complete legacy/current Indian tax-audit form mappings, Companies Act/CARO/IFC and country reporting packs using the existing regulatory library and statutory report composer. A tax-close checklist is not a complete tax-audit engine.
4. Add live authorized registries, sanctions/PEP providers and beneficial-owner resolution. Uploaded declarations are not live verification; professional attestation, physical stock attendance and insurance are not supplied by software generation.
5. Qualify representative consented client pilots and close the existing hosted security, recovery, operations and professional release gates. Synthetic success is not production certification.

All original 13 reference use cases map to these workflows or the existing statutory/GRC/reporting infrastructure. Complete legal parity remains explicitly open in the roadmap; no previously planned India module is silently relabeled as qualified.


Shared bank cash approval now checks active obligation allocation reviews across the same legal entity’s engagements within the current firm, for UAE and India. Conflicting reviews block approval; explicit independent withdrawal appends a release while preserving the earlier approval, including when its source has become stale. See [shared cash approval scope and limits](native-adapters.md#shared-bank-cash-approval-controls-uae-and-india). See [entity scope, access boundaries and historical claims](native-adapters.md#bank-cash-capacity-across-a-legal-entitys-engagements). Cross-entity bank ownership and independently checked client pilots remain open.


Retained-history listing now reuses bounded request-local read metadata while preserving recursive access and freshness checks. The 100-row UAE/India paired benchmark returned identical JSON with about 85–86% fewer SQL queries; this is synthetic local evidence, not production capacity qualification. See [implementation, measurements and repeat command](native-adapters.md#retained-history-request-reuse--uae-then-india).


XLSX exports now preserve oversized source/control values in ordered continuation records and show all bank cash manifest movements on a dedicated sheet. Download checksums bind the saved bytes to the export audit record. See [complete-text export behavior and bounds](native-adapters.md#complete-text-in-uae-and-india-reconciliation-xlsx-exports).

# Native source adapters and VAT engine bridge

Implementation checkpoint: 25 October 2026. These additions extend the existing evidence, intelligence job, immutable event, review and lineage infrastructure.

## Current combined regression

The current combined receipt now records **12 passing browser tests in 7.8
minutes**, after fresh guarded fixture preparation. It includes retained-source
publication in both countries, obligation/bank allocations, currency conversion,
subsequent clearance, import VAT/VAT201, history, PDF, credit applications,
withholding, native sources and CSV/XLSX bridges. This supersedes the intermediate
11-pass/one-picker-timeout run. The picker now has an explicit accessible name;
the focused publication flow also passed before the clean combined rerun.
Use fresh fixture preparation for each full campaign rather than accumulating
results across repeated campaigns; the dedicated history test separately retains
its deliberate population beyond 100 events. Earlier checkpoints below are
historical and their counts must not be summed.

After refreshing the isolated API and intelligence worker and preparing fresh guarded
fixtures, `browser-results.json` records **10 passing browser tests in 6.1 minutes**.
This supersedes the earlier eight-pass/two-timeout run. Existing test timeouts were
unchanged. The combined run exercises reviewed UAE/India currency conversions and
rule assessments, subsequent bank clearance, the selected VAT201 import bridge,
import-VAT version decisions, history beyond 100 events, PDF bank extraction,
credit applications, India withholding roles, native-source controls and exports,
and CSV/XLSX bank and payable bridges through the real worker.

Country implementation hashing now takes one snapshot per active database
transaction. Each new transaction recomputes it; sessions without an active
transaction do not cache it. This avoids repeatedly reading the same implementation
files while checking a history page. Entity, period, currency, source version,
document integrity and dependency freshness checks still run. The API regression
in `history-freshness-integration-results.xml` proves that a subsequent request
recomputes the fingerprint and detects a simulated rollout; its six passing cases
also include bank-clearance and supporting-bank lineage regressions.

The pre-CAMT checkpoint recorded **1,176 passing backend unit tests and four
skips** for opt-in connector database tests. Those four connector cases passed
separately against their disposable database and Redis namespace. The retained
frontend receipt records 111 passes. These checks verify the exercised synthetic
workflows, not representative provider exports, live government integrations,
qualified legal packs or completion of the full original roadmap. Older counts
below describe their historical checkpoints and must not be added together.

## Single-file CAMT statement pagination

`camt053-2` now accepts complete statement-page chains within one retained XML
document. The profile follows [SWIFT CGI-MP v1.6, pages 49–55](https://www.swift.com/swift-resource/252088/download).
Selection uses the statement ID and account; different statements remain distinct.
Pages must be ordered from one, share their electronic/legal sequence and currency,
and mark only the final page as last. Opening and closing interim subtypes and
amount/date carry-forward are checked. Each page balances independently, including
empty intermediate pages; aggregate opening plus entries must equal final closing.
The first-page count controls the whole statement. Reported gross, net and
credit/debit summary controls are checked against all entries. Repeated summary
groups on later pages and duplicate control fields are rejected.

Rows preserve physical statement position, logical page, original page row and
global row. Page receipts retain both balances, dates, subtypes and entry totals;
the review screen exposes a compact table and all fields. XLSX exports retain
every page in a separate **CAMT page controls** sheet. Booked entry amounts remain
the transaction grain; detail amounts are not added again. The original XML is
retained unchanged. Complete single-page imports remain supported.

The fictional [three-page sample](sample-inputs/SYNTHETIC-camt-statement-pages.xml)
uses account `BANK-1`, statement `SYNTHETIC-STMT`, two booked entries and an
independent control of `AED=95`. Its middle page is intentionally empty and still
participates in balance carry-forward. It is an arithmetic example, not bank evidence.

`camt-pages-unit-results.xml` records 111 overlapping targeted passing tests,
including three currencies, broken chains, controls, explicit statement selection,
the 100-page bound, XLSX, existing native readers and implementation guards.
`camt-pages-integration-results.xml` records four passing UAE/India CAMT and MT940
API cases: original-file download, maker/checker separation, independently reviewed
cashbook reconciliation, XLSX controls and source-replacement staleness. Scanner
and broker boundaries are explicit test doubles in those API cases.
`camt-pages-frontend-results.xml` records 112 passing frontend tests. The updated
full backend receipt records 1,210 passes and four opt-in connector skips. Scoped
Python typing, lint, frontend type checks and UTF-8 preflight pass.

This adds single-file statement-page assembly. Separate XML files, message-level
pagination, provider export qualification and bank identity authentication remain
open. The earlier ten-test browser receipt predates this CAMT addition.
The updated native-source browser test passes in one minute against the refreshed
API and real Redis/Celery worker (`camt-pages-browser-results.txt`). It imports the
three-page sample through the source form and asserts all three page controls.
The captured `screenshots/native-sources/camt053-statement-page-controls.png` was
visually inspected: all columns and the empty middle page's carry-forward are readable.
This focused run also retains the native bank, payroll, tax, export and country
isolation assertions; it does not replace the earlier full ten-test checkpoint.

## Supported profiles

- **Retained regulatory reference copies:** the firm rule library now keeps its
  public reference material separately from client evidence. `POST /regulatory/sources`
  accepts a bounded PDF/UTF-8 text copy and explicit title, country or GLOBAL,
  source HTTPS URL and retrieval date. It reuses private versioned object storage,
  quotas, structural validation, malware scanning, firm permissions and audit logs.
  A source copy is usable only after a CLEAN scan; scanner failures/rejections do
  not create usable copies. Source records are immutable and tenant-isolated.
  List/download responses omit private object-store keys; download verifies the
  retained bytes and uses attachment/sandbox headers.

  Every citation needs `source_document_id` before independent approval or
  publication. The retained copy's jurisdiction, URL, retrieval date and SHA-256
  must agree with the citation; an entered hash alone no longer qualifies a rule.
  Copies scoped GLOBAL may support several country rules. The proposer and any
  cited source uploader cannot independently approve the rule. Publication remains
  an authorized firm-administrator action after independent approval. Approval and
  publication retain the verified-copy receipts in their append-only actions.
  Binding a copy does not set technical validation or professional review flags.

  Rule selection rechecks retained-file integrity. A damaged/missing source blocks
  new assessments and makes dependent historical assessments stale while preserving
  their original result and checksum. Successful verification is cached only for
  the active database transaction; a new transaction rechecks the bytes. Individual
  copies are limited to 10 MiB and verification to 100 MiB per transaction; limits
  fail explicitly rather than omitting sources. Uploaded bytes do not authenticate
  an official URL or establish correct legal interpretation/applicability.

  Migration `0021` adds the source table, RLS and immutable-history trigger; the
  readiness contract now requires that migration. The existing-environment upgrade
  was applied only to the owned disposable country-workflow database. Existing published
  rules without retained copies remain historical records and require an amended
  proposal with source bindings before new qualified use. No legal rule content is
  silently rewritten or auto-published.

  `regulatory-sources-integration-results.xml` records 14 passing database/API cases
  covering source integrity, citation mismatches, tenant isolation, immutable history,
  source-uploader separation, failed scans, downstream staleness, currency conversion,
  rule versioning, specialist reporting and the foundation workflow. Scanner/queue
  boundaries are explicit doubles where used; copied text/rates are synthetic.
  The latest full unit receipt records 1,247 passes and four opt-in connector skips.
  A separate disposable-database run passed those four connector cases through the
  new migration. `regulatory-sources-frontend-results.xml` records 118 passes,
  including upload metadata, bounded source pagination and attaching a specific
  citation without granting content approval. Scoped typing, lint and UTF-8 checks
  and the production frontend build pass. `browser-results.json` records the
  complete 12-test passing campaign.
  `regulatory-sources-browser-results.txt` preserves the focused publication run;
  `ae-retained-source-rule-publication.png` and
  `in-retained-source-rule-publication.png` were visually inspected. The legacy
  regulatory browser fixture now retains a scanned copy instead
  of supplying a fictitious hash; running that separate environment requires its
  migration and operational scanner rather than bypassing either gate.

- **Obligation / reported amount / bank allocations:** the shared
  `obligation-bank-allocations` workflow is enabled for UAE and India. It compares
  independently reviewed expected obligations and reported instructions/returns
  with retained bank transaction rows through an independently reviewed allocation
  source. A single bank debit can cover several employees, months and components;
  an obligation can have several partial payments. Each link must name the exact
  expected, reported and bank row, currency, amount and evidence assessment.
  Registration, subject, month and component must agree. Allocations cannot exceed
  any obligation, reported amount or bank movement. Repeated links and overlapping
  corrected obligation identities are rejected. Inflows are retained separately and
  cannot net against salary/dues payments; reversals need assessed restatement.

  The user declares an obligation-month range, bank account/currency, settlement
  window and payment sign. Native CAMT/MT940 outflows use debit-negative amounts.
  Missing expected months remain missing, rather than being treated as zero.
  Expected-source due dates drive the timing comparison; absent/conflicting due
  dates, late settlements and overdue residuals remain visible. Due dates and
  liabilities are not legally inferred. WPS/ECR imports can establish the reported
  role only. UAE domestic PF/ESI/PT/TDS/TCS components remain excluded; historical
  India 206C(1H) cannot create new obligations from April 2025. A current payment
  against a valid historical obligation remains a separate matter.

  The review screen has compact source/settled/remaining columns, aggregate residual
  controls and an explicit provenance expansion. Exact original fields and allocation
  details remain in the saved result and XLSX. Late-payment exceptions must be
  documented before independent approval; documenting an exception does not remove
  the late amount or establish legal compliance. This does not reconcile the GL,
  prove beneficiary/bank ownership, determine employment-register completeness,
  qualify legal rates/deadlines or authenticate a government filing/challan.

  `dues-allocation-integration-results.xml` records seven passing database/API cases:
  native UAE SIF and India monthly ECR with separate expected registers and bank
  movements, mandatory source review, pooled/partial settlement, documented late
  payments, maker/checker separation, export and source-replacement staleness,
  plus existing monthly ECR and bank-clearance regressions. Scanner and broker
  boundaries are explicit doubles; API, object storage, DB and processor are real.
  The due dates in these examples are fictional, not legal deadlines.
  The latest full unit receipt records 1,242 passes and four opt-in connector skips;
  `dues-allocation-frontend-results.xml` records all 114 frontend tests passing.
  The executable catalogue now has 148 synthetic operational cases, including six
  added allocation scenarios. These counts overlap and are not client qualifications.
  The export regression checks the exact late amount, allocation IDs and residual
  controls in the XLSX, rather than only its HTTP status.

  `dues-allocation-browser-results.txt` records the real-worker browser flow for
  both countries: reviewed-only source selection, explicit scope/sign, pooled bank
  allocations, a documented late-payment exception and a separate final approver.
  It also asserts that the compact table fits its container and the first column
  is fully visible. The four `ae/in-obligation-bank-allocations.png` and
  `ae/in-obligation-allocation-controls.png` screenshots were inspected; all rows,
  columns and residual controls are readable. Notifications are dismissed through
  their normal UI button. The native-source browser regression also passed in the
  preceding combined run. The earlier ten-test full browser receipt remains a
  historical checkpoint. Production frontend build, type checks, scoped lint and
  UTF-8 preflight pass for this increment.

- Explicit regulatory-base currency conversion now reuses a current independently reviewed lead and a separately reviewed `fx-rates` source. Rate rows declare a recognized direct currency pair, positive decimal rate, closing/period-average/assessed method, rate date and coverage, retained quote version/hash/URL and an applicability assessment. The source-import document picker can bind blank quote IDs/hashes; conflicting references, superseded documents and failed file integrity are rejected, and quote uploaders remain contributors for independent review. Rate rows use independent row counts and document provenance, not a money-total control. Closing quotes must identify the reporting date exactly; other methods must cover the whole reporting period.

  `POST /regulatory/engagements/{eid}/conversions` requires explicit decimal places, rounding and an independently declared converted amount that must agree exactly. The result preserves original currency/amount, direct rate, unrounded amount, rounded result, policy assessment and source/quote dependencies. It requires independent review. A subsequent rule assessment may name that reviewed conversion while retaining its original source schedule. Functional currency remains the entity's currency; `tax_base_currency` comes from the selected reviewed conversion. The target amount must agree exactly and the conversion must originate from that source. There is no inferred reciprocal, triangulation, legal rate policy, market retrieval, posting or filing. Original quote replacement propagates staleness through conversion and assessment.

  The form includes explicit preparation/review links, named conversions, reviewed-only selection, older source-history loading and quote-row pagination with selection retained across pages. `regulatory-conversion-unit-results.xml` records 209 targeted passing tests; `regulatory-conversion-integration-results.xml` records four API cases covering UAE/AED, India/INR and UAE/USD, quote binding, maker/checker, pre-review rejection, converted controls, downstream rule use and replacement staleness, plus existing publication/versioning regression. These quotes and rates are synthetic arithmetic fixtures. `regulatory-conversion-frontend-results.xml` records all 111 frontend tests passing. Production build, scoped type checks and lint pass. The focused browser flow now passes for both UAE and India; details and screenshots are recorded below. The earlier full-suite receipt predates this increment.

- Regulatory rate currency controls: a flat-rate rule now declares a recognized ISO `calculation_currency` before independent approval/publication. Both applicability assessments and specialist checklists bind `functional_currency` from the actual entity, alongside the existing authoritative country/framework/period facts; a submitted contradiction is rejected. The rate-assessment endpoint requires a current independently reviewed lead schedule and an exact base amount in the declared currency. Results retain that currency. Mismatched currencies require the separately evidenced and independently reviewed conversion workflow described above. UAE entities are not forced to AED: a UAE/USD entity can assess a USD-denominated rule. The rule picker displays each declared currency and disables legacy unspecified-currency rates until amendment/review. Repeated rule-version selections and unknown currency codes are rejected. Regulatory schema/evaluation/service files are now included in the legacy operation implementation guard so changes invalidate affected saved assessments.

  `regulatory-currency-unit-results.xml`: 34 passing targeted currency, regulatory evaluation and implementation-scope tests. `regulatory-currency-integration-results.xml`: four passing API cases, including real committed-ledger/reviewed-lead assessments for UAE/AED, India/INR and UAE/USD, rejected unspecified-currency rule approval, rejected currency substitutions/mismatches and repeated rule IDs, plus the existing rule publication/versioning regression. Rates and source attestations in these disposable tests are explicitly synthetic; these are not legal tax-rate qualification receipts. `regulatory-currency-frontend-results.xml`: all 107 frontend tests pass, including declared/legacy currency choice behavior. Frontend and scoped backend type checking, scoped lint and UTF-8 checks pass. Browser verification of the new regulatory currency flow remains open.

- Country-workflow implementation freshness now uses the server-defined `country-workflows/1` scope in `audit-operations/2` receipts for both `workflow-source` and `country-workflow` events. It fingerprints every Python/JSON file under the country-workflow and VAT modules, including future readers/calculators, plus the shared JSON/document/XLSX readers, matching, reconciliation balance reader, IFRS calculations/schemas, authorization, lineage, jurisdiction context and bridge API code. Relevant installed library versions are included. Saved receipts cannot choose file paths, substitute a supporting-table scope or relabel their event kind. Existing version-1 receipts retain their legacy global comparison and are not silently promoted. Source and result reuse therefore requires regeneration/review when the guarded implementation changes. Supporting-table receipts retain their separate existing scope.

  `country-implementation-unit-results.xml` records 290 passing targeted tests, including module addition/change/removal, nested JSON changes, shared reader changes, library versions, scope/kind substitution rejection and entity-currency checks. `country-implementation-integration-results.xml` records five API cases: UAE/India retained clearance/bridge workflows become stale under an implementation rollout, reuse is denied, the unchanged implementation restores current status, upstream source rejection still propagates, and supporting-table scope isolation remains intact. Scanner/dispatch doubles remain explicit. A freshly seeded focused UAE/India BRS-clearance browser run also passed after the new scope was introduced; the nine-test full browser receipt below predates this freshness hardening. Further browser work requires fresh fixtures under the complete country fingerprint. Scoped backend type checking and lint pass.

- Subsequent bank clearance (`bank-subsequent-clearance`), shared across countries: retain independent `bank-outstanding`, later statement `transactions` and explicit `bank-clearances` CSV schedules. The outstanding schema records account, currency, original date/reference, reporting balance date, signed amount and evidence reference. Allocations record outstanding/transaction IDs, currency, positive allocation amount, evidence reference and rationale. Declare one account/currency, reporting date and review-through date. Each imported schedule needs row counts and independent currency totals; outstanding totals are signed, allocation totals positive. Later statement entries must fall strictly after reporting date and within the review window. Same-account/currency/direction allocations may split across entries or outstanding items but cannot exceed either side. Duplicate outstanding reference/date/amount populations and repeated allocation pairs are rejected. Reporting-date amounts remain unchanged; partial/not-cleared items and unallocated later movements remain review exceptions. No automatic reference-only clearance, BRS restatement, journal posting or payment execution occurs. Native bank sources can supply the later transaction role, subject to the same date/scope checks. A current independently reviewed BRS can now supply explicitly selected book-side exceptions through `bank-outstanding-source`. The preparer selects exception IDs and declares an independent row count, signed total and scope assessment. Both retained BRS source schedules must already be independently reviewed. The bridge reconstructs original book dates, references and signed amounts, retains BRS/source row links and candidate cause/disposition, and requires independent review again. Statement-side exceptions cannot become outstanding book items. The interface retains selections across result pages, separately for each selected parent result. The focused browser flow passes for both UAE/AED and India/INR using the actual form, independent source/final reviewer and real Redis/Celery calculation. Visually inspected `ae-subsequent-bank-clearance.png` and `in-subsequent-bank-clearance.png` show the reviewed status, original -100 reporting amount, 100 subsequently cleared and zero residual. Compact balances are visible by default; the provenance toggle retains all allocation details.

  `bank-clearance-unit-results.xml` records 238 passing shared/country/credit/clearance/bridge regression tests. `bank-clearance-integration-results.xml` records four UAE/AED and India/INR cases covering retained CSV schedules, preparer approval rejection, independent source/final reviews, exact original/residual amounts, XLSX export and rejected out-of-window clearance. The BRS reuse cases additionally verify rejected premature derivation, original source row linkage, independent controls, downstream clearance and recursive staleness after an upstream book source is rejected. Scanner and queue dispatch use explicit doubles; jobs execute through the real processor. `bank-clearance-frontend-results.xml` records all 106 frontend tests passing, including 37 workflow component tests for both currency payloads, explicit book-only selection and independent bridge controls. Production build, frontend/scoped backend type checking and scoped lint pass. These overlapping verification counts must not be summed.

- [UAE import VAT detail review](uae-import-vat.md): customs/portal/books comparison with separate taxable-base/tax controls, current-version resolution and distinct declaration/adjustment populations. Reviewed selected populations can now feed the books side of VAT201 box comparison with independent controls and review. Native customs/EmaraTax qualification and whole-return composition remain open.

- [Value-only XLSX supporting schedules](supporting-spreadsheets.md): reuse the shared guarded workbook reader with explicit worksheet scope, original numeric decimals, date-epoch receipts and physical row links. Independently reviewed schedules can feed the existing bank/open-item bridges without rewriting the original evidence.

- [Reviewed supporting bank-table bridge](supporting-bank-bridge.md): reuse current independently reviewed bank rows with original evidence, row links, new independent controls and propagated staleness. Explicit PDF text grids are supported as described below; provider and OCR qualification remains open.
- [Reviewed supporting open-item bridge](supporting-open-items-bridge.md): reuse receivable/payable schedules with explicit side, balance date and sign convention; retain invoice/credit-note/debit-note classification, due dates, segments and original balances for existing shared audit workflows.

- [Original CSV column mapping](csv-column-mapping.md): explicit field-to-header mapping and declared exclusions, with original evidence retained. This extends canonical sources across shared and country workflows; it is not a qualified bank or government-format adapter and performs no amount/date conversion.

- India GSTR-2B v1.0 JSON: explicit provider document-total and item-sum profiles, recipient/month/document controls, four signed tax-component rows per document, source review flags and unresolved amendment versions. Partial responses and unknown sections fail the import. [Supported fields, workflow, verification and limits](gstr2b.md). This is a document comparison source, not an eligible-ITC calculation or authenticated GST retrieval.

- India monthly EPFO ECR: eleven `#~#` separated fields, with an independently declared establishment, wage month, member count and currency total. Three contribution rows per member retain employee PF, employer EPS and employer PF. Non-zero advance refunds produce a separate fourth row. Controls include those three contributions plus refunds; insurance/administration charges, interest, damages and arrear returns are outside this file profile. Due dates are explicit inputs. Neither a return upload nor a matching amount proves portal filing or payment execution. Rates, exemptions, membership and pension ceilings are not calculated by this reader.

- India INV-01 1.1 JSON: plain invoice objects or a bounded array, with explicit entity GSTIN, purchase/sale direction and reporting month. Invoices, credit notes and debit notes retain signed tax components, reverse-charge flags and document controls. Five component rows are emitted per document, including zero components; declared INR controls are signed tax totals. Assessable value repeats per component and must not be summed across those rows. Item-to-header assessable amounts, component taxes and invoice totals are checked. Rate correctness, IRP authenticity, cancellation/portal status, eligibility, GSTIN registry validity and the full IRP submission schema are not verified. Signed/encrypted wrappers and unregistered/export-buyer profiles require separate adapters.

- CAMT.053: namespace versions 02, 04, 08–13, booked account entries, one complete selected statement. Original opening/closing balances, currency, account, references and dates remain attached. Nested transaction details are not counted twice. Incomplete paginated statements are rejected.
- SWIFT MT940 reader version 2: one complete statement across up to 100 explicitly sequenced messages, including reversal direction and year rollover. Raw concatenated messages and bounded MT940 FIN envelopes are supported. The reader requires contiguous page numbers, one statement number, matching accounts/currencies, first 60F/final 62F, intermediate 60M/62M and exact amount/date carry-forward. Every page and the assembled statement must balance. Multiple independent statements require separate source preparation. Optional reference cross-checking uses the first logical message's Tag 20. Available balances and closing information remain separate from booked entries. Original field/message positions and every message's controls are retained, including a dedicated XLSX controls sheet. Synthetic UAE/AED and India/INR tests cover both envelope forms; this does not establish bank-provider or transport-authentication qualification.
- UAE WPS SIF: the explicit ten-field EDR/SCR profile, employee records followed by one employer trailer. Filename, employer, employee, account, routing, period, count and amount controls are checked. A SIF instruction never proves payment execution. Other bank-specific variants require additional adapters.
- Existing UAE VAT201 engine: current, reconciled calculations become `return-boxes` sources without re-keying or recalculating VAT rates. Reviewed manual tax adjustments remain separate from base tax. Calculation dependencies propagate staleness; filed-return evidence must still be imported independently. Aggregate box 1 does not establish an emirate-level comparison.

Uploads remain subject to clean retained evidence, private storage, hash verification, explicit external row/amount controls and independent source review. Structured uploads are bounded to 10 MiB and 5,000 rows. XML uses entity/DTD protection. Native parsing verifies file consistency, not account ownership or legal compliance.

Native WPS/ECR sources are restricted to return/channel/reported roles. They cannot establish independently expected payroll/dues or a bank/payment population. Payroll registers, reviewed contribution calculations and payment allocations require separate evidence. This restriction is enforced when calculating queued jobs, including direct API submissions, rather than relying on a warning in the source description.

The source picker uses native-format metadata from the event listing to omit WPS/ECR sources from incompatible roles and explains the separate-evidence requirement. Canonical schedules remain selectable; their classification and payment support still require independent source review. The backend independently rejects incompatible native sources even if a caller bypasses the picker.

The results screen exposes original source controls and calculation basis. Available formats are country gated; WPS and the VAT bridge require a UAE engagement. Access to the VAT bridge also requires VAT read permission, including when its results are consumed downstream.

## Verification receipts

Browser verification was refreshed after the CSV, supporting-table, credit-application and withholding extensions. `browser-results.json` records four passing suites against the isolated API and real Redis/Celery worker. The original UAE/India suite covers country isolation, native imports, VAT/GST and reviewed payroll comparison. The supporting-table suite queues XLSX preparation, explicit debit/credit CSV mapping, reviewed XLSX bank reuse, two independent cashbook reconciliations and the payable sign/control-account bridge. The credit suite queues applications for both UAE/AED and India/INR, checking visible invoice residuals, unapplied credits and independent GL controls. The withholding suite verifies domestic India isolation, explicit legal roles, assessed superseded observations, displayed differences, source provenance and export. Source approvals are prepared independently in the synthetic fixture; browser jobs themselves use the real broker and worker. Scanner qualification and client pilots remain outside this verification.

Seven supporting-table screenshots in `screenshots/native-sources/` capture the relevant review panels: `xlsx-table-worker-review.png`, `mapped-debit-credit-worker-review.png`, `reviewed-xlsx-bank-source.png`, `mapped-bank-reconciliation-worker.png`, `xlsx-bank-reconciliation-worker.png`, `reviewed-xlsx-payable-sign-source.png` and `reviewed-xlsx-payable-control-worker.png`. Source and result panels are captured directly so result rows are not omitted below the viewport. If Windows locks an existing image, the writer retries only the file operation, then preserves a timestamped copy and attaches its actual path to the browser report. The current full frontend suite records 81 passing tests in `withholding-assessment-frontend-results.xml`; production build, frontend type checking and scoped lint pass at this checkpoint.

Browser verification also fixed stale supporting-table result choices: the result picker now refreshes and requests the latest 100 events. Job histories show the latest five entries initially with an explicit expansion control. This changes presentation, not stored history, source review or calculation results. Supporting-table layout receipts occupy their own panel rather than competing with export/review actions in a horizontal toolbar.

Country workflows now use the existing accounting-workspace table styling, including cell padding and row boundaries. Bank/open-item source views prioritize readable balances, dates, references and sign information; **Show source provenance and all columns** exposes the complete retained row fields. The compact view changes no exported values or review data.

Fixture preparation records the backend implementation fingerprint and rejects implementation changes during seeding. Browser preflight/teardown verify that fingerprint, so changed code cannot silently turn reviewed fixture sources stale mid-run. A read-only UTF-8 source preflight also detects invalid source encodings before the browser waits on an unavailable application. This preserves the existing staleness safeguards rather than bypassing them for tests. Repeat the guarded fixture preparation after backend implementation changes.

Earlier shared audit regression: [Operating calendars](operating-calendars.md) documents explicit population calendars and isolation between repeated analytics evaluations. Its recorded broad backend run passed 928 tests with 259 environment-dependent skips; its frontend run passed 62 tests. Its separately executed combined country database/API suite passed 21 tests, including the retained calendar, native sources, rule review, benefit cohorts, reconciliation, export and staleness paths. Later CSV/table-reader verification receipts are described in the linked guides above. These are overlapping suites and their counts must not be summed. These receipts do not establish live integrations, professional country rule qualification or completion of the original roadmap.

Latest native checkpoint:

- Regulatory conversion browser checkpoint: `reviewed currency conversions feed scoped UAE and India rule assessments` passes after fresh fixture preparation under the complete country implementation fingerprint. The browser selects the normal working country in Settings, selects its authorized engagement, prepares an explicitly assessed conversion from reviewed source/rate inputs, independently approves it, uses it in a published synthetic rule assessment, and independently approves the result. The working-country preference is restored to UAE. Engagement-directory country filters remain intact. The compliance heading and assessment rule query resolve country from the selected engagement, rather than assuming the global preference is its legal country. A component test covers an India engagement under a UAE global preference.

  Visually inspected screenshots: `ae-reviewed-currency-conversion.png`, `in-reviewed-currency-conversion.png`, `ae-converted-rule-assessment.png`, `in-converted-rule-assessment.png` in `screenshots/native-sources/`. The conversion views show preserved original amounts, declared direct rate, unrounded amount, independently controlled converted amount and explicit rounding. Assessment views show country-specific rule keys and period starts, calculation currency, tax base, applied rate and unrounded calculated amount as readable primary columns. Full original calculation/provenance fields remain available under the normal toggle. Notifications are dismissed through their actual UI control before capture. The rates are explicitly synthetic verification inputs. All 111 frontend tests, production build, type checking and scoped lint pass. The focused run preserves the earlier nine-test `browser-results.json`; that full-suite receipt has not yet been refreshed for this increment.

- Full browser regression after subsequent-clearance reuse: `browser-results.json` records **nine passing tests** against the isolated API and real Redis/Celery worker. This includes UAE/India reviewed BRS → independently reviewed outstanding source → later clearance, selected VAT201 scope, unresolved import versions, history beyond 100 events, both PDF grids, credit applications, India withholding, native imports (including multipart MT940 in both currencies), and CSV/XLSX bank/payable bridges. Source/scanner fixture qualifications remain as described above. All 106 frontend tests and the production build pass at this checkpoint; dedicated clearance screenshots were visually inspected after requiring the new reviewed event version to finish loading.

- Multipart MT940 browser checkpoint: the focused `UAE source controls, BRS exceptions, exports and India isolation` test passes with both UAE/AED and India/INR three-message FIN imports through the real API/Redis/Celery worker. It fills the first-message reference cross-check, checks four table rows (header plus three messages), and retains the empty intermediate page. Visually inspected `swift-mt940-ae-message-controls.png` and `swift-mt940-in-message-controls.png` show 60F/62M, 60M/62M and 60M/62F with balances 0 → 100 → 100 → 95 and entry counts 1/0/1. Full source receipts remain accessible below the compact table. `mt940-pages-unit-results.xml` records 59 focused passing tests, including the 100-message bound and all 100 XLSX message controls. This focused browser rerun does not replace the existing full-suite `browser-results.json` receipt.

- `mt940-pages-integration-results.xml`: two passing retained-file/API cases, UAE/AED and India/INR. Each verifies a three-message FIN statement with an empty intermediate page, original byte download, preparer approval rejection, independent source review, separately retained/reviewed cashbook reconciliation, final review, all message controls in XLSX and recursive staleness after original replacement. Scanner and queue dispatch are explicit test doubles; jobs run through the real processor. Bank-provider qualification remains open; focused multipart browser verification is described above. These cases supplement the 59 focused native/message/export unit tests and 34 workflow component tests; suite counts overlap and are not cumulative.

- `native-role-picker-integration-results.xml`: retained ECR format is present in the real event listing; the same integration verifies successful reconciliation and rejected source-role substitutions. Thirteen workflow component tests, frontend type checking and scoped frontend lint pass for the picker change.

- `native-role-unit-results.xml`: 242 targeted tests, including WPS channel acceptance and rejection of payroll/bank substitution.
- `native-role-integration-results.xml`: five database/API tests, including successful ECR reconciliation and rejected ECR substitutions for expected dues and payments. These focused receipts supplement the broader checkpoint below; counts overlap and must not be added together.

- `native-india-regression-results.xml`: 396 backend tests across reconciliation, shared audit, practice, sector, diligence and native/calculation sources.
- `native-country-integration-results.xml`: sixteen database/API integration tests across country workflows, native files and calculation bridges.
- `india-gstr2b-integration-results.xml`: two database/API tests for retained JSON, independent source review, document reconciliation, original download, export and rejection of partial provider responses.
- `india-ecr-integration-results.xml`: original ECR download, retained member/component controls and three-way expected/return/payment reconciliation.
- `india-invoice-integration-results.xml`: India entity/engagement, retained native JSON, source job, original download, country filtering and schedule-label regression.
- `browser-results.json`: browser suite covering BRS, VAT201/GST, export, native CAMT/WPS/INV-01/ECR/GSTR-2B preparation and native GSTR-2B purchase-register comparison and reviewed-rule payroll calculations through real Redis/Celery. Native screenshots are in `screenshots/native-sources/`. Seed evidence uses an explicit scanner double.

Frontend type checking, twelve workflow component tests and a production build passed. Native reader type checks and scoped lint passed. Normal evidence and client-request upload controls accept the native file extensions. JSON rejects duplicate keys, non-finite numbers, null bytes and excessive nesting. The source picker uses the user's schedule title while retaining the original filename in its receipt.

[Payroll contribution rules review](payroll-rules.md) adds source-bound expected-versus-reported calculations for reviewed PF/EPS, ESI and PT inputs. Its rule source requires independent approval and retained document hashes. This calculation capability does not establish a qualified production legal rule pack.

[UAE benefit rule review](benefit-rules.md) reuses retained-document binding and independent rule-source approval for the existing end-of-service calculation. Its results preserve rule provenance and become stale when supporting documents are replaced. It still requires assessed regime/cohort facts and professionally qualified rule parameters; alternative schemes remain outside the bounded gratuity computation.

An omitted zero-tax component in a sparse register is reconciled only when the native source explicitly contains a checked zero, the opposite document exists, and its net amount, document date, reporting period and active status agree. The result records this comparison basis without inventing a source-row ID. Missing documents and non-zero component differences remain exceptions. Canonical absence alone does not prove zero. Reporting periods after the reconciliation cutoff are rejected.

Earlier checkpoint receipts:

- `workflow-regression-results.xml`: 275 backend tests across reconciliation, shared audit, practice, sector, diligence, native parsing and the VAT bridge at this checkpoint.
- `native-integration-results.xml`: four native upload/evidence/job tests with real HTTP, PostgreSQL and private object storage.
- `vat-bridge-integration-results.xml`: VAT workbench calculation → source event, calculation lineage, choice listing and invalidation after reopening an invoice.

Integration tests use explicit scanner and broker doubles; they do not qualify a production scanner or prove a live bank integration. Synthetic examples are not consented client pilots.

## Shared credit-note application bridge

`credit-note-applications` reuses evidence upload, controlled CSV sources, immutable jobs,
independent review, export and derived-open-item preparation. It is available in UAE, India
and other engagement countries because its arithmetic does not infer local tax law.

Prepare three independent source roles: `audit-open-items` (signed balances before the listed
applications), `balance-controls` (independent GL controls), and `credit-applications`
(positive application amounts with credit/invoice IDs, currency, date, evidence reference,
allocation reference and rationale). Confirm the pre-application basis in the workspace.
The generated CSV template lists the exact fields; a fictional application example is
in `sample-inputs/SYNTHETIC-credit-applications.csv`.

Applications require the same account, subledger side, party and currency, a negative credit
note and positive invoice/debit note, dates no earlier than either document and no later
than cutoff, and no overapplication or duplicate evidence/allocation reference. Duplicate
document identities under different row IDs are rejected. Split and partial applications
preserve total signed balances; unapplied credits remain exceptions and controls must agree.
Document residual-credit dispositions before independent approval. A reviewed, unblocked
result can prepare a new unreviewed `audit-open-items` source for subsequent procedures,
retaining source dependencies and staleness propagation. This does not post journals or
determine UAE VAT/Indian GST adjustment eligibility.

Verification checkpoint: `credit-application-unit-results.xml` records 421 tests across
the new bridge and existing country/audit/native-reader regressions;
`credit-application-integration-results.xml` records three database/API cases, including
independent approval, required exception disposition, export, derived source freshness,
120-character source IDs, and supporting-table implementation-scope regression.
`credit-application-frontend-results.xml` records 76 frontend tests. Production build,
type checking, scoped lint and UTF-8 preflight pass. The browser receipt records three
passing suites with zero skips or flaky results. Screenshots
`screenshots/native-sources/ae-credit-applications-worker.png` and
`screenshots/native-sources/in-credit-applications-worker.png` were visually inspected;
compact columns keep original/applied/remaining balances and control differences visible,
with all provenance available on expansion and export. This is synthetic workflow
verification, not a client pilot or legal-rule qualification.

## Role-scoped India withholding evidence

Two typed workflows replace new selections of the aggregate `india-withholding` preview:
`india-withholding-liability` requires an explicitly selected deductor or collector role
and four source roles (`expected`, `withheld`, `reported`, `deposited`);
`india-withholding-credit` requires a deductee or collectee role and three source roles
(`books`, `statement`, `certificate`). Both use independently retained
`withholding-records` CSV evidence, separate from generic payroll obligations. Domestic
India workflows are unavailable under UAE or other country engagement packages. UAE
foreign-tax evidence still needs its separately scoped rules and credit assessment.

Each record carries the entity registration, counterparty, role, TDS/TCS scheme, assessed
rule reference, explicit tax-year dates, month, transaction reference/date, INR amount,
current/superseded/cancelled status and original source reference/version. The workspace
requires a role selection; matching uses all these scope fields rather than aggregating
by counterparty totals. Currency controls cover every retained CSV row, including old
versions; `selected_current_totals` separately identifies amounts used in the comparison.
See the generated template and `sample-inputs/SYNTHETIC-withholding-record.csv`.
The sample dates and amounts are fictional test assessments. Prepare separate retained
evidence for each role; copying a single file into multiple roles does not establish
independent populations.

Only one assessed current observation per logical transaction/source role is allowed.
Amendments with multiple current observations, duplicate source versions and contradictory
statuses fail closed; old/cancelled IDs remain in the result but never inflate current
amounts. A source version is a retained identifier, not a sorting instruction or proof of
portal authenticity. Missing current observations remain missing, never zero. Different
legal roles, counterparties, registrations, rules, years or transaction identities cannot
clear each other. Liability timing compares actual deposit dates with the supplied expected
due date and rejects future or pre-transaction deposits. Credit matching never determines
legal entitlement, recoverability or refund rights. Exports and generated source-linked
workpapers retain role, comparison basis, selected totals and source-version references.

The legacy aggregate preview remains readable and can produce a blocked comparison for
older API clients; it cannot be approved, including older retained bodies that omitted
the blocked flag. Earlier role-unassessed approvals are stale even without execution
metadata and cannot feed new workpapers or actions. Regenerate with explicit role-scoped
source records for review.

This is controlled evidence comparison, not a native 26AS/AIS/TRACES/return parser or a
qualified tax-rate, certificate-validity, threshold or current/legacy section crosswalk.
Each current record is a normalized cumulative transaction observation. Raw challan
allocation, partial deposits, FX and overlapping provider observations still need reviewed
normalization; two current lines are not silently summed to approximate that normalization.

Earlier role-separation checkpoint: `withholding-unit-results.xml` records 463 backend tests
across withholding and the existing country/audit/native-reader regression;
`withholding-integration-results.xml` records five database/API tests (two withholding,
two credit-application and one supporting-table freshness case);
`withholding-frontend-results.xml` records all 78 frontend tests. The new two Python modules
pass scoped mypy; backend/frontend scoped lint, frontend type checking, production build
and UTF-8 preflight pass. `browser-results.json` records four real-worker browser suites,
with no skips, unexpected failures or flaky outcomes. The inspected screenshots
`screenshots/native-sources/india-deductor-withholding-worker.png` and
`screenshots/native-sources/india-collectee-withholding-worker.png` show labelled amounts
and differences, with full source/version provenance available on expansion and export.
These receipts overlap earlier checkpoints and must not be added together as independent
scenario counts. They do not qualify live portals, native return formats or legal rules.

## Retained withholding assessments and shared certificate limits

Expected liability records now require a `rule` assessment, and certificate-credit
records require a `certificate` assessment, before a result can be approved. Supply
`assessment_evidence_version_id`, `assessment_sha256`, `assessment_kind`,
`assessment_period_start` and `assessment_period_end`; certificate assessments also need
`assessment_amount_limit` in INR tax amounts. The source workspace's optional shared
assessment-document selector fills blank IDs and hashes from the selected retained
document. It rejects conflicting CSV bindings. The sample CSV leaves these bindings
blank deliberately: upload and select the actual assessed document rather than treating
the fictional sample as supporting evidence.

The existing bounded verifier checks current, clean, authorized retained document
versions and original private-object hashes. Source and result dependencies carry the
document receipts. Replacing an assessment document makes its source and result stale.
Source preparation and calculation retain the document uploader as a contributor, so
that uploader cannot independently approve a source prepared by another user. The same
contributor handling is reused for existing payroll and UAE benefit rule documents.

Numerical comparison and assessment support remain separate. Missing retained evidence,
the wrong assessment kind or a transaction outside the declared coverage period blocks
approval even when every amount matches. `comparison_state` retains the numerical/timing
outcome; `assessment_issues` explains the support problem. A documented exception cannot
override this block. Earlier results without the new assessment contract are stale and
cannot feed new workpapers or actions.

Certificate limits apply across selected current records sharing a retained assessment
document and certificate `source_reference`, rather than separately to each line. The
declared scope, party, registration, role, scheme, currency, version and cap must agree
within that pool. Two records of 100 exceed a shared cap of 150 even though each line is
below the cap. Superseded observations do not consume it. Provenance records both the
cap and total amount used. These are checks of assessed input coverage and limits, not
authentication of the certificate, extraction of its printed terms, legal tax computation
or a reservation of credit across filings and separate runs. Those qualifications remain
open; `credit_entitlement` remains `NOT_DETERMINED`.

Prior assessment checkpoint: `withholding-assessment-unit-results.xml` records 481 backend tests;
`withholding-assessment-integration-results.xml` records ten database/API cases covering
withholding, shared certificates, document ownership/integrity/replacement, existing
payroll/UAE benefit rules, credit applications and supporting-table freshness.
`withholding-assessment-frontend-results.xml` records all 81 frontend tests. Scoped mypy
passes for the two withholding modules and shared workflow service; scoped lint, frontend
type checking, production build and UTF-8 preflight pass. The four real-worker browser
suites in `browser-results.json` include the shared-certificate approval block.
`screenshots/native-sources/india-collectee-cap-withholding-worker.png` was visually
inspected: both rows show numerical `MATCHED` alongside unsupported assessment scope
and disabled approval. Counts overlap earlier receipts and are not additive. Synthetic
fixture uploads use scanner/broker doubles during preparation; browser jobs use the real
Redis/Celery worker. No live portal or professional country qualification is claimed.

## Supporting-table freshness

Prepared supporting-table receipts now use `audit-operations/2` with a server-defined
`supporting-table/1` implementation scope. Reader, normalization, storage, review/access,
schema and relevant library-version changes invalidate these tables; unrelated IFRS
calculation changes do not. Scope selection is not accepted from saved metadata. Older
receipts and other result kinds retain their conservative global implementation guard.
Evidence replacements and dependent-result freshness still propagate normally. This is
file-level isolation for supporting tables, not complete dependency scoping for every engine.

## Explicit PDF bank text grids

Retained bank PDFs can now use an explicit text-grid profile in Supporting tables.
Map the exact account and currency header values on every selected page, the data-row
bands, and the amount or debit/credit columns. Select the sign convention explicitly.
The authenticated raster preview supplies percentage coordinates; the original file
remains unchanged. Reviewers see financial fields first and can expand all provenance.

Extraction verifies the original hash in an isolated process, matches header values,
rejects text crossing row or undeclared column boundaries, and retains page, row,
native cell bounds, raw cell text, ignored-column bounds and selected/unselected pages.
Cropped-page origins are preserved. Limits are 10 MiB, 20 pages, 5,000 selected row
bands, 100,000 characters per page, one million total characters and 45 seconds.
Encrypted, active-content, rotated, image-only and wrapped-row profiles are rejected.

The resulting bank table requires independent review before the existing workflow-source
bridge can consume it. Independent population totals and BRS opening/closing controls
remain supplied separately; footer balances and whole-document completeness are not
inferred. Header transcription checks do not establish ownership or authenticity.
The two cases in `pdf-grid-integration-results.xml` exercise UAE/AED and India/INR
extraction, independent approvals, source bridging, reconciliation, working papers,
export and replacement staleness. These are synthetic fixtures, not provider qualification.

`pdf-grid-unit-results.xml` records 22 reader cases and `pdf-grid-frontend-results.xml`
records all 90 frontend tests. The PDF browser test uses distinct preparer and reviewer
sessions, checks the preview has actually decoded, queues extraction and source bridging
through the real worker, independently approves each stage and reconciles against a
separately retained cashbook in AED and INR. A content-policy defect discovered by
visual review was fixed to allow local blob images; image decoding is now asserted.
Counts overlap previous checkpoints and are not additive.

The combined `browser-results.json` receipt records five passing real-worker browser
tests after fresh fixture preparation: PDF mapping/review/reconciliation in both countries,
credit applications, India withholding role separation, UAE/native country controls and
CSV/XLSX bridges. Production frontend build, type checking, scoped lint and UTF-8
preflight also pass. A fixture variable collision found by the combined run was corrected
so PDF cashbooks cannot replace the older UAE cashbook reference.

## Source history beyond 100 events

Country workflow and accounting-intelligence pickers now expose **Load older sources
and results**. Each request remains bounded to 100 raw events. The newest-first API
accepts `before=<event UUID>` and returns `next_before`; its keyset uses creation time
and UUID together, so tied timestamps and concurrent new events do not shift an older
page's boundary. Cursors must belong to the same tenant, engagement and kind filter.
The existing ascending `after` interface remains available; incompatible cursor modes
are rejected. Event access checks and freshness evaluation still run for every choice.

The UI keeps the newest page live and a contiguous loaded history, deduplicates IDs
with live values taking precedence, and refreshes the full loaded cursor chain after
query invalidation. Retaining the history head prevents new results from pushing
boundary rows out of both visible populations. Older pages do not poll continuously.
Failed requests preserve the current choices and can be retried; history queries are
partitioned by tenant and engagement. This removes the old picker cutoff rather than
increasing a hidden fixed cap.

`event-history-integration-results.xml` verifies 105 tied-time events, a concurrent
insert, exhaustion, cursor/filter rejection and the legacy interface in the disposable
database. `event-history-frontend-results.xml` records 94 passing frontend tests,
including retries, invalidation, scope isolation and the live-boundary regression.
The dedicated browser fixture retains a real reviewed cashbook behind 105 explicitly
unreviewed synthetic placeholders; the placeholders have no qualified provenance and
cannot substitute for approved sources. Its screenshot is
`screenshots/native-sources/older-approved-source-selection.png`.

After the live-boundary fix, the combined browser receipt records six passing tests
(history selection plus the five country-workflow regressions). Production build,
TypeScript checks, scoped frontend/backend lint and UTF-8 preflight pass. This verifies
source-history navigation and the exercised synthetic workflows; it does not qualify
100 client cases or the outstanding country legal packs.

## Remaining work

Representative bank exports and production WPS variants still need qualification. PDF/OCR bank statements, customs imports, GSTR-2B pagination, authenticated retrieval, broader GSTR/IMS/withholding/ESIC government formats, ECR arrears and filing/challan/payment adapters, qualified payroll rule packs across states/cohorts, signed e-invoice verification, live registries and professional country release gates remain open. INV-01 invoice import and the explicit GSTR-2B document profile do not establish IMS action execution or legal ITC eligibility. Monthly ECR parsing does not calculate legal PF dues or establish settlement of a whole challan. The new contribution-review engine computes reviewed input rules; it does not establish their legal applicability. This checkpoint does not close the full original roadmap.

Format references: [SWIFT statement market practice](https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf), [Mashreq WPS upload guidelines](https://netbanking.mashreqbank.com/B001/WPSFileUploadGuidelines_eng.html), [DIB WPS upload walkthrough](https://www.dib.ae/docs/default-source/wps-guidelines/wps-file-upload-walkthrough-for-customers-v1.pdf).

India field reference: [notified e-invoice schema at GSTN-authorized IRP 6](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/). The reader validates reconciliation fields only; it is not an IRP submission validator.

ECR field reference: [EPFO re-engineered ECR user manual v3.0](https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf). The indexed official manual defines the eleven-field monthly member text; direct PDF retrieval was unavailable during implementation. The import validates this explicit reconciliation profile rather than all EPFO submission rules. The example `sample-inputs/SYNTHETIC-india-monthly-ecr.txt` contains fictional members and is not for filing.

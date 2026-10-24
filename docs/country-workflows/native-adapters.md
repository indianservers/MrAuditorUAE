# Native source adapters and VAT engine bridge

Implementation checkpoint: 25 October 2026. These additions extend the existing evidence, intelligence job, immutable event, review and lineage infrastructure.

## Supported profiles

- [Value-only XLSX supporting schedules](supporting-spreadsheets.md): reuse the shared guarded workbook reader with explicit worksheet scope, original numeric decimals, date-epoch receipts and physical row links. Independently reviewed schedules can feed the existing bank/open-item bridges without rewriting the original evidence.

- [Reviewed supporting bank-table bridge](supporting-bank-bridge.md): reuse current independently reviewed bank rows with original evidence, row links, new independent controls and propagated staleness. This reuses existing CSV table normalization; PDF/OCR table qualification remains open.
- [Reviewed supporting open-item bridge](supporting-open-items-bridge.md): reuse receivable/payable schedules with explicit side, balance date and sign convention; retain invoice/credit-note/debit-note classification, due dates, segments and original balances for existing shared audit workflows.

- [Original CSV column mapping](csv-column-mapping.md): explicit field-to-header mapping and declared exclusions, with original evidence retained. This extends canonical sources across shared and country workflows; it is not a qualified bank or government-format adapter and performs no amount/date conversion.

- India GSTR-2B v1.0 JSON: explicit provider document-total and item-sum profiles, recipient/month/document controls, four signed tax-component rows per document, source review flags and unresolved amendment versions. Partial responses and unknown sections fail the import. [Supported fields, workflow, verification and limits](gstr2b.md). This is a document comparison source, not an eligible-ITC calculation or authenticated GST retrieval.

- India monthly EPFO ECR: eleven `#~#` separated fields, with an independently declared establishment, wage month, member count and currency total. Three contribution rows per member retain employee PF, employer EPS and employer PF. Non-zero advance refunds produce a separate fourth row. Controls include those three contributions plus refunds; insurance/administration charges, interest, damages and arrear returns are outside this file profile. Due dates are explicit inputs. Neither a return upload nor a matching amount proves portal filing or payment execution. Rates, exemptions, membership and pension ceilings are not calculated by this reader.

- India INV-01 1.1 JSON: plain invoice objects or a bounded array, with explicit entity GSTIN, purchase/sale direction and reporting month. Invoices, credit notes and debit notes retain signed tax components, reverse-charge flags and document controls. Five component rows are emitted per document, including zero components; declared INR controls are signed tax totals. Assessable value repeats per component and must not be summed across those rows. Item-to-header assessable amounts, component taxes and invoice totals are checked. Rate correctness, IRP authenticity, cancellation/portal status, eligibility, GSTIN registry validity and the full IRP submission schema are not verified. Signed/encrypted wrappers and unregistered/export-buyer profiles require separate adapters.

- CAMT.053: namespace versions 02, 04, 08–13, booked account entries, one complete selected statement. Original opening/closing balances, currency, account, references and dates remain attached. Nested transaction details are not counted twice. Incomplete paginated statements are rejected.
- SWIFT MT940: one complete final-balance statement, including reversal direction and year rollover. Intermediate balances, multiple pages and unsupported tags are rejected rather than silently dropped.
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

Current receipts: `withholding-assessment-unit-results.xml` records 481 backend tests;
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

## Remaining work

Representative bank exports and production WPS variants still need qualification. PDF/OCR bank statements, customs imports, GSTR-2B pagination, authenticated retrieval, broader GSTR/IMS/withholding/ESIC government formats, ECR arrears and filing/challan/payment adapters, qualified payroll rule packs across states/cohorts, signed e-invoice verification, live registries and professional country release gates remain open. INV-01 invoice import and the explicit GSTR-2B document profile do not establish IMS action execution or legal ITC eligibility. Monthly ECR parsing does not calculate legal PF dues or establish settlement of a whole challan. The new contribution-review engine computes reviewed input rules; it does not establish their legal applicability. This checkpoint does not close the full original roadmap.

Format references: [SWIFT statement market practice](https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf), [Mashreq WPS upload guidelines](https://netbanking.mashreqbank.com/B001/WPSFileUploadGuidelines_eng.html), [DIB WPS upload walkthrough](https://www.dib.ae/docs/default-source/wps-guidelines/wps-file-upload-walkthrough-for-customers-v1.pdf).

India field reference: [notified e-invoice schema at GSTN-authorized IRP 6](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/). The reader validates reconciliation fields only; it is not an IRP submission validator.

ECR field reference: [EPFO re-engineered ECR user manual v3.0](https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf). The indexed official manual defines the eleven-field monthly member text; direct PDF retrieval was unavailable during implementation. The import validates this explicit reconciliation profile rather than all EPFO submission rules. The example `sample-inputs/SYNTHETIC-india-monthly-ecr.txt` contains fictional members and is not for filing.

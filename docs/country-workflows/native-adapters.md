# Native source adapters and VAT engine bridge

Implementation checkpoint: 25 October 2026. These additions extend the existing evidence, intelligence job, immutable event, review and lineage infrastructure.

## Supported profiles

- India monthly EPFO ECR: eleven `#~#` separated fields, with an independently declared establishment, wage month, member count and currency total. Three contribution rows per member retain employee PF, employer EPS and employer PF. Non-zero advance refunds produce a separate fourth row. Controls include those three contributions plus refunds; insurance/administration charges, interest, damages and arrear returns are outside this file profile. Due dates are explicit inputs. Neither a return upload nor a matching amount proves portal filing or payment execution. Rates, exemptions, membership and pension ceilings are not calculated by this reader.

- India INV-01 1.1 JSON: plain invoice objects or a bounded array, with explicit entity GSTIN, purchase/sale direction and reporting month. Invoices, credit notes and debit notes retain signed tax components, reverse-charge flags and document controls. Five component rows are emitted per document, including zero components; declared INR controls are signed tax totals. Assessable value repeats per component and must not be summed across those rows. Item-to-header assessable amounts, component taxes and invoice totals are checked. Rate correctness, IRP authenticity, cancellation/portal status, eligibility, GSTIN registry validity and the full IRP submission schema are not verified. Signed/encrypted wrappers and unregistered/export-buyer profiles require separate adapters.

- CAMT.053: namespace versions 02, 04, 08–13, booked account entries, one complete selected statement. Original opening/closing balances, currency, account, references and dates remain attached. Nested transaction details are not counted twice. Incomplete paginated statements are rejected.
- SWIFT MT940: one complete final-balance statement, including reversal direction and year rollover. Intermediate balances, multiple pages and unsupported tags are rejected rather than silently dropped.
- UAE WPS SIF: the explicit ten-field EDR/SCR profile, employee records followed by one employer trailer. Filename, employer, employee, account, routing, period, count and amount controls are checked. A SIF instruction never proves payment execution. Other bank-specific variants require additional adapters.
- Existing UAE VAT201 engine: current, reconciled calculations become `return-boxes` sources without re-keying or recalculating VAT rates. Reviewed manual tax adjustments remain separate from base tax. Calculation dependencies propagate staleness; filed-return evidence must still be imported independently. Aggregate box 1 does not establish an emirate-level comparison.

Uploads remain subject to clean retained evidence, private storage, hash verification, explicit external row/amount controls and independent source review. Structured uploads are bounded to 10 MiB and 5,000 rows. XML uses entity/DTD protection. Native parsing verifies file consistency, not account ownership or legal compliance.

The results screen exposes original source controls and calculation basis. Available formats are country gated; WPS and the VAT bridge require a UAE engagement. Access to the VAT bridge also requires VAT read permission, including when its results are consumed downstream.

## Verification receipts

Latest native checkpoint:

- `native-india-regression-results.xml`: 359 backend tests across reconciliation, shared audit, practice, sector, diligence and native/calculation sources.
- `native-country-integration-results.xml`: fourteen database/API integration tests across country workflows, native files and calculation bridges.
- `india-ecr-integration-results.xml`: original ECR download, retained member/component controls and three-way expected/return/payment reconciliation.
- `india-invoice-integration-results.xml`: India entity/engagement, retained native JSON, source job, original download, country filtering and schedule-label regression.
- `browser-results.json`: browser suite covering BRS, VAT201/GST, export, native CAMT/WPS/INV-01/ECR preparation and reviewed-rule payroll calculations through real Redis/Celery. Native screenshots are in `screenshots/native-sources/`. Seed evidence uses an explicit scanner double.

Frontend type checking, eleven workflow component tests and a production build passed. Native reader type checks and scoped lint passed. Normal evidence and client-request upload controls accept the native file extensions. JSON rejects duplicate keys, non-finite numbers, null bytes and excessive nesting. The source picker uses the user's schedule title while retaining the original filename in its receipt.

[Payroll contribution rules review](payroll-rules.md) adds source-bound expected-versus-reported calculations for reviewed PF/EPS, ESI and PT inputs. Its rule source requires independent approval and retained document hashes. This calculation capability does not establish a qualified production legal rule pack.

An omitted zero-tax component in a sparse register is reconciled only when the native source explicitly contains a checked zero, the opposite document exists, and its net amount, document date, reporting period and active status agree. The result records this comparison basis without inventing a source-row ID. Missing documents and non-zero component differences remain exceptions. Canonical absence alone does not prove zero. Reporting periods after the reconciliation cutoff are rejected.

Earlier checkpoint receipts:

- `workflow-regression-results.xml`: 275 backend tests across reconciliation, shared audit, practice, sector, diligence, native parsing and the VAT bridge at this checkpoint.
- `native-integration-results.xml`: four native upload/evidence/job tests with real HTTP, PostgreSQL and private object storage.
- `vat-bridge-integration-results.xml`: VAT workbench calculation → source event, calculation lineage, choice listing and invalidation after reopening an invoice.

Integration tests use explicit scanner and broker doubles; they do not qualify a production scanner or prove a live bank integration. Synthetic examples are not consented client pilots.

## Remaining work

Representative bank exports and production WPS variants still need qualification. PDF/OCR bank statements, customs imports, India GSTR/IMS/withholding/ESIC government formats, ECR arrears and filing/challan/payment adapters, qualified payroll rule packs across states/cohorts, signed e-invoice verification, live registries and professional country release gates remain open. INV-01 invoice import does not replace GSTR-2B or IMS. Monthly ECR parsing does not calculate legal PF dues or establish settlement of a whole challan. The new contribution-review engine computes reviewed input rules; it does not establish their legal applicability. This checkpoint does not close the full original roadmap.

Format references: [SWIFT statement market practice](https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf), [Mashreq WPS upload guidelines](https://netbanking.mashreqbank.com/B001/WPSFileUploadGuidelines_eng.html), [DIB WPS upload walkthrough](https://www.dib.ae/docs/default-source/wps-guidelines/wps-file-upload-walkthrough-for-customers-v1.pdf).

India field reference: [notified e-invoice schema at GSTN-authorized IRP 6](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/). The reader validates reconciliation fields only; it is not an IRP submission validator.

ECR field reference: [EPFO re-engineered ECR user manual v3.0](https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf). The indexed official manual defines the eleven-field monthly member text; direct PDF retrieval was unavailable during implementation. The import validates this explicit reconciliation profile rather than all EPFO submission rules. The example `sample-inputs/SYNTHETIC-india-monthly-ecr.txt` contains fictional members and is not for filing.

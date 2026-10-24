# India GSTR-2B document import

This adapter adds original JSON evidence to the India GST workflow. It preserves document amounts and source review flags; a matching purchase register does not establish recoverable input tax credit.

## Import and review

1. Retain the original JSON as clean evidence for an India engagement.
2. In Country workflows → Prepare sources, choose `tax-documents` and `india-gstr2b-json`.
3. Declare the recipient GSTIN, return month, independent document count and signed INR tax control. Each document produces four rows: IGST, CGST, SGST and CESS, including zero components. The expected row count is four times the document count.
4. Independently review the prepared source. Select that reviewed version and a separately prepared purchase register for the India GST comparison.
5. Investigate review flags and differences before result approval. Source replacement invalidates dependent results through the existing evidence and lineage controls.

Controls sum signed document tax fields, including notes and reversal records. They are neither a net credit claim nor an eligible-ITC total. Taxable value repeats across component rows and must not be summed across them.

The fictional example [SYNTHETIC-india-gstr2b.json](sample-inputs/SYNTHETIC-india-gstr2b.json) contains one June 2026 invoice for recipient `27ABCDE5678G1Z8`: one document, four rows and INR 18 signed tax. It is for testing only and must never be filed or represented as a government-issued return.

## Explicit supported profiles

Version `1.0` plain documents and bounded transparent `data` wrappers are supported. The layouts are based on the provider's [current document response](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-2b/document) and [legacy upload example](https://sandbox-docs.readme.io/reference/upload-gstr-2b). These references document particular provider payloads; they do not establish universal GST portal schema coverage. The [GST matching-tool manual](https://tutorial.gst.gov.in/downloads/matchingtool.pdf) describes downloading JSON and matching but does not qualify every field layout handled here.

Supported document sections are `b2b`, `b2ba`, `cdnr`, `cdnra`, `isd`, `isda`, `impg`, `impgsez`, `ecom`, `ecoma` and `itcrev`. Both item sums and direct document totals are handled. When both appear, their amounts must agree. Credit-note direction is applied once to unsigned source amounts.

Imports retain customs port and bill-of-entry identity. Compare those records with a bill-of-entry register; supplier-invoice identity is not inferred. ISD records without a taxable base explicitly mark that base unavailable. Amendments, reversals, unavailable credit and rejected/pending IMS records require source review even if amounts agree.

Multiple original/amended/reversal versions of the same comparison key retain every source version. The calculation neither picks the first version nor sums them into a current credit. It emits an unresolved review exception with unavailable comparison amounts until the source history is resolved through an appropriate workflow.

## Rejection and limits

Unknown document sections, partial/paged responses, provider business failures, competing payloads, invalid dates, duplicate same-section documents and inconsistent controls fail the source preparation. Nil activity requires an explicit rationale and zero document, row and monetary controls; a nonzero summary cannot be imported as nil.

The bounded reader accepts at most 10 MiB, 1,250 documents and 5,000 component rows. Decimal values remain exact. Duplicate JSON keys, non-finite numbers, excessive nesting and extreme numeric exponents are rejected. Provider checksum strings are retained as metadata, not cryptographically verified; the evidence pipeline separately verifies the stored original file hash.

## Verification and open qualification

`test_india_gstr2b_source.py` unit tests cover layouts, controls, notes, amendments, imports, ISD, nil returns, wrappers, failure bodies, source-version ambiguity and numeric boundaries. The database/API tests exercise retained evidence, source review, reconciliation, original download and XLSX export. The browser suite queues native preparation and purchase-register comparison through Redis/Celery; screenshots are in `screenshots/native-sources/india-gstr2b-json-native-review.png` and `india-native-gstr2b-reconciliation.png`.

Authenticated GST retrieval, paginated-part assembly, provider checksum verification, representative consented client fixtures, future schema variants, historic amendment resolution and a legally qualified ITC engine remain open. Synthetic scanner doubles used in verification do not qualify production malware scanning. This adapter does not close the original thirteen-use-case roadmap.

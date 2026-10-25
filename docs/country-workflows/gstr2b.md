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

Unknown document sections, standalone partial/paged responses, provider business failures, competing payloads, invalid dates, duplicate same-section documents and inconsistent controls fail the source preparation. Nil activity requires an explicit rationale and zero document, row and monetary controls; a nonzero summary cannot be imported as nil.

The bounded reader accepts at most 10 MiB, 1,250 documents and 5,000 component rows. Decimal values remain exact. Duplicate JSON keys, non-finite numbers, excessive nesting and extreme numeric exponents are rejected. Provider checksum strings are retained as metadata, not cryptographically verified; the evidence pipeline separately verifies the stored original file hash.

## Numbered original response files

The explicit `india-gstr2b-json-parts-1` profile supports numbered responses from the current provider document API. Retain the original manifest containing `fc` and every original response file separately. Enable **Assemble numbered GSTR-2B files** in source preparation, select the manifest, and supply the independently checked file count, each file number and evidence version, document count, signed tax control and original request reference. Declare whole-population counts and totals separately and record the retrieval batch assessment. Blank template controls require operator input.

Every index from 1 through the declared count must occur exactly once. The manifest file count, GSTIN, return period and schema version must agree. Present response dates must equal the manifest generation date. Some provider examples omit file numbers and generation dates; original request references and explicit batch assessment therefore require independent source review. The assembler cannot prove that such files belong to one provider generation or authenticate their origin. It retains original byte hashes and checksum strings without treating them as provider authentication.

Each part must close its independent controls, and the combined population must close the whole manifest controls. Repeated original bytes and duplicate documents fail preparation. Per-part summaries remain in retained originals with fingerprints and are not added to the whole manifest summaries. Every component row retains its original part number, evidence version, byte hash and source row identity. Source replacement makes dependent calculations stale through retained evidence lineage.

Limits are 100 parts plus one manifest, a 100 MiB original-evidence verification budget, 10 MiB for each JSON and the assembled document, 1,250 documents and 5,000 component rows. Unknown sections and token pagination remain unsupported. The original single-file reader still rejects partial responses. Numbered assembly is available only to India engagements; GSTR-2B sources can supply the return role of the India GST workflow, with independent review required before matching an assembled source. A separately retained purchase register supplies the books role.

## Verification and open qualification

`test_india_gstr2b_source.py` unit tests cover layouts, controls, notes, amendments, imports, ISD, nil returns, wrappers, failure bodies, source-version ambiguity and numeric boundaries. The database/API tests exercise retained evidence, source review, reconciliation, original download and XLSX export. The browser suite queues native preparation and purchase-register comparison through Redis/Celery; screenshots are in `screenshots/native-sources/india-gstr2b-json-native-review.png` and `india-native-gstr2b-reconciliation.png`.

Authenticated GST retrieval, token-paginated and other unqualified response profiles, provider checksum verification, representative consented client fixtures, future schema variants, historic amendment resolution and a legally qualified ITC engine remain open. The focused numbered-file browser flow passes through actual source preparation, independent approval, role filtering and purchase-register comparison: eight matched component rows and zero exceptions. Visually inspected screenshots are `screenshots/native-sources/india-gstr2b-numbered-file-controls.png` and `india-gstr2b-numbered-file-comparison.png`. The production frontend build also passes. Numbered-file tests cover independent per-part and whole controls, missing or mixed scope, retained originals, role/country restrictions, review, exports and replacement staleness. The committed receipts record 1,376 passing backend unit tests (four skipped), 134 passing frontend tests and four passing GSTR-2B integration tests. Synthetic scanner doubles used in verification do not qualify production malware scanning. This adapter does not close the original thirteen-use-case roadmap.

# UAE import VAT detail review

The `uae-import-vat` workflow compares three independently retained and reviewed
`import-vat-lines` sources: `customs`, `portal` and `books`. It complements the
existing customs/invoice/goods-receipt and VAT201 box comparisons.

The FTA's [VAT Returns User Guide](https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf)
distinguishes imported goods in Box 6 from corrections in Box 7. This comparison
preserves that separation; the mapping is indicative of the assessed source kind.
It does not calculate legal import valuation, rates, recovery or filing entitlement.

## Prepare sources

Select **Prepare sources → Retained source file → Controlled canonical CSV →
import-vat-lines**. Retain separate customs, portal and book files. The original
files must be clean and hash verified. Copies of one identical file cannot establish
independent roles. Supply a row count, an AED **tax** total and a separate independent
AED **taxable-base** total. Both totals control every retained row, including any
superseded/cancelled observations, before the workflow selects current observations.

The three `sample-inputs/SYNTHETIC-uae-import-vat-{customs,portal,books}.csv` files
contain fictional populations: two rows each, AED taxable-base control **900** and
tax control **45**. They exercise a declaration of 1,000/50 and a distinct adjustment
of -100/-5, rather than netting both into one declaration.

Each row identifies a 15-digit TRN, customs registration, authority, declaration,
line reference, assessed VAT period, actual import/adjustment date and source evidence
reference. `record_version` is an opaque source identifier; it is not sorted to
guess the newest record. Declare `version_status` explicitly as `current`,
`superseded` or `cancelled`.

`entry_kind=declaration` requires non-negative net and tax amounts and an empty
adjustment reference. `entry_kind=adjustment` requires its own reference and permits
signed corrections, including tax-only corrections. No rate is assumed. Keep the
actual economic date for late-reported entries; a date outside the assessed period
is a timing exception. Future dates and periods are rejected at calculation.

Have an independent reviewer approve each source, then select the three roles in
**Run workflows → UAE import VAT declarations / portal / books review**. Use one
TRN and assessed VAT period per run. This domestic workflow is unavailable in India.

## Review results

Matching uses the complete declaration, registration, authority, line and adjustment
identity. Opposing declaration differences cannot cancel at aggregate level. Net,
tax and dates are compared separately. Superseded/cancelled records remain in
provenance; they do not add to current balances. A source key without exactly one
current record blocks approval. Missing values stay unknown rather than becoming zero.

The summary keeps declarations and corrections separate for every source role.
An absent adjustment population does not assert a verified nil Box 7. An unresolved
role makes that role's selected totals incomplete. Expand source provenance to inspect
every version, amount, assessment and evidence reference. Exports preserve the full
result. Independent approval can feed the existing source-linked working-paper action;
original evidence replacement makes dependent approvals stale.

## Bridge selected boxes to the VAT201 comparison

On a current, independently reviewed import comparison, expand **Prepare selected
import boxes for VAT201 comparison**. Choose the assessed role (`books`, `customs`
or `portal`), a source title and the populated boxes. Supply exact independent
current-detail row counts, taxable amounts and tax totals for each selected box,
plus a scope assessment. These controls concern selected current detail, unlike
the original file controls that include all retained versions.

The bridge reconstructs canonical `return-boxes` from the selected detail and
cross-checks the parent totals. Empty or incomplete populations are rejected;
missing adjustment detail cannot become a zero Box 7. You may select Box 6 alone
when only that population is assessed. It does not generate summary boxes.
Signed Box 7 values stay signed. The canonical `tax` field holds the final assessed
tax of that population, with a zero separate `adjustment` field to avoid counting
the correction twice. Detail-row IDs and the parent comparison remain linked.

The new source starts **UNVERIFIED** and needs an independent reviewer who did not
prepare it or contribute its underlying data. A parent reviewer may review the next
stage if they did not prepare it; reviewing alone does not make them a data contributor.
Select it as the
**books** source in **UAE VAT201 box-level return reconciliation**, select separately
retained filed evidence as **return**, and explicitly set the required boxes to
the assessed scope, for example `6,7`. The server rejects this derived source as
filed-return evidence. Changes to original evidence make the bridge and downstream
comparison stale. This transfers reviewed assessed values; it does not execute a
filing or establish whole-return completeness.

By default, `required_boxes` remains a minimum-coverage control: every retained box
is compared, and additional filed boxes appear as return-only exceptions when book
evidence is absent. For an import-only review against a full filed source, explicitly
check **Compare only the required VAT201 boxes** and complete **Selected VAT201 box
scope assessment**. The calculation then compares only the named boxes while retaining
every excluded row with its original ID, registration, period, currency and amounts.
Selection does not turn missing selected evidence into zero or hide additional
registrations and future periods from the source-wide checks.

The result states **Selected VAT201 boxes only** and **Whole-return completeness is
not determined**. Included/excluded counts and calculated base, tax and adjustment
totals explain the partition of the original source. Review exclusions through their
own page controls; paging them does not move the selected comparison rows. The XLSX
retains every exclusion in **Excluded VAT boxes**. PDF/DOCX cover text and generated
working papers carry the selected scope; working-paper row tables retain the existing
1,000-row preview bound and refer back to the complete immutable source/XLSX.

`sample-inputs/SYNTHETIC-vat201-14-box-source.csv` is a fictional canonical fixture
covering all fourteen supported box keys, not a native portal file or a filing. Declare
14 rows and the AED tax-field file control **230**. That control sums all retained tax
fields, including summary boxes; it is not VAT payable. The import-only comparison
includes tax **45** and excludes tax **185** across twelve other rows. Base controls
partition into **900** included and **1,500** excluded. These are calculated review
controls, not a legal tax calculation or evidence of whole-return correctness.

The workflow API uses `restrict_to_required_boxes=true` with a meaningful
`box_scope_assessment` to request the explicit selection. Omitting the flag preserves
the all-retained-box behavior. Event detail supports independent `excluded_offset`
and `excluded_limit` (default 100, maximum 500) without altering selected-row pagination.

API: `POST /intelligence/engagements/{eid}/events/{id}/import-vat-box-source` takes
`source_role`, `label`, `assessment` and a `boxes` map keyed only by `6` and/or `7`.
Each box requires `expected_rows`, `taxable_amount` and `tax`. All original import
source roles and the parent comparison must be current and independently reviewed.

This remains a controlled comparison of assessed source details. Native customs/EmaraTax
downloads, authenticated TRN/customs linkage, agent responsibility, valuation and rate
rules, input-tax recovery, adjustment justification and whole-return composition
remain separate qualification/integration work. Nothing is filed, posted or paid.

## Verification

`import-vat-unit-results.xml` covers the new engine plus shared country, sector,
practice, payroll, withholding and native-source regressions. The dedicated API
receipt is `import-vat-integration-results.xml`: actual retained CSVs, separate
source identities and controls, maker/checker rejection, independent approvals,
export, working-paper creation and replacement staleness. Scanner and broker
dispatch are explicit test doubles in API fixture preparation. Browser jobs use
the real Redis/Celery worker; these fixtures do not qualify a production provider.

Initial import-detail checkpoint: 376 targeted backend tests, the import database/API case and
all 96 frontend tests pass. The combined browser receipt records seven passing
tests, including successful import comparison/export, India isolation and the
ambiguous-current-version approval block. Production build, type checking,
scoped mypy/lint and UTF-8 preflight pass. Counts overlap earlier receipts.

Selected-box bridge checkpoint: `import-vat-bridge-unit-results.xml` records 388
targeted backend tests; `import-vat-bridge-integration-results.xml` records two
database/API cases, covering the full bridge/independent filed comparison and the
unreviewed-source block. `import-vat-bridge-frontend-results.xml` records all 100
frontend tests. The combined browser receipt now records eight passing tests,
including actual UI bridge preparation, independent review and VAT201 comparison
through the real worker. The parent reviewer may review the derived source when
they did not prepare it, consistent with existing maker/checker rules. Original
preparers remain excluded. Production build, type checks, scoped mypy/lint and
UTF-8 preflight pass. These counts overlap the initial checkpoint.

`screenshots/native-sources/uae-import-boxes-filed-comparison.png` shows the reviewed
result: both selected boxes matched, with source row IDs and zero differences.

Explicit wider-source scope checkpoint: `vat-selected-scope-unit-results.xml` records
399 targeted backend tests, including unchanged all-retained-box behavior, missing
selected evidence, extra registrations/future periods, partition control totals and
XLSX/PDF/DOCX scope retention. `vat-selected-scope-integration-results.xml` records
two database/API cases and verifies the 14-box source, independent excluded-row
pagination, full XLSX exclusions, working-paper scope and replacement staleness.
`vat-selected-scope-frontend-results.xml` records all 103 frontend tests, including
101-row exclusion paging and visible scope in working-paper actions. The combined
browser receipt records eight passing real-worker tests against the updated fixtures.
Production build, type checking, scoped mypy/lint and UTF-8 preflight pass. The synthetic
two-page PDF export was rendered and visually reviewed; scope labels and the excluded
count were legible without clipping. Counts overlap prior checkpoints.

`screenshots/native-sources/uae-vat-selected-scope-exclusions.png` captures the explicit
scope assessment and all twelve excluded rows from the fictional full source.

Screenshots in `screenshots/native-sources/uae-import-vat-*` show the independent
source totals and blocked-version case. Separate row captures preserve the full
vertical row population and, where needed, the right-hand decisions after ordinary
horizontal scrolling; the original summary capture alone can clip rows in the
workspace's scroll container.

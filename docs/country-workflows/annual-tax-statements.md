# India annual tax statement scope

The beneficiary-credit workflow now preserves an explicitly declared annual
statement header on manually normalized `withholding-records`. This is groundwork
for native statement readers, not a native Form 26AS or Form 168 import profile.
The original controlled CSV, independent source review, assessment-document
bindings, immutable result, export and downstream freshness rules are reused.

## Country and period rules

The [Income Tax Department's e-filing procedure](https://www.incometaxindia.gov.in/tax-services/process-annual-tax-statement-e-filing-form-26as-form-168)
distinguishes the declared statutory Form 26AS through previous year 2025–26 /
assessment year 2026–27 from Form 168 starting in tax year 2026–27. The separate
[TRACES procedure](https://www.incometaxindia.gov.in/tax-services/process-annual-tax-statement-traces-form-26as-form-168)
still calls its modern portal statement Form 26AS while asking for a tax year.
A printed portal label must therefore not be used to infer statutory-form
equivalence. Historical AY and modern TY headers can both display `2026-27`,
but their underlying periods differ. The schema requires the complete April–March period,
the exact form, PAN, displayed year, explicit assessment-year/tax-year basis and
snapshot generation date. A transaction or reporting month cannot postdate the
snapshot. A snapshot may be generated during the underlying year; it does not
establish full-year completeness.

`annual_statement` is an optional JSON object in each controlled CSV row. Blank
values make no form claim. A nonblank malformed, null, array or boolean value is
rejected. If one row declares a header, every row in that statement population
must declare one. PAN, form and underlying year must agree across the population;
one source version must have one snapshot date. Different retained amendment
versions may preserve different snapshot dates. Current/superseded/cancelled
selection remains explicit and never sums duplicate current versions.

The row's registration must equal the declared PAN and its assessed year must
equal the header's underlying period. Only deductee/collectee records may carry
these headers. At calculation, only the `statement` source role accepts them:
they cannot serve as books, certificates, liability returns or deposit evidence.
The domestic workflow remains unavailable in UAE and other country contexts.
PAN formatting is checked; registry authenticity is not established.

## Example header

For underlying period 2026-04-01 through 2027-03-31:

```json
{"form":"168","pan":"ABCDE1234F","period_start":"2026-04-01","period_end":"2027-03-31","displayed_year_basis":"TAX_YEAR","displayed_year":"2026-27","generated_on":"2026-06-30"}
```

`ABCDE1234F` is fictional format-only test data. An earlier underlying period
2025-04-01 through 2026-03-31 instead requires form `26AS`, basis
`ASSESSMENT_YEAR`, and displayed year `2026-27`. The CSV cell must use ordinary
CSV quoting around its JSON object. The source still requires independent INR
amount and row-count controls, transaction identity, original source reference
and version, assessed status, plus the existing separately retained certificate
assessment for a supported beneficiary-credit comparison.

The result retains each source-version header under `annual_statement_scopes`
and the selected current header on each matched statement row. The UI shows the
underlying period separately from the displayed year. XLSX includes the scope
contract, explicit normalization basis and all snapshot headers on its cover,
and the selected header in its row details. A declared header never supplies
rates, booking status, a missing certificate, entitlement, recoverability,
filing proof or payment confirmation.

## Primary-source investigation and remaining native work

The [TRACES text-to-Excel tutorial](https://traces61contents.tdscpc.gov.in/docs/E-Tutorial%20-%20Procedure%20of%20Converting%20Form%2026AS%20Text%20File%20to%20Excel%20File.pdf)
was downloaded and pages 4 and 10 visually inspected on 2026-10-28. The original
781,769-byte PDF had SHA-256
`0b05c6f1841cf1f570816e9962012010befec1a69d2edb9584f86e0207245181`.
Its screenshot shows a 2022–23 annual statement with caret-delimited header,
deductor-summary and transaction-detail records, followed by distinct parts.
The tutorial is not a complete current transaction-format specification. The
original and inspection images are local research files, not redistributed
client fixtures or a committed qualification receipt.

The [official Form 168 guidance](https://www.incometaxindia.gov.in/documents/d/guest/fn-168)
describes PAN-linked information and the tax-year header. It does not supply a
complete portal export grammar. Native imports therefore remain open: obtain
and preserve complete versioned formats for all relevant TDS/TCS parts, verify
summary/detail controls and booking-status semantics, retain original positions
and amendments, and test unsupported parts without silently dropping them.
Do not infer Form 168 compatibility from the older caret tutorial. These scope
checks do not qualify the full Form 168 information population, professional
conclusions, portal compatibility or real-client coverage.

## Verification

[The validation record](../phase-12/annual-statement-validation.json) pins the
tested source hashes and exact JUnit receipts. The full unit run passed 3,135
tests with five known skips; 45 new unit cases cover the statement scope.
Five database/API cases passed, including historical Form 26AS and current
Form 168 collectee flows through independent review, approval, XLSX export,
working-paper creation and stale evidence handling. Scanner and broker dispatch
remain explicit doubles in those API cases. All 295 frontend tests passed,
including separate AY/TY display cases. Production build, frontend type checks,
scoped lint, Python typing across 393 application files and contract consistency
checks passed. These counts overlap; this increment adds no claim of native
statement browser verification or a completed independent client pilot.


## Explicit modern TRACES portal-label declaration

When retaining a modern TRACES statement without asserting a statutory form
number, use `form: null`, `source_channel: "TRACES"` and the exact nonblank
`portal_statement_label`. For example:

```json
{"form":null,"pan":"ABCDE1234F","period_start":"2026-04-01","period_end":"2027-03-31","displayed_year_basis":"TAX_YEAR","displayed_year":"2026-27","generated_on":"2026-06-30","source_channel":"TRACES","portal_statement_label":"Form 26AS"}
```

This is a complete declared header object, not a null `annual_statement` CSV
cell. The statutory form remains unasserted. The label and channel are retained
in reviewed sources, results and XLSX; the UI identifies a portal statement and
shows its printed label. No equivalence with Form 168 or a historical Form 26AS
population is inferred. Portal and statutory declarations cannot be mixed as
amendment snapshots in one normalized source. All PAN, underlying-year,
transaction-date, snapshot, role and independent-control checks still apply.

Do not attach these portal-label fields to an asserted statutory form. Older
statutory headers keep their original serialized shape: absent optional portal
fields are not inserted as null metadata. Neither mode is a native TRACES/AIS
export parser, a complete statement-population assessment, credit entitlement
or portal authenticity verification.

The naming distinction was reviewed against the two official procedures on
30 October 2026. Official Form 168 guidance describes broader AIS information;
that does not supply a complete TRACES export grammar. Direct local retrieval
of that guidance PDF returned HTTP 403, so no new original-PDF checksum or full
visual-format qualification is asserted by this increment.

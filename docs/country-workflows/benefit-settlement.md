# UAE gratuity: reviewed calculation to bank settlement

`POST /intelligence/engagements/{eid}/benefit-settlement-source` reuses a current,
independently reviewed `uae-benefit-review` result to prepare expected final
gratuity obligations. This closes the re-entry gap between the supplied-rule
employee calculation and the existing `obligation-bank-allocations` workflow.
It does not create a payment instruction or determine statutory applicability.

## Workflow

1. Retain employee service facts and rule documents, independently review the
   sources, calculate benefits and independently approve the current result.
   New benefit results retain original service start/end and scheme. Older
   results without those facts must be regenerated before this bridge is used.
2. In the reviewed UAE result, select the employee service spans. Supply an
   assessed employer registration, separate retained settlement-support document,
   independently prepared selected-row count and AED total, and each supported
   due date and document reference. The UI retains selections across result pages;
   controls cover only the explicitly selected population.
3. Independently review the prepared expected source. The preparer and retained
   settlement-document uploader are contributors and cannot approve their own
   source. The parent result and exact clean supporting version remain dependencies.
4. Prepare separate independently reviewed HR settlement-register, bank and
   allocation sources. Expected computation, declared HR reporting and booked
   bank movements are separate evidence roles. The derived expectation cannot
   impersonate a reported settlement or a bank source.
5. Run the existing explicit bank-allocation comparison, review differences and
   timing, and obtain independent final approval. XLSX retains the employment
   scope and amounts; context/rule replacement makes dependent results stale
   without rewriting their saved bodies.

The new form uses ordinary employee selections and individual date/reference
fields. Independent count and total start blank; no legal due date is inserted.
The employer, employee-ID interpretation, selected service population and due
dates require assessment against the retained document. A retained hash verifies
bytes, not document meaning or an employer's legal identity.

## Evidence and identity

The source contains `obligations`, restricted to the `expected` role of
`obligation-bank-allocations`. Its parser contract is
`benefit-settlement-obligations/1`. Row counts and AED totals are checked before
preparation and checked again against the current parent at calculation. Original
employee/result-row and rule-document/version/hash references remain available.
Derived row IDs are bounded even when an original employee ID uses all 120
characters. Unselected parent rows are explicitly recorded as excluded.

Each row uses `BENEFIT:GRATUITY`, AED and the service-end month. Its typed
`benefit_scope` contains `service_start`, `service_end`, `regime`, `cohort`,
`work_model` and `scheme`. Expected and reported scopes must agree alongside
employer, employee, month, component and currency. Different service spells,
cohorts and work models cannot clear each other through matching cash amounts.
These scopes cannot be combined with pension or withholding scopes, routed into
an aggregate comparison, or treated as Indian domestic payroll obligations.

The comparison retains the existing partial/pooled allocation, capacity,
over-allocation, independent source review, reversal and booked-date safeguards.
A movement before service end cannot establish final gratuity settlement;
advances require a separate assessed procedure. A value-date fallback cannot
establish the dated settlement. Due dates cannot precede service end, and later
payments are compared against the explicitly assessed due date.

For a fictional expected gratuity of AED 2,100, a declared employee-file paid
amount of AED 999 does not reduce the expectation. Independently allocated bank
cash of AED 1,500 leaves AED 600 outstanding. A full AED 2,100 payment after an
assessed due date can still be late. These examples explain evidence arithmetic,
not a legal rate, eligibility decision or actual client result.

## Limits and verification

Only resolved full-time or part-time gratuity with one constant assessed work
model and service span is supported. Alternative schemes, changing work models,
unsupported cohorts and missing rule provenance remain unresolved. The bridge
does not qualify the supplied rule pack, calculate a statutory deadline, establish
IAS 19 measurement, post a journal or verify that money reached the employee.
Employee-benefit calculations and this settlement comparison retain their
separate purposes.

The API regressions exercise retained full-time/part-time inputs, independent
source/result review, exact totals, a pooled bank outflow, XLSX scope export,
purpose restrictions, document-uploader separation and recursive staleness after
either rule or settlement-support replacement. Their scanner and dispatch
boundaries are explicit doubles. Unit tests additionally cover partial and late
payments, service-identity mismatches, advances, reversals, value-date fallback,
zero versus missing amounts, long identifiers and India isolation. Frontend tests
cover explicit controls, pagination selections, older undated results, country/
freshness gating and visible service dates. Hosted browser verification is a
separate source-pinned gate; authored assertions alone are not a passing receipt
or a visually inspected screenshot. Real-client and professional qualification
remain open.

[The source-pinned local validation record](../phase-12/benefit-settlement-validation.json)
retains original JUnit receipts: 3,170 unit tests passed with five known skips,
including 35 new benefit-settlement cases; four database/API regressions passed.
The frontend passed 302 tests, its production build, type checking and scoped
lint. Python typing passed across 395 application files and current API contract
snapshots matched. These counts overlap.

[Hosted browser proof on b315b53](../phase-12/gratuity-browser-b315b53.json)
records all three cases passing in 1.3 minutes. The new UAE path uses real
scanner/broker/worker services, the browser preparation form, independent source
review, worker bank allocation, UI final review, exact XLSX values and service
scope, and context-replacement staleness with complete object equality and
disabled approval. Three original images were downloaded with a verified archive
digest and individually inspected. The stale frame captures an ancillary
cash-claim panel still loading; it does not visually qualify that panel's final
status. Source setup/reviews use APIs and all fixtures are synthetic. The earlier
selector and JSON-order test failures remain retained as negative receipts.
Frontend302/build/types/lint, security, ML and containers passed on b315b53;
latest-source full backend verification remains running.

Original captures: [preparation](screenshots/browser-workflows/AE-gratuity-settlement-preparation-b315b53.png),
[reviewed settlement](screenshots/browser-workflows/AE-gratuity-reviewed-bank-settlement-b315b53.png),
and [stale result](screenshots/browser-workflows/AE-gratuity-context-replaced-stale-b315b53.png).

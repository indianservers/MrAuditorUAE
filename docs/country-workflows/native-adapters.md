# Native source adapters and VAT engine bridge

Implementation checkpoint: 25 October 2026. These additions extend the existing evidence, intelligence job, immutable event, review and lineage infrastructure.

## Reviewed contributions to expected remittances

`POST /intelligence/engagements/{eid}/contribution-obligation-source` prepares
expected settlement obligations from a current, independently reviewed UAE pension
or India payroll contribution result. It preserves employee-level rows and their
original calculation/basis references, with no re-entry of calculated amounts.
Only explicitly selected registration/month/component groups are included; each
requires an independent row count, amount control, assessed due date and reference
to a retained clean due-date document. Missing groups are not nil populations.
The full parent calculation must be resolved before any group can be prepared.

UAE selection additionally requires one explicit authority, scheme, membership
cohort, nationality, pension-country, sector and jurisdiction scope. Government
support remains a separate payer and cannot be selected as an employer remittance.
The synthetic example therefore prepares **AED 2,200.00** of employee plus net
employer remittances from a **AED 2,500.00** contribution comparison. India keeps
employee PF, employer PF, EPS, ESI, PT and advance-refund components separate.
Dates in the sample controls are fictional inputs, not legal deadline defaults.

The resulting `contribution-obligations/1` source needs independent review and
can feed only the **expected** role of statutory-dues or obligation-bank-allocation
review. It cannot establish a return, payment or bank population. Consumption
rederives its rows and controls against the original reviewed result and retained
due-date evidence. Changing that document stales the expected source and settlement
result without changing the original contribution arithmetic or historical hashes.
Changing an upstream calculation/rule also propagates through the dependency graph.

Canonical obligation sources now support an optional typed `pension_scope` JSON
column. All seven scope fields are mandatory when present, and the field is
restricted to pension components. Both statutory comparison and explicit bank
allocation include that scope in their matching identity. A scoped expectation
cannot be settled against an unscoped return or another authority/cohort with the
same registration, employee and amount. Legacy unscoped obligations retain their
existing identities. CSV values use quoted JSON objects, not executable expressions.

The reviewed-result screen offers independent group controls and due-date evidence
selection. Its format helper leaves amounts and row counts blank. Synthetic JSON
controls and a scoped reported-remittance CSV are supplied in `sample-inputs/`;
they are fixture formats, not qualified country rules or proof of filing/payment.

`contribution-source-full-unit-results.xml` records **1,358 passing backend unit
tests**, with four opt-in connector skips. The two country cases in
`contribution-source-integration-results.xml` verify the complete review → expected
source → independent return/bank/allocation → settlement → export chain, source-role
substitution refusal and due-document replacement staleness. Integration storage,
API, database and job processor are real; scanner and broker dispatch are explicit
doubles. All **133 frontend tests**, type checks, scoped lint and production build
pass. The event listing exposes the expected-role restriction so derived sources
are excluded from return/payment pickers; backend checks enforce it independently.

`contribution-source-browser-results.txt` records the complete UAE/India browser
chain passing in **36.4 seconds** through the owned API and real Redis/Celery worker,
including independent derived-source review and the expected-only picker behavior.
The four `*-contribution-remittance-controls.png` and
`*-contribution-bank-settlement.png` screenshots were visually inspected. The JSON
editors have bounded readable heights so the supplied controls and scope remain
visible. Earlier full-suite receipts are retained as historical evidence; this
focused run does not qualify legal deadlines, native providers or client pilots.

## Published UAE pension profiles

The regulatory library now supports `pension_profile` with the same
`PensionParameters` model used by retained canonical pension-rule sources. Profiles
require UAE scope, wage-month date selection, explicit authority/scheme/cohort
parameters and reviewed fixture receipts. Generic regulatory assessments refuse
this method and direct the user to `uae-pension-review`. The proposal template
contains empty scope fields and null rates; it does not seed a legal pack.

Pension fixture inputs use `pension_basis`, `reported_amount` and independently
specified expected outcomes. Employer-offset fixtures may supply an explicitly
resolved `government_amount`, retained at fils precision, or test the actual
missing-support refusal. The supporting fixture value isolates employer arithmetic;
it does not qualify the government-support scheme. Short-lived versions with no
complete wage month can record blocking-only validation. Publication replays the
approved fixtures and retains the receipt; calculator/schema/runtime changes
invalidate reuse while preserving historical output. Previously published versions
with stale receipts require explicit new versions and independent review.

`POST /intelligence/engagements/{eid}/pension-rule-source` binds selected published
versions to one exact, current, independently reviewed `pension-bases` event and an
independent row-count control. It reuses the India payroll whole-month selection,
source verification, contributor and dependency infrastructure. Each basis needs
one published version matching authority, scheme, membership cohort, nationality,
pension country, employment sector and jurisdiction throughout its entire wage
month. A newer interior-month amendment blocks the original version even when
both month endpoints would select it. Limits remain twenty selected profiles,
5,000 basis rows and one hundred distinct wage months.

The derived source requires independent review and can feed only the pension
workflow's rules role. Calculation rederives it against the original basis event
and current published rules; substituting a different reviewed basis event is
rejected. Results retain global source-copy identifiers separately from engagement
evidence IDs, published version IDs/hashes and the separately resolved government
component. Amendments, withdrawal or source replacement stale dependencies;
historical bodies/hashes remain readable. Multiple published versions retain their
selected wage months so older versions cannot create false overlaps in new months.

The source-preparation UI supports published pension profiles alongside the existing
benefit and India payroll selectors. Profile choices remain paginated and exclude
unpublished versions. Native authority statement readers, qualified legal packs,
salary-basis derivation, filing/payment adapters and client pilots remain open;
published profile mechanics do not establish any of those external qualifications.

Verification: `published-pension-full-unit-results.xml` records **1,339 passing
backend unit tests**, with four opt-in connector skips. The seven tests in
`published-pension-integration-results.xml` cover pension publication and recorded
fixtures, exact basis-event binding, support arithmetic, export, withdrawal and
interior-month amendment staleness, plus existing India payroll, UAE benefit and
manual pension paths. They use a real database, API, private storage and job
processor with explicit scanner/broker doubles. All **129 frontend tests**, scoped
type/lint checks and the production build pass. The additional four tests in
`published-pension-regulatory-regression-results.xml` verify generic fixture
approval/publication and controlled withdrawal after the shared schema extension.

`published-pension-browser-results.txt` records **four passing browser tests in
44.8 seconds** against the owned API and real Redis/Celery worker: published
pension preparation/review/calculation, manual pension comparison, published India
payroll and published UAE benefits. The pension test also checks that the proposal
template starts without a rate or authority and preserves all selected version IDs
in the result. The two `uae-published-pension-*.png` screenshots were visually
inspected. These focused results preserve the earlier full-suite receipt rather
than replacing it with a four-test report.

## UAE pension contributions

`uae-pension-review` adds separate assessed salary bases, retained-document rule
inputs and authority-reported contributions. It reuses canonical CSV preparation,
row/currency controls, private evidence verification, immutable intelligence jobs,
independent source/result review, source-change freshness and XLSX export. All
three sources must be independently reviewed before calculation. India engagements
cannot prepare these pension sources or run the UAE workflow.

Each row declares its pension authority, scheme, membership cohort, nationality,
pension country, employment sector and jurisdiction. No authority or law is chosen
from an employment start date. A salary-basis reference and membership-continuity
reference are required. Salary definitions, reference months, partial-month
treatment and foreign-currency conversion must be assessed before supplying an
AED basis; this comparison does not derive those assessments from gross payroll.

Rules supply explicit rates or fixed amounts, salary caps, minimum supported bases,
effective dates and a fils-rounding method. No statutory rate or ceiling is seeded.
An assessed salary below a reviewed minimum blocks calculation rather than being
silently increased. A rule must cover the entire wage month. An overlapping
partial-month amendment blocks the old whole-month calculation; overlapping
whole-month rules remain ambiguous. Contributions retain unrounded values,
rounded gross amounts, rule versions and document hashes.

Employee, employer and government components remain separate. The optional
`employer-minus-government` formula subtracts only separately resolved government
support for the exact person, employer registration, wage month and pension scope.
Missing support is unresolved, never zero. Explicitly assessed ineligible support
can resolve to zero under its reviewed rule. Support above the employer's gross
contribution blocks calculation. Totals sum employee, **net employer** and
government components; they are not the employer's bank-payment amount.

The three `sample-inputs/SYNTHETIC-pension-*.csv` files use fictional arithmetic
and authority identifiers. Their controls are AED 30,000.03 for the three assessed
basis rows and AED 2,500.00 for reported contributions. The rule CSV deliberately
omits its document ID/hash: select a retained clean rule document during source
preparation, or provide matching original document references yourself. These
examples are not GPSSA, ADPF, Sharjah or GCC legal packs.

`pension-full-unit-results.xml`, `pension-integration-results.xml` and
`pension-frontend-results.xml` record 1,324 passing backend unit tests (four
opt-in skips), six passing API tests and 128 passing frontend tests. API checks
exercise independent sources and final review, exact support arithmetic, export,
document-hash rejection, India exclusion and original-document replacement
staleness. Scanner and broker dispatch are explicit integration doubles; database,
API, private storage and job processing are real. Scoped type/lint checks and the
production frontend build pass. `pension-browser-results.txt` records the new
real Redis/Celery browser case passing in 12.5 seconds, including an XLSX export.
The screenshot `screenshots/native-sources/uae-pension-contribution-review.png`
was visually inspected for the three components, visible scope and readable
amounts. The earlier complete 14-test campaign predates this new workflow; this
focused receipt does not silently replace its full-suite evidence.

At this earlier checkpoint, published pension profiles in the firm regulatory library, legally qualified
authority/cohort packs, native pension-authority statement readers, salary-basis
derivation, filing/payment adapters and consented client pilots remained open.
This increment supports reviewed canonical contribution comparisons and does not
complete those remaining roadmap requirements.

## Recorded rule fixture validation

`VALIDATED` metadata alone no longer qualifies a rule for approval/publication.
Independent approval supplies one to twenty typed `validation_cases` with explicit
expected outcomes and expected-value references. The server runs the actual
checklist/flat-rate evaluator, UAE benefit/pension calculator or India payroll calculator.
Wrong amounts, mismatched kinds, duplicate case IDs and suites without an
applicable case are rejected. Decimal expectations remain independent inputs;
the server never replaces them with its calculated values. Source-copy checks,
proposer/source-uploader independence and the existing publication permissions
remain in force.

`POST /regulatory/rules/{id}/validate` performs a dry check and returns expected
versus actual outcomes. A completed check with mismatches returns HTTP 200 with
`passed: false`; malformed inputs still fail validation. Dry checking does not
approve a rule or advance its lifecycle sequence. The rule's validation-contract
endpoint supplies a typed input schema and an intentionally incomplete skeleton,
with no manufactured expected monetary result. Fixtures belong to the shared
firm rule library and must contain anonymized test inputs.

Approval records the complete cases/outcomes and a receipt bound to the immutable
rule hash, method, trusted implementation and runtime versions. Publication
replays the approved cases and requires the identical receipt. Selection checks
the recorded receipt against the current implementation; code changes or missing
receipts make affected historical work stale and block reuse while preserving
its original body/hash. Previously published versions without such a receipt
require an explicit new proposal and independent approval, not a silent backfill.

The implementation fingerprint includes source files, canonical representations
of the loaded core function code/defaults, and Python/Pydantic/Babel versions.
It excludes object reference counts and absolute source paths. A regression
reproduced an unstable serialization-based fingerprint while a normal payroll
result remained live; the canonical fingerprint now remains stable in that
condition and still detects changed loaded calculator code.

A short-lived payroll amendment that contains no complete wage month may record
a passing **blocking-only** fixture. This verifies the expected refusal and
records zero applicable calculation cases; it does not qualify split-month
arithmetic or invent proration. The preparation/calculation path still blocks
unsupported whole-month use. The UI describes this distinction, shows the recorded
fixture status, and hides a passing preview when the inputs or expectations change.

The gate proves agreement with the supplied examples, not completeness of legal
boundary coverage or authenticity of an expected-value reference. Those references
remain reviewer attestations. No legal pack, representative client-data pilot,
provider qualification or statutory compliance conclusion is certified here.

At the recorded-fixture checkpoint, the backend receipt recorded **1,297 passes
and four opt-in connector skips**. `regulatory-validation-integration-results.xml` records **21 passing API
tests**, including failed/missing fixtures, exact unrounded output, receipt replay,
implementation-change freshness, both profile bridges, withdrawal and existing
reporting paths. Scanner/broker are explicit boundary doubles; the database,
storage and API/job processor are real. Frontend tests record **124 passes**,
including immutable expectations and stale-preview handling. Production build
and scoped lint/type checks also pass. Older checkpoint counts below are historical.

After this gate was added, the complete browser campaign was rerun from freshly
seeded synthetic fixtures against the owned API, database, private storage and
real Redis/Celery worker. `browser-results.json` records **14 passing tests** in
**501.1 seconds**, with **zero failures, skips or flaky results**, starting
25 October 2026 at 08:02 UTC. It includes both published profile bridges,
independent fixture approval/publication and withdrawal, pooled dues payments,
reviewed FX, subsequent bank clearance, import VAT, history beyond 100 events,
PDF provenance, credit applications, India withholding, country isolation,
exports and CSV/XLSX reconciliation. Preparation uses an explicit scanner double;
this campaign does not qualify a production scanner, legal packs or client data.
The accompanying screenshots were refreshed by the same campaign.

Employer-residual fixtures may provide an explicitly resolved pension amount or
test the real missing-pension refusal. The supporting resolved value is retained
at paise precision; it is not rounded using the employer's rounding rule. This
isolates the employer residual and does not itself qualify the pension scheme.

## Controlled rule withdrawal and explicit restoration

UAE and India rules now accept an append-only `withdraw` decision. This requires
`tax.rules.approve`, the Firm Administrator role, the current action sequence and
a meaningful recorded reason. Only a published version can be withdrawn. A newer
draft does not prevent withdrawing an earlier active published version. Source
bytes do not need to be readable or intact to stop using a suspect rule.

Selection stops with `withdrawn_rule` when the highest published version covering
the assessed date has been withdrawn; it does not silently revive an older
version. An older date outside that version's effective range remains separately
selectable. Existing affected result bodies/hashes remain immutable and readable
with stale freshness, and independent approval refuses those stale results.
The existing impact view shows directly dependent results within the caller's
accessible engagements. This is an on-read freshness control, not a background
recalculation or bulk rewrite of existing work.

Restoration requires a new amendment or controlled-revert proposal, fresh
independent approval and publication. The withdrawn version itself cannot be
republished. Controlled reverts now normalize historical optional schema defaults
before comparing content, without rewriting the original stored version or hash.
Source-copy verification and all publication gates still apply to replacements.

The rule screen offers actions for the current lifecycle state and retains a
read-only withdrawal reason, actor and time after reopening the page. Withdrawn
versions retain amendment/revert actions and show affected stale work. The
focused UAE/India browser flow passed in 15.2 seconds; both withdrawal-history
screenshots were visually inspected. Its setup request includes the actual
same-origin header required by the proxy; an earlier missing-header attempt was
rejected rather than weakening that policy.

`regulatory-withdrawal-integration-results.xml` records **14 passing API tests**,
including both country withdrawal cases, role and sequence conflicts, withdrawal
with corrupted source bytes, blocked fallback and stale review, explicit reviewed
restoration, the legacy rule path and published India/UAE profile bridges. Scanner
and broker are explicit doubles; database, original storage and API processing are
real in the owned test environment. The current unit receipt records **1,281
passes and four opt-in connector skips**; frontend tests record **121 passes**.
Production build and scoped lint/type checks pass. This closes a rule-lifecycle
gap; source authenticity, legal qualification and the remaining release gates
are separate requirements.

The workflow selector also now has an explicit accessible label. A combined run
had 13 passes and one timeout locating that visible control; after the label
change, the focused India/UAE profile flows both passed in 28.8 seconds with the
existing timeouts. `workflow-label-browser-results.txt` retains that focused
receipt. This intermediate run is superseded by the current combined receipt
below rather than being counted as an additional passing campaign.

## Published India payroll profiles and complete wage months

The library now supports `method: payroll_profile` and typed `payroll_parameters`
shared with the existing India contribution engine. Parameters retain the rule
group, component, jurisdiction, half-open wage slab, optional salary cap, formula,
exact rate/fixed amount and explicit rounding. PF employee/EPS/employer and refund,
ESI employee/employer and PT remain distinct components. Each stable rule key must
identify its particular component/cohort/slab; amendments retain that identity.
No statutory rates, thresholds or membership decisions are installed by this change.

`POST /intelligence/engagements/{eid}/payroll-rule-source` binds selected published
versions to a current independently reviewed `payroll-bases` population and an
independent row-count control. Every basis needs one matching profile over the
**entire** wage month and its assessed wage slab. Selection checks all published
effective-date and expiry boundaries within that month, including amendments not
selected by the preparer. A short-lived June 10–20 amendment therefore invalidates
the month even if June 1 and June 30 select the same older version. The workflow
requires separate supported assessment of split months; it does not invent daily
proration. Saved regulatory dependencies retain the complete interval and repeat
this check when determining freshness.

The UI reuses the UAE profile-preparation component with India-specific profile,
basis, row-count and endpoint bindings. Select **payroll-rules** in the source
screen; the rule library provides an India proposal template with no supplied
rate, salary cap or threshold. Generic tax assessments disable payroll profiles.
The generated source requires independent review, and the normal worker re-derives
its rows against the original assessed wage population and retained source copies
before using them. A different population cannot reuse the source. The calculation
retains published version IDs/hashes and original firm source-copy receipts in
rows and XLSX; it never treats those copies as engagement evidence versions.
Legacy engagement-document payroll rules continue to work.

Bounds are 20 explicit profiles, 5,000 basis rows and 100 wage months per prepared
population, with at most 1,000 overlapping published versions per rule interval.
Missing, ambiguous or split-month selection blocks preparation. Employer PF still
depends on separately resolved EPS for the same registration, employee, month
and jurisdiction. Wage eligibility, pension continuity, exemptions and wage bases
remain reviewed inputs. EDLI/admin fees, interest, damages, due dates, payment and
filing are not established by the contribution comparison.

`published-payroll-source-integration-results.xml` records **11 passing API tests**,
covering the new May/June profile bridge, interior amendment staleness, independent
review, retained-source publication, legacy India payroll and the UAE benefit
bridge. Scanner and broker are explicit doubles; actual storage, database, API
and job processing are exercised. The focused real-worker browser receipt records
two passes in 24.9 seconds, for India PF/EPS/employer and UAE full-/part-time
benefits. The India preparation and calculation screenshots were visually checked.
At the India bridge checkpoint, the backend receipt recorded **1,277 passes and four opt-in connector
skips**; frontend tests record **121 passes**. Production build and scoped lint/type
checks also pass. A regression also verifies that an older shadowed checklist
with a different period basis does not block a current typed profile under the
same stable key. These remain synthetic workflow proofs; qualified legal packs
and representative provider exports remain open.

## Published UAE benefit profiles and employee calculations

The rule library now accepts `method: benefit_profile` with explicit
`benefit_parameters`. These parameters share their definition with the existing
employee benefit engine: regime, cohort, work model, minimum service, year basis,
salary divisor, tier durations/rates and salary-month cap. No legal defaults are
inserted. Publication retains the normal source-copy, integrity, technical review
and independent content-approval requirements. UAE scope and selection by employee
service-end date are required; unsupported work models and flat-rate or fixed
currency attributes are rejected. Generic assessments reject these profiles and
direct callers to the employee-level workflow rather than returning a benefit
amount without employee evidence.

`POST /intelligence/engagements/{eid}/benefit-rule-source` now prepares a derived
rule source from explicitly selected published profile versions and a current,
independently reviewed employee source. Every supported employee must have exactly
one current published profile matching regime, cohort and work model at their
service-end date. A source may contain different published versions of the same
rule key: explicit service-end selections prevent an older overlapping version
from producing false ambiguity. Unused profiles, missing coverage, conflicting
rule keys and a mismatched independent employee count are rejected. Generic
applicability predicates are rejected for benefit profiles; cohort selection and
its documented professional assessment remain explicit.

In the source screen, select **benefit-rules** to prepare published profiles.
The library also provides a benefit-profile proposal template with no numeric
defaults. Profiles can be selected across library pages; employee source history
retains the existing controls for loading older versions. The generated source
needs independent review before the normal worker calculates benefits. At
consumption, the server re-derives and compares its rows, checks the exact original
employee source and verifies published rules and every retained source copy.
Its contributors include employee preparers, profile proposers and source-copy
uploaders. Original rule IDs, hashes, source-copy IDs and dated rule dependencies
remain in results and exports; global source copies are not presented as
engagement evidence versions. Publishing a later effective amendment makes
affected saved sources/results stale while their original hashes remain intact.

Bounds are 20 explicit profile versions, 5,000 employee rows and 100 distinct
service-end dates per prepared population. Unsupported schemes and work-model
changes still block the employee calculation; no service segmentation, pension
eligibility or legal applicability is inferred. Existing engagement-document rule
sources remain supported. No qualified legal pack has been published by this change.

`benefit-profile-integration-results.xml` records six passing retained-source API
cases, including publication of a fictional typed profile and rejection of a
generic assessment. The scanner is explicitly doubled; storage, tenant permissions,
publication actions and API processing use the owned database and original bytes.
`published-benefit-source-integration-results.xml` records eight passing API cases,
including the legacy engagement-document workflow and the new mixed May/June
version selection, independent review, original-population binding, XLSX export
and amendment staleness. Its scanner and broker are explicit boundary doubles;
the job processor runs against the owned database and retained objects. The
frontend receipt at that checkpoint recorded 120 passing tests; the backend receipt recorded 1,265
passes and four opt-in connector skips. A focused real-worker browser flow passed
in 14.7 seconds, covering full-time and part-time employee calculations and the
source-copy/profile fields. Screenshots are retained as
`uae-published-benefit-preparation.png` and `uae-published-benefit-calculation.png`.
These are synthetic control proofs, not legal or provider qualification.

## Current combined regression

The current combined receipt now records **14 passing browser tests in 8.2
minutes**, after fresh guarded fixture preparation. It includes the published
India payroll and UAE benefit-profile bridges, controlled rule withdrawal and retained-source
publication in both countries, obligation/bank allocations, currency conversion,
subsequent clearance, import VAT/VAT201, history, PDF, credit applications,
withholding, native sources and CSV/XLSX bridges. This supersedes the prior
13- and 12-pass checkpoints and intermediate
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

- [UAE import VAT detail review](uae-import-vat.md): customs/portal/books comparison with separate taxable-base/tax controls, current-version resolution and distinct declaration/adjustment populations. Reviewed selected populations can now feed the books side of VAT201 box comparison with independent controls and review. Native customs/EmaraTax qualification and legal whole-return completeness remain open. Reviewed disjoint canonical book schedules can now be composed across all fourteen explicit VAT201 boxes, with independent whole-schedule controls and fresh source review; the composition does not derive missing/summary boxes or establish filed-return evidence.

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

## India ESIC member, paid-day and wage populations

After the UAE payroll/channel/GL bridges, `india-esic-population` adds an India-only comparison of independently assessed payroll and reported member populations. It reuses controlled canonical CSV evidence, private retained originals, source hashing, independent source review, queued calculations, immutable result versions, exception disposition, approval, pagination, staleness and complete XLSX exports. This is a member/wage audit procedure; contribution calculation and bank/challan settlement stay in their existing separate workflows.

The [official monthly contribution manual](https://portal.esic.gov.in/InsuranceGlobalWebV4/ESICInsurancePortal/Documents/MC_Presentation.pdf) distinguishes wage/day/member inputs from portal contribution calculation and discusses supplementary submissions separately. The [official FAQ](https://www.esic.gov.in/attachments/files/faq.pdf) describes the employer code as 17 digits. These published references informed the canonical evidence fields; they do not establish current portal compatibility, legal eligibility, rates, deadlines or authenticated registry membership. No rates or contribution amounts are inferred from these files.

Prepare two independent `esic-members` sources: `payroll` and `reported`. Each canonical row retains `id`, 17-digit `registration`, `period` (`YYYY-MM`), 10-digit `subject` (IP/member number), `member_name`, whole `paid_days`, nonnegative INR `amount` (wages, at most two decimal places), `zero_wage_reason`, optional ISO `last_working_day`, `evidence_reference` and an assessment. Leading zeroes remain text. Blank optional dates remain unknown, not an invented leaving date. Zero wages require an explicit assessed reason; positive wages use a blank zero-wage reason. Reason values are compared literally; legal reason-code meanings and required-date applicability are not inferred. The canonical contract rejects fractional days, counts exceeding the selected calendar month, and leaving dates after that month; it does not round malformed source values or claim native upload validation.

Declare `expected_rows`, INR wage control totals, `esic_paid_days_control` and `esic_zero_wage_members_control` independently. All four controls must agree with retained rows. Explicit nil sources need the existing nil rationale and zero controls. A completely empty pair cannot establish an employer/month scope. Both sources must be independently reviewed before comparison. Select one employer and one wage month; the month must close by reconciliation date and lie fully within the engagement period. Duplicate members in the same employer/month fail even when their original row IDs differ. The new workflow and source are unavailable in UAE engagements.

Comparison preserves every member in the union of both populations. Missing payroll or reported members block approval and require correction/regeneration, including missing zero-wage members whose absence leaves wage totals unchanged. Matched IDs compare wages, paid days, exact names, assessed zero-wage reasons and leaving dates. A monetary tolerance applies only to wage differences; it never excuses identity, day, name, reason or date discrepancies. Under/overstated wages for different members cannot offset. Multiple monthly/supplementary records are not automatically merged or added: first retain a separately assessed comparable population, preserving originals and the composition assessment. Contribution liability, filing acknowledgement and payment execution are not established by this comparison.

The review page shows employer/month scope, per-source member/wage/day/zero-wage counts and compact member comparisons. **Show source provenance and all columns** reveals reasons, dates and original references. The existing row disposition and independent reviewer controls apply. Withdrawing either source review makes dependent results stale. XLSX retains the full source-linked rows, scope, totals and limitations.

Synthetic examples are in `sample-inputs/SYNTHETIC-esic-population/`: independent payroll/reported CSVs and literal controls. One reported member has 24 paid days against 25 expected days while both wage totals remain INR 10,000. A second zero-wage member and assessed leaving date remain explicit. These are fictional engine fixtures, not real member data or independent professional expected results. The explicit XLS profile below adds native reading; other XLS layouts, portal retrieval, legal rate/eligibility qualification and real client pilots remain open.

Verification for this increment: 1,786 backend unit tests passed (four skipped), including the 5,000-member-per-source bound; 10 payroll HTTP tests passed, including three ESIC cases; all 179 frontend tests passed. ESIC API cases cover mandatory source review, unresolved exception rejection, documented disposition followed by independent approval, paging/export, withdrawal staleness, UAE isolation and an out-of-period wage month. The real Redis/Celery browser flow verifies the retained member/day discrepancy and exposes reason/date provenance; its receipt is `../phase-12/esic-population-browser-results.json`, with `in-esic-{scope,member-comparison}.png` screenshots. Both saved CSV examples were reparsed and compared against their literal expected controls. Production build, typecheck, scoped Ruff/mypy/ESLint and UTF-8 checks passed. The scenario catalogue remains 154 authored synthetic scenarios; this additional workflow coverage is not relabeled as client or legal qualification.

## ESIC populations linked to assessed contribution bases

`india-payroll-rules` now accepts an optional current `esic_population_review_id`, a meaningful `esic_basis_scope_assessment` and explicit `esic_components` (`ESI:EMPLOYEE`, `ESI:EMPLOYER`, or both). The link reuses the existing assessed payroll bases and source-bound contribution-rule calculation. It does not copy observed wages into a legal contribution base or infer eligibility from wages, days, a zero-wage reason or a leaving date.

The selected parent must be an independently reviewed, current, complete `india-esic-population/1` result in the same authorized engagement. Its review date cannot exceed the contribution reconciliation date. All contribution inputs must also be independently reviewed before a linked calculation. Parent exceptions require their recorded dispositions; their count, original observations and disposition comments remain retained in the link even when the contribution calculation matches numerically. An undisposed exception, unreviewed parent or missing payroll/reported member evidence prevents linking.

For every retained member, provide exactly one explicit assessed basis for each selected ESI component, including zero-wage and ineligible members. These rows still carry the existing rule group, jurisdiction, eligibility flag/reference and basis assessment. The employer, month and member must agree exactly; leading-zero identifiers stay distinct. Extra/missing ESI bases, duplicate component bases and reported-only ESI contributions outside this coverage fail. Other PF/PT components can continue through their existing independent assessments without being represented as ESIC evidence. A run covering one ESI component does not claim coverage of the other. The existing 5,000-row source bound remains; large populations can be reviewed by explicitly selecting one component per run.

Each contribution row retains its parent member-row link, both observed wage amounts, days, reasons and dates, assessed base/eligibility, basis assessment and exact base-minus-wage differences. For example, an independently assessed fictional base of INR 8,000 can be retained against INR 10,000 observed wages with a -2,000 difference; no automatic adjustment or statutory justification is inferred. The compact contribution table shows wage/base differences, and provenance/export retains the complete context. The review panel links to the immutable parent and displays selected component coverage and documented population observations. An unlinked ESI calculation remains explicitly **NOT_LINKED** to a reviewed ESIC population.

The parent receipt participates in normal dependency and contributor controls. Withdrawal/replacement of an original ESIC source makes the parent, linked contribution calculation and subsequently derived expected remittance sources stale. Regeneration cannot use that stale parent. This bridge establishes source population coverage only: reviewed legal rules, professional applicability assessment, portal/filing evidence and actual challan/bank settlement remain separate requirements. Synthetic rule rates used in tests are deliberately fictional and are not a country rate pack.

Verification: 1,802 backend unit tests passed (four skipped), all 180 frontend tests passed, and seven ESIC/contribution API tests passed, including the existing UAE/India remittance paths. Binding tests cover explicit component coverage, missing zero-wage bases, other employer/month/member identities, extra reported members, unreviewed parents/inputs, documented parent observations, differing assessed bases, export retention and transitive staleness into expected remittances. Both real Redis/Celery browser flows passed: linked contribution review plus the earlier ESIC member/day comparison. The receipt is `../phase-12/esic-binding-browser-results.json`; inspected screenshots are `in-esic-contribution-{binding,bases}.png`. Production build, typecheck, scoped Ruff/mypy/ESLint and UTF-8 checks passed. These are synthetic fixture results; native XLS/portal support, professional country qualification and independently checked client pilots remain open.

## Native ESIC six-column XLS source

`india-esic-members-xls` adds a bounded India-only native source profile for the six-column Excel 97-2003 member/day/wage worksheet illustrated in the [ESIC monthly-contribution guide](https://portal.esic.gov.in/InsuranceGlobalWebV4/ESICInsurancePortal/Documents/MC_Presentation.pdf). The guide's illustrated headers and its text-cell instructions were visually inspected. This profile is not a claim that the current authenticated portal accepts every historical template or variant. The workbook supplies only the **reported** role of `india-esic-population`; it cannot establish independent payroll expectations, contributions, filing acknowledgement or payment.

Retain the original `.xls` in private evidence and a separate clean employer/month context document. Select native format **India ESIC six-column text XLS**, declare `employer_registration`, `obligation_period`, `esic_return_kind` (`monthly` or `supplementary`), `esic_context_evidence_version_id` and `esic_scope_assessment`. The context must have distinct bytes from the workbook, participates in permissions/contributor controls, and is retained by its actual evidence hash. Declare the existing independent member-row, INR wage, paid-day and zero-wage-member controls. The workbook does not embed a verified employer/month identity; that context remains an explicit independently reviewed assessment.

The supported profile requires one visible BIFF8 worksheet, original headers in A1:F1 and no more than 5,000 member rows. Header prefixes preserve the illustrated column order while permitting explanatory header text and line wrapping: IP number, IP name, paid/payable days, monthly wages, reason code and last working day. Every source value must be a text cell. Numeric/date/boolean/error cells are rejected instead of coercing values or inventing missing leading zeroes. Days require whole unsigned text; wages require plain unsigned text with at most two decimal places. Dates require padded `DD/MM/YYYY` or `DD-MM-YYYY` text. Trailing empty rows are counted but do not become members; internal blank gaps and duplicate IP numbers fail. The existing canonical member validation and all independent controls still apply. The original sheet, physical row, cell text, reason code and date spelling remain retained alongside normalized values.

Zero-working-day reasons are preserved separately as `zero_day_reason`; zero-wage reason assessment remains a separate canonical field. Native reason codes are retained literally, without assigning a legal meaning or deriving membership eligibility. Literal code `0` on a positive-day record denotes no special day reason in this profile; the exact original `0` remains in `source_zero_day_reason` and the original cell receipt. Zero-day or zero-wage records require an explicit reason code. Positive wages with zero paid days do not become zero wages or an invented contribution liability. Last-working-day applicability and the reason-code meaning still require professional assessment. Independent payroll CSVs can populate the optional `zero_day_reason` to compare the corresponding reported code, and its discrepancy is never excused by a monetary tolerance.

The shared reader checks the OLE directory and BIFF record boundaries before materializing cells. It rejects formula records even when a reader could return a plausible numeric cache, macro/module/chart/dialog/hidden sheets, supporting-workbook links/defined names, embedded-object streams, encryption, merged table cells and dimensions exceeding bounds. Hidden table rows/columns are not silently discarded. The evidence upload path uses the same bounded container checks and the existing fail-closed scanner; valid original evidence can still be quarantined until the configured scanner marks it clean. XLS support here does not add general legacy XLS support to the accounting GL importer. The production runtime dependencies are locked `xlrd`/`olefile`; `xlwt` is a development-only synthetic fixture writer. Reader implementation and runtime versions participate in the workflow fingerprint.

Native-source role restrictions are enforced by the server as well as the picker. The source begins unverified and requires independent approval before comparison. Replacing the separate context evidence makes the prepared source and dependent comparisons stale. Supplementary records stay explicitly tagged and are not merged into a complete monthly population. Other XLS layouts/versions, multiple-sheet profiles, authenticated retrieval, portal compatibility, contribution legality and real client qualification remain open.

`sample-inputs/SYNTHETIC-esic-population/` now includes `members.xls`, `native-context.txt` and literal `native-controls.json`. These fictional records retain two leading-zero member IDs, 25 total paid days, INR 10,000 wages and one zero-wage member with a separately retained day reason/date. They are engine fixtures, not real member data, live portal evidence or professional expected results.

Verification: 1,827 backend unit tests passed (four skipped), all 181 frontend tests passed, and 17 ESIC/GST/invoice API tests passed. Tests include a deliberately populated numeric formula cache, which is rejected before value normalization, hidden/macro/dialog/extra sheets, original text identity, controls, dimensions, nil/5,000-member bounds, quarantine, wrong country/role, context replacement, comparison and export. Three real Redis/Celery browser flows passed: original XLS preparation plus independent review and reconciliation, the ESIC contribution link, and the member/day regression. The receipt is `../phase-12/esic-xls-browser-results.json`; inspected screenshots are `in-esic-xls-{scope,members}.png`. The saved XLS was re-imported against its literal controls. Production build, typecheck, scoped Ruff/mypy/ESLint and UTF-8 checks passed. Scanner doubles, synthetic data and local tests do not qualify the live scanner, hosted release, portal or client coverage.

Reader design references: [xlrd's handling of XLS and formula results](https://xlrd.readthedocs.io/en/stable/), [OLE container APIs](https://olefile.readthedocs.io/en/latest/Howto.html), [MS-XLS sheet type/visibility](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/b9ec509a-235d-424e-871d-f8e721106501), and [MS-XLS worksheet/dialog flags](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/ccbd73f9-ff1d-4069-be31-13d16c074ec4).

## Remaining work

Representative bank exports and production WPS variants still need qualification. PDF/OCR bank statements, customs imports, unqualified GSTR-2B pagination profiles, authenticated retrieval, broader GSTR/IMS/withholding/ESIC government formats, additional ECR arrear variants and filing/challan/payment adapters, qualified payroll rule packs across states/cohorts, signed e-invoice verification, live registries and professional country release gates remain open. INV-01 invoice import and the explicit GSTR-2B document profile do not establish IMS action execution or legal ITC eligibility. Monthly ECR parsing does not calculate legal PF dues or establish settlement of a whole challan. The new contribution-review engine computes reviewed input rules; it does not establish their legal applicability. This checkpoint does not close the full original roadmap.

Format references: [SWIFT statement market practice](https://www.swift.com/sites/default/files/files/pmpg-interbank-statement-creation-market-practice-final-version.pdf), [Mashreq WPS upload guidelines](https://netbanking.mashreqbank.com/B001/WPSFileUploadGuidelines_eng.html), [DIB WPS upload walkthrough](https://www.dib.ae/docs/default-source/wps-guidelines/wps-file-upload-walkthrough-for-customers-v1.pdf).

India field reference: [notified e-invoice schema at GSTN-authorized IRP 6](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/). The reader validates reconciliation fields only; it is not an IRP submission validator.

ECR field reference: [EPFO re-engineered ECR user manual v3.0](https://www.epfindia.nic.in/site_docs/PDFs/MiscPDFs/User-Manual-ReECR_v3.0.pdf). The indexed official manual defines the eleven-field monthly member text; direct PDF retrieval was unavailable during implementation. The import validates this explicit reconciliation profile rather than all EPFO submission rules. The example `sample-inputs/SYNTHETIC-india-monthly-ecr.txt` contains fictional members and is not for filing.


Numbered GSTR-2B response assembly now supports the explicit current provider profile with separately retained manifest and original files, independent per-file and whole-population controls, row-level original hashes, request references and mandatory independent source review. Missing provider dates or indices rely on operator batch assessment and do not prove provider origin or a common generation. Token pagination, authentication, checksum verification and client qualification remain open. See [GSTR-2B import](gstr2b.md#numbered-original-response-files) for scope and bounds.


## UAE WPS variable-pay profile

The separate `uae-wps-sif-evp` profile implements the inspected EDR/EVP/SCR layout in the [Emirates Islamic Salary WPS File Creation Guide](https://www.emiratesislamic.ae/-/media/ei/pdfs/business-online/salary-and-utility-payments/ei_businessonline_salary_wps_file_creation_user_guide.pdf), pages 1-4. It is UAE-only and must be explicitly selected; the existing EDR/SCR-only reader continues to reject EVP records. This does not qualify every current bank or exchange-house variant.

Each nonzero EDR variable amount requires an immediately following EVP for the same employee and agent routing. EVP retains housing, conveyance, medical, annual-passage, overtime, other-allowance and leave-encashment amounts. All seven fields must be non-negative, fit the published amount width and have at most two decimal places. The reader checks the component sum against that EDR's variable income. Zero-variable employees may omit EVP; any supplied zero EVP must also close to zero. Orphan, repeated, unknown, mismatched and out-of-order records fail preparation.

Prepare the original clean SIF through **Retained source file** with the explicit EVP format. Declare the employee row count and total salary separately from the independent EVP record count and seven AED component totals. The template leaves values blank; zero components require explicit zero controls. EVP detail never creates extra salary obligations. The SCR count concerns EDRs, and its salary total includes fixed plus variable EDR amounts once. The existing employee, period, IBAN-format/checksum, filename and trailer controls are reused. A 13-digit padded employer ID is required for this profile. Due dates remain explicitly declared rather than inferred from bank format guidance.

Bounds are 10 MiB, 5,000 employees and at most 10,001 physical records including the final SCR. Sources preserve original EDR and EVP record positions, employee-level components and aggregate component controls. The default source view shows fixed/variable salary and total amount; expand **Original source controls and calculation basis** for the component control table and **Show source provenance and all columns** for individual original fields. Retained originals and XLSX remain available. Sources require the existing independent review process and may supply only channel/return/reported roles, never independent payroll expectations or bank settlement.

The fictional [SIF example](sample-inputs/SYNTHETIC-wps-evp/1234567890123260630123456.sif) has two EDRs, one EVP and one SCR. Controls are two employee rows, AED 1,500 total salary and one EVP with AED totals 40 housing, 10 conveyance, 5 medical, 15 annual passage, 20 overtime, 8 other allowances and 2 leave encashment. These are synthetic test values, not a bank-approved salary submission. No account ownership, routing-master lookup, employee eligibility, legal wage calculation, bank acceptance or payment execution is established. Refund/return files and other undocumented bank extensions remain unsupported.


EVP verification receipts: `wps-evp-full-unit-results.xml` records 1,406 passing backend unit tests (four skipped); `wps-evp-frontend-results.xml` records 137 passing frontend tests; `wps-evp-integration-results.xml` records six passing API tests including existing native formats. The EVP integration flow exercises retained original download, independent source review, separate payroll/channel/bank reconciliation, rejection of instruction-as-bank substitution, XLSX export, source replacement staleness and India rejection. The maximum-bound fixture parses 5,000 employees and 10,001 physical records without double counting. The focused browser flow passes through queued native preparation, the seven-component control table in bank field order, salary summary, independent approval and role filtering. Visually inspected screenshots are `uae-wps-evp-source-controls.png`, `uae-wps-evp-component-controls.png` and `uae-wps-evp-salary-summary.png` under `screenshots/native-sources/`. The production frontend build, typecheck, Ruff, selected-module mypy and ESLint pass. These synthetic tests do not close representative-client, bank-acceptance or professional release gates.


## Controlled inventory count-date bridging

The existing `inventory-count-bridge` workflow now offers **Use controlled counts before or after reporting**. Its default forward-only mode remains available. Controlled mode requires current independently reviewed books, counts and movement sources, a review-through date on or after reporting, and an explicit calendar day-end cutoff assessment. A later count must fall within the review window; the direct stock-audit comparison still rejects unbridged future counts.

`stock` and `stock-movements` support an optional `lot` field. Blank means the source does not distinguish a lot; it does not authorize guessing or combining known lots. Matching uses site, SKU, lot, UOM and currency. Counts remain unique by that full partition. Reporting-date books must use the reporting date. Source quantity controls preserve every partition independently; quantities in EA, KG or different currencies are never added into one control.

In source preparation, enable **Declare independent inventory quantity controls** and supply `inventory_quantity_controls`: site, SKU, lot, UOM, currency, exact row count, non-negative positive-quantity total and non-positive negative-quantity total. Both directions are controlled separately, so opposing errors cannot disappear into a zero net movement. Every actual partition must be covered exactly once. An explicitly nil movement file requires the existing nil rationale and an empty control list; a zero-net populated file is not nil. These controls are optional for existing source consumers, but all three sources must have verified controls before controlled bridging. The server rechecks them against retained rows at calculation.

Earlier counts add the retained signed movements through reporting day-end. Later counts subtract movements after reporting day-end through count day-end. The earlier day-end is excluded and the later day-end included. Same-day intraday cutoff is not inferred. A movement without a corresponding count or outside its exact bridge fails; repeated same-partition/date/evidence/quantity observations cannot become extra movements merely by changing a row ID. Opposing lot variances remain separate. The result retains original count quantities and dates, movement IDs, direction, signed applied movement and calculated reporting-date quantity. It does not rewrite original counts.

The screen provides independently paged **Inventory quantity controls** and **Inventory count-date bridges** tables. API detail parameters `inventory_offset`/`inventory_limit` and `bridge_offset`/`bridge_limit` page those lists without changing main result rows; default 100 and maximum 500 apply. XLSX has **Inventory quantity controls**, **Count date bridges** and **Inventory movement links** sheets as applicable. Individual movement links are separate rows rather than a long JSON cell that could be truncated. PDF/DOCX summaries identify the complete XLSX detail rather than embedding an unbounded bridge population into a paragraph.

Coverage uses the uploaded book monetary-value denominator supported by calculated reporting-date quantities. It does not establish financial-statement population completeness, title, reporting-date condition or physical attendance. Original condition and its count date remain in provenance; a quantity bridge cannot establish condition on another date. Unit cost/NRV remain supplied assessed inputs. UAE/India accounting-framework selection, AS/IndAS applicability, audit methodology and professional reporting qualification remain separate. Original evidence replacement makes the source, bridge and downstream approvals stale. No journal, stock adjustment, lender drawing power or tax filing is executed.


Synthetic examples are under `sample-inputs/SYNTHETIC-inventory-count-bridge/`: separate AE/AED and IN/INR books, counts and movements CSVs, each with its independently declared `*-controls.json` list. All six CSVs were reparsed against those controls. Both examples have lot A counted at 9 units on 29 June with a +1 movement to 30 June, and lot B counted at 23 units on 2 July with net +3 movements after 30 June; the derived reporting quantities are 10 and 20. These are fictional operational fixtures and must not be represented as client, physical-attendance or professional-report qualification.

Verification receipts: `inventory-controlled-full-unit-results.xml` records 1,421 passing backend tests (four skipped); `inventory-controlled-frontend-results.xml` records 140 passing frontend tests; `inventory-controlled-integration-results.xml` records two passing country API tests. The tests cover directional controls, missing/incompatible partitions, opposing lot variances, duplicates, nil movements, exact cutoff windows, retained originals, independent review, source replacement staleness, independent API paging and row-level XLSX sheets. A 5,000-link export fixture with 120-character movement IDs verifies that every link survives without Excel cell truncation. The browser flow prepares and reviews signed movement evidence and runs both directions for UAE first and then India, with zero exceptions for both controlled examples. Visually inspected screenshots are `{ae,in}-inventory-source-quantity-controls.png`, `{ae,in}-inventory-bridge-scope.png` and `{ae,in}-inventory-count-date-bridges.png` in `screenshots/native-sources/`. The production frontend build, typecheck, Ruff, selected-module mypy and ESLint pass. Framework qualification, physical attendance, condition/ownership support and representative client pilots remain open.


## India EPFO eight-field arrear ECR

The explicit `india-epfo-arrear-ecr-v2` retained-file profile follows the arrear layout in EPFO's [ECR 2.0 introduction](https://www.epfindia.gov.in/site_docs/PDFs/EPFOUnifiedPortal/Introduction_ECR2.0.pdf). The [EPFO ECR 2.0 FAQ](https://www.epfindia.gov.in/site_docs/PDFs/EPFOUnifiedPortal/FAQs_ECR2.0.pdf) distinguishes the separate arrear file from the monthly file. This implements a structural profile, not universal compatibility with every later re-engineered portal variant. Current-period layout applicability still requires assessment against retained context. The monthly eleven-field reader remains separate.

The eight fields are UAN, display name, arrear EPF wages, arrear EPS wages, arrear EDLI wages, employee EPF, employer EPF and pension contribution. Employer EPF is field 7 and pension is field 8, unlike the monthly file order. Those are separate reported amounts; the reader does not subtract pension from the employer EPF field a second time. Whole-rupee fields, distinct non-zero twelve-digit UANs, member count and wage hierarchy are checked. No rate, wage ceiling, exemption or membership eligibility is calculated.

Choose the arrear format, the retained original text, one assessed establishment and wage month, independent member/derived-row counts and the INR contribution total. Each member creates three rows, including zero components. Supply six independent totals: EPF/EPS/EDLI wages and employee EPF/employer EPF/pension. Wage totals are source-file controls, not repeated component-row sums. Bounds are 10 MiB, 1,666 member lines and 4,998 derived rows. Empty text cannot establish nil arrears.

Retain separate clean evidence for the establishment, member wage-month attribution and salary-arrear disbursement context. Supply that version, the salary disbursement date and a meaningful scope assessment covering every member. The member text does not itself contain those facts. Files spanning different original wage months require separately assessed source populations; the reader never invents a month split or treats the disbursement month as the original wage month. The context is human-assessed retained support, not automatic semantic verification of a portal statement. Its original hash and evidence dependency are retained, rechecked and included in maker/checker restrictions. Replacing context makes the source and dependent comparison stale; a superseded context cannot be silently reused.

Independently review the attributed source before comparison. Select **Compare arrears only, separately from regular monthly dues** and INR for this native profile. Canonical expectation and payment obligation rows must explicitly declare `population=arrears`; regular or unspecified obligation rows cannot clear this comparison. Native monthly ECR rows identify `population=regular`, while existing canonical files default to `unspecified`. The native arrear source can supply only the return/reported role of statutory-dues, India payroll-rule or obligation-bank-allocation review. For payroll-rule comparisons, incremental arrear bases and applicable rules remain separately assessed inputs. The source cannot establish expected dues or contribution bank payment. UAE engagements cannot activate this domestic reader.

Source views show UAN, wage month, population, component and amount with original row provenance available separately. Original controls have a six-field control table. Arrear-only result views compare expectation, return and payment amounts separately, and their scope notice/export cover excludes regular monthly activity. Salary disbursement is not payment of PF contributions. Text does not prove portal acceptance, filing, TRRN/challan payment, identity/master linkage or legal timeliness. Gross wages, NCP and advance-refund fields are absent rather than fabricated as zeros. EDLI insurance, administration/inspection, interest, damages, regular-return composition and current statutory qualification remain separate.

Verification: 1,432 backend unit tests passed (four skipped), 142 frontend tests passed, and three API integration tests passed. The focused browser test passed, covering retained source preparation, independent review, arrears-only comparison and UAE profile exclusion. The three `india-ecr-arrear-*.png` screenshots in `screenshots/native-sources/` were visually inspected. Frontend production build, typecheck and ESLint passed. These are synthetic engineering fixtures; current portal qualification and representative client pilots remain open.


## Reversal bank movements and settlement

The shared transaction table now accepts optional `is_reversal` in controlled CSV/XLSX imports. Use an explicit boolean from the assessed original bank evidence. Omitted values retain the existing unflagged behavior and do not prove that the transaction is irreversible. Native CAMT and MT940 continue to preserve their original reversal indicators and signed balance effects. CAMT rejects empty, repeated or unsupported reversal indicators instead of silently treating them as false.

For UAE first and India, **bank-subsequent-clearance** refuses an allocation to a flagged reversal even when its amount, account, currency and direction agree with an outstanding item. Unallocated flagged movements remain in the result with `REVERSAL_NOT_CLEARANCE`, their original signed amount and the full residual. The reporting-date BRS is unchanged. **obligation-bank-allocations** retains its prohibition on reversed settlement; controlled CSV/XLSX can now carry the flag as well as native bank imports. Its unallocated reversals show `REVERSAL_NOT_SETTLEMENT`. Source provenance and XLSX retain the flags. Neither workflow infers which original transaction a reversal cancels or automatically reopens a previously cleared item. That requires separately assessed retained evidence and a corrected comparison scope.

Verification: `bank-reversal-full-unit-results.xml` records 1,444 passing backend unit tests (four skipped), including native CAMT/MT940 reversal-to-clearance tests, both signed directions, AED/INR canonical imports, unallocated residuals and malformed CAMT indicators. `bank-reversal-integration-results.xml` records four passing API tests covering independently reviewed UAE/India source preparation, reversal allocation rejection, existing clearance/export and source-replacement lineage. Ruff and source UTF-8 validation passed. No legal rate or deadline is introduced by this control.


## Reviewed bank residual carry-forward

The shared **bank-subsequent-clearance** result now offers **Carry reviewed bank residuals into the next clearance window** after independent review. This is available for UAE and India without importing domestic tax assumptions. It reuses retained source events, review, current-version checks and recursive lineage rather than requiring the operator to retype residuals in a new CSV.

The bridge recomputes the saved clearance from its current independently reviewed outstanding, statement and allocation sources. Review comments/dispositions remain on the parent and do not alter calculation fields. A mismatch requires recalculation. Every nonzero outstanding residual is included exactly once; no selection can silently omit an old cheque or deposit. The new balance date is the parent's declared review-through date. Each item keeps its original transaction date, reference, account and currency, signed residual, previous balance date/amount, previously cleared amount and original outstanding date/amount/ID. Repeated windows preserve original age and cannot settle the original gross amount again.

Supply an independently assessed residual count, non-negative positive total, non-positive negative total and a meaningful retained-window/reversal assessment. Explicit zero controls are required. Opposing deposit and payment balances cannot disappear into a zero net control. Bounds are 5,000 residual rows. If the entire retained population has cleared, zero rows and both zero directional totals create an explicitly nil source with the assessment retained as its nil rationale.

All three upstream sources and the parent must be current and independently reviewed. The new source starts unverified and requires its own independent review before it can supply the outstanding role of the next clearance. The next window starts strictly after the carried balance date. Original evidence replacement or withdrawal of an upstream review invalidates the carry-forward and dependent results recursively. Compact source columns show original date, carried balance date, remaining amount and prior-window clearance; full provenance is available through the existing toggle and exports.

The carried residual population is not a full new-period BRS: new-period outstanding items, unbooked statement entries, reversal pairing, continued validity and statement-window completeness require separate assessed evidence. There is no automatic date extension, new liability, journal or payment execution. Professional qualification and representative client pilots remain open.

Verification receipts are `bank-carryforward-full-unit-results.xml` (1,459 passing backend tests, four skipped), `bank-carryforward-frontend-results.xml` (145 passing frontend tests), and `bank-carryforward-integration-results.xml` (two passing country API flows). Unit fixtures cover both currencies and signed directions, offsetting controls, two partial-clearance windows, preserved age, over-allocation, nil residuals, recalculation integrity and the 5,000-item bound. The passing browser flow exercises retained preparation, independent approval and final next-window clearance for UAE first, then India. Six visually inspected screenshots are `{ae,in}-bank-carryforward-controls.png`, `{ae,in}-bank-carried-original-date.png` and `{ae,in}-bank-carried-next-window.png` in `screenshots/native-sources/`. Production frontend build, typecheck, scoped ESLint/Ruff, selected-module mypy and UTF-8 validation pass. API and browser fixtures use the owned disposable database and explicit seed-time scanner/broker test doubles; they do not qualify a real bank integration.


## Payroll accounting allocations to GL balances

The UAE-first, then India **payroll-ledger-rollforward** workflow connects independently assessed payroll accounting allocations to actual posted GL movements and prior-day opening / reporting-date closing controls. It reuses clean retained source files, strict canonical CSV mapping, independent controls and source review, queued calculations, immutable calculation receipts, exception dispositions, current-version checks and existing exports. It complements the separate payroll/WPS/bank and obligation-bank-allocation workflows.

Prepare four independent sources: `opening` and `closing` as `payroll-account-balances`; `payroll` and `posted` as `payroll-ledger-lines`. Independently review every source before calculation. Each source carries the existing independent row-count and complete currency control totals. Those signed source totals are file controls across supplied accounts, not gross salary or a payment conclusion. Posted GL evidence must remain independent from the expected payroll allocation evidence.

Balance fields are row ID, employer registration, account, `account_class` (`expense` or `liability`), currency, normal-sign amount, retained evidence reference and balance date (`as_of`). Expense accounts are debit-positive; liability accounts credit-positive. Opening balances must use the day before the declared accounting-window start; closing balances must use the reporting date. The accounting window may be a subperiod of the engagement, but cannot extend outside it. Missing balances are not zero and block approval; zero balances require explicit controlled records. Accounts with conflicting classifications fail rather than silently reversing signs.

Movement rows add `posting_date`, `wage_month`, `component`, `category` (`accrual`, `settlement` or `adjustment`), subject, original journal/reference and an allocation assessment. Nonzero signed amounts follow the account's normal sign. Wage month cannot start after posting date; historical months remain separate for assessed arrears. All postings must fall within the accounting window. Distinct original line IDs do not excuse duplicated identical accounting observations. Explicit nil movement files require the existing nil rationale. The workflow does not derive account mapping, gross/net allocation, wage month, eligibility, rates or deductions from the GL.

Comparison groups preserve employer, account, currency, wage month, component, posting category and assessed subject. Positive and negative amounts are checked separately: equal opposing extra postings cannot disappear behind a correct net or closing balance. Every supplied account also gets two independent checks: opening plus expected payroll movements versus actual closing, and opening plus posted GL movements versus actual closing. Gross salary, net pay, employee deductions and employer contribution expense/payable can therefore be reviewed separately. Indian domestic PF/ESI/PT/TDS/TCS components are not activated by a UAE engagement. Applicable country rule calculations remain in their separate reviewed workflows.

Subject comparisons also prevent equal account totals from concealing postings to the wrong employee or offsetting under/overallocations between employees. Expected and posted rows use the same independently assessed subject identity. Multiple original journal lines for that subject may match one expected allocation; original journal references, posting dates and line IDs remain in the source links. An aggregate GL journal must first have independently evidenced allocations to comparable subjects. The software does not infer employees from equal amounts or assert that an assessed identifier is an authenticated employee identity. Account rollforwards remain separate aggregate controls, so they can agree while subject comparisons report exceptions.

The subject-isolation increment was checked through 1,763 backend unit tests (four skipped), four UAE/India payroll HTTP tests, all 178 frontend tests and the UAE-then-India payroll browser flow. Unit cases include employee substitution, equal-total cross-employee allocation variances, legitimate split journals and the existing 5,000-line-per-source bound. HTTP cases prepare independently reviewed sources, preserve subject exceptions in paginated results and XLSX, and retain source-withdrawal staleness. The browser receipt is `../phase-12/payroll-subject-browser-results.json`; refreshed posting screenshots show the subject column. Production build, scoped Ruff/mypy/ESLint, typecheck and UTF-8 checks pass. These remain synthetic controls, not employee authentication or independently qualified client results.

Use **Payroll accounting view** to switch independently paginated account balances and posting comparisons. Expand **Payroll posting source links** for separately paginated individual source lines. Each link retains role, source event and row IDs, comparison group, wage month, subject, posting date, component, category, amount, journal reference and evidence reference. XLSX has a complete **Payroll posting links** sheet with one link per row; no unbounded list is placed in a single Excel cell. The source bound is 5,000 rows per input, including up to 10,000 movement links across expected and posted sources.

A settlement journal is not bank execution evidence. Cash/asset accounts, complete balanced journal batches, legal wage/tax/pension calculations, employee population completeness and financial-statement completeness require separate scope and evidence. No payroll, journal, payment or filing is executed. The accounting bridge does not establish a statutory compliance conclusion or an audit opinion.

Synthetic input examples are under `sample-inputs/SYNTHETIC-payroll-ledger/`: four CSVs and one independently declared controls JSON for each country. All eight CSVs were reparsed. The example separates salary expense 1,000, net-pay accrual 900, employee deductions 100, a net-pay settlement posting of -900, and employer contribution expense/payable of 50 each. A separately supplied opening net-pay balance of 200 remains 200 at closing; it is not cleared merely because current payroll settled. These amounts are fictional accounting fixtures, not legal wage or contribution rates.

Verification: `payroll-ledger-full-unit-results.xml` records 1,483 passing backend tests (four skipped); `payroll-ledger-frontend-results.xml` records 148 passing frontend tests; `payroll-ledger-integration-results.xml` records two passing country API flows. Tests cover currency/employer/month/component/category separation, opposing postings, missing balances, bad dates, duplicate observations, review restrictions, independent result/link pagination, exports and withdrawal staleness. A maximum-bound export test retains all 10,000 posting links with long original IDs. The browser flow runs UAE then India and checks five account controls, six posting comparisons and all twelve individual links. Eight screenshots are `{ae,in}-payroll-ledger-{accounting-window,account-balances,direction-comparisons,source-links}.png` in `screenshots/native-sources/`. Production frontend build, typecheck, scoped ESLint/Ruff, selected-module mypy and UTF-8 validation pass. Scanner/broker fixture doubles, the disposable database and fictional inputs do not qualify a provider or client pilot.

Reconciliation workpaper exports also now state source freshness at export and the export timestamp separately from the recorded review status and original result timestamp. Stale historical exports remain downloadable and explicitly say `STALE_HISTORICAL_RESULT_REQUIRES_RECALCULATION`; a previous approval cannot imply current evidence. The export audit event records the evaluated freshness. XLSX, PDF and DOCX freshness labels are tested. This does not change statutory report issuance requirements or upgrade a historical result to current.


## UAE VAT201 emirate layout

The existing VAT201 comparator and reviewed-book-schedule composition now support an explicit `emirate-20` reconciliation layout: Boxes 1a-1g plus Boxes 2-14. The aggregate fourteen-row layout remains separate. This closes the operational gap where offsetting geographic allocations could agree at aggregate Box 1 while disagreeing by emirate. It does not infer legal allocation, tax eligibility, e-commerce qualification or current portal compatibility.

The public FTA [Final VAT 201 Return for e-commerce reporting manual](https://tax.gov.ae/DownloadOpenTextFile?fileUrl=en%2FVAT_VAT_Guides%2FProcess_Final_VAT_return%2FFinal_VAT_return_for_e-commerce_reporting.pdf), July 2023, pages 23-25, was downloaded and visually inspected. It displays the emirate totals and the separate e-commerce/other detail. The [VAT Returns User Guide](https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf) describes geographic reporting; source version and applicability still require assessment. Older software-requirement tables have different non-Box1 numbering and must not be reused as current filing templates. This increment compares assessed emirate totals; it does not generate the separate e-commerce questionnaire or its detailed allocation schedules.

In **Prepare sources**, choose **VAT201 composition layout → Box 1a-1g by emirate - twenty rows**. Retain all seven independently assessed geographic rows, including explicit zeros, and all thirteen other box rows. Use two to twenty current independently reviewed disjoint component sources. An aggregate Box 1 cannot substitute for or be automatically distributed across sub-boxes. Every retained component row participates; duplicates, overlapping boxes, absent emirates, inconsistent periods/TRNs/currencies and amounts not stated to the nearest fils fail the explicit profile. Independent taxable, tax and adjustment totals control the complete composed population. Summary rows are included in those source controls; the totals are not net tax payable. Original component event and row identities remain linked.

In **Compare workflows**, select the same **VAT201 comparison layout**. It fixes the twenty required boxes and disables selected-box exclusions. Both book allocations and independently retained filed evidence must be reviewed before calculation. The profile compares one fifteen-digit TRN and one return period in AED. Missing evidence on either side blocks approval rather than inventing a zero. Sub-boxes and aggregate Box 1 cannot mix. The existing custom assessed subset mode and aggregate profile remain available for their declared scope; a composed twenty-row source requires the explicit twenty-row comparison.

The result shows emirate names, original source links and separate taxable/tax/adjustment differences in form-row order. An equal aggregate total cannot offset an Abu Dhabi difference against a Dubai difference. Independent evidence, source-origin separation, maker/checker, replacement/withdrawal staleness and existing XLSX/PDF/DOCX workpaper exports are reused. India receives neither these UAE layout choices nor the domestic composition workflow. The existing VAT engine's aggregated calculation source is preserved; its retained emirate metadata is not silently spread across unallocated manual adjustments or promoted to independently assessed filing allocations.

`sample-inputs/SYNTHETIC-vat-emirates/` contains two disjoint book CSVs, a matching independent-filed example, an example with offsetting Abu Dhabi/Dubai allocations, and declared controls. All four CSVs were reparsed. The example's complete canonical taxable/tax/adjustment controls are AED 2,400 / 230 / 0, including summary rows. The seven book allocations total 200 / 10; the offsetting filed example reports 120 / 6 and 80 / 4 against book allocations of 100 / 5 each. These are fictional reconciliation amounts, not prescribed rates, authentic filings or tax-payable controls.

Verification: `vat-emirates-full-unit-results.xml` records 1,501 passing backend tests (four skipped), `vat-emirates-frontend-results.xml` records 150 passing frontend tests, and `vat-emirates-integration-results.xml` records four passing API flows including the aggregate-layout regression and India rejection. Fixtures cover missing zero evidence on either/both sides, offsets, duplicate/mixed layouts, fils precision, scope isolation, independent controls/review, export and recursive staleness. The focused browser flow composes reviewed books, obtains independent source approval, locks all twenty required boxes, displays two geographic variances and eighteen matches, and confirms India exclusion. Three visually inspected screenshots are `uae-vat201-emirate-composition-controls.png`, `uae-vat201-emirate-comparison-scope.png` and `uae-vat201-emirate-offsetting-differences.png` in `screenshots/native-sources/`. Production frontend build, typecheck, scoped ESLint/Ruff, selected-module mypy and UTF-8 validation pass. Provider authentication, legal/content qualification and representative client pilots remain open.

The requested pilot-data folder is now `pilot-data/`. UAE and India each have separate redacted-input, independent-expected-result and review-record directories, with unfilled real-pilot manifest templates. Client folder contents are ignored by Git. `pilot-data/synthetic-examples/` separately saves all 148 existing authored scenarios, including original inputs and literal expected results: 100 UAE and 48 India. Each case retains its source fixture hash and explicitly denies real-client or professional-validation status. These exported fixtures do not close the real-client qualification gate.


## India invoice evidence versus filed returns

The India-only **india-invoice-register** workflow compares an independently reviewed purchase or sales register (`books`) with independently reviewed invoice evidence (`invoices`). Select purchase or sale explicitly. Native INV-01 direction must agree with the comparison direction. Both roles reuse the existing tax-document matching engine, source controls, retained originals, exception review and XLSX export. Result rows label `invoices_tax`; the result and export carry the declared direction and explicit filing/IRP scope.

INV-01 is invoice evidence and cannot supply a GST `return` role, even when every amount agrees. Existing invoice-supported `books` remain available in India GST against separate return evidence. A sales INV-01 cannot supply purchase books against inward GSTR-2B. Native invoices are excluded from the new workflow's register role and unsupported workflow roles. Recalculate historical comparisons that used invoices as returns with correctly scoped independent evidence; an old MATCHED result does not establish return filing.

This addition does not implement a native GSTR-1 reader or qualify filing status, IRP authenticity, complete book populations, credit eligibility or a statutory conclusion. Native GSTR-1 still requires a verified format profile and separately assessed filing context. The GSTN [offline tool guide](https://tutorial.gst.gov.in/downloads/invoiceuploadofflineutility.pdf) and [GSTR-1 preparation guide](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm) distinguish preparation/upload from filing.

Verification: `invoice-roles-full-unit-results.xml` records 1,505 passing backend tests (four skipped); `invoice-roles-frontend-results.xml` records 152 passing frontend tests; `invoice-roles-integration-results.xml` records three passing API tests. They cover role rejection, both directions, component amounts, retained originals, independent review, source choices and XLSX export. The passing browser test exercises purchase then sales, direction filtering, five component rows and invoice-specific result labels, and checks that the India workflow is unavailable in UAE. Four inspected screenshots are `india-{purchase,sale}-invoice-register-{scope,comparison}.png` in `screenshots/native-sources/`. Production build, typecheck and scoped static checks pass. API/browser fixtures use the owned disposable database and explicit scanner/broker test doubles; they do not qualify a live government integration.


## India GSTR-1 summary metric reconciliation

The India-only **india-gstr1-summary** workflow now compares independently reviewed book-summary metrics with a retained GSTR-1 summary response. The native **india-gstr1-summary-json** profile follows the first-party [Sandbox summary contract](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/gstr_1), inspected on 25 October 2026. It accepts the documented raw summary object or the explicit two-level successful provider wrapper. It does not issue a live provider request. GSTIN and MMYYYY return period must match the selected entity registration and month. A generated summary does not establish filing or provider authenticity.

The typed `gst-summary-metrics` canonical CSV contract preserves registration, month, section, subsection, subsection nature, counterparty, state code, metric, unit and value. Each supplied numeric observation produces one retained metric row. Section totals, overlapping section variants, subsections and counterparty totals remain distinct identities. `ttl_*` and `act_*` metrics remain separate. `ttl_tax` retains its provider field name; the provider describes taxable value rather than total tax payable. No parent/child, actual/total or counterparty values are added into a liability. Source checksums are retained as supplied values and are not authenticated.

Nineteen documented numeric fields are supported: the returned IGST, CGST, SGST, cess, taxable/value and actual metrics, nil/exempt/non-GST amounts, record counts and document-issued/cancelled/net counts. Four count metrics use `COUNT`; other metrics use `INR`. Counts require non-negative integers. Signed monetary observations are preserved without deriving an amendment offset or a credit-note legal treatment. Every explicit zero remains a row; an absent field stays absent. Unknown numeric/hierarchy fields, unsuccessful wrappers, duplicate node/metric identities, unsupported nesting, invalid dimensions and more than 5,000 metric rows fail closed. The parser does not flatten additional future schema fields silently.

Prepare both sources with a declared row count and **every independently assessed per-metric control** in `gst_summary_metric_controls`. These are arithmetic sums across all supplied hierarchy observations, including overlaps; they are not unique record counts or tax-liability totals. Mixed currency control totals are disallowed for this table. There is no inferred nil return: sources must contain explicit metric observations. Canonical book metrics remain independently prepared evidence rather than a schedule generated from the imported return.

Both sources require independent review before comparison. Native summary evidence may supply only the return role of this workflow and is excluded from book-source choices. The source contract and native format are unavailable for UAE engagements. Comparison is exact even if the generic tolerance is nonzero; offsetting differences in different section paths remain separate exceptions. Missing metrics on either side block approval. A reporting month cannot extend past the reconciliation date. Results retain original dimensions and source row IDs, distinguish `COUNT` from `INR`, and expose no overall liability total. Original replacement stales the dependent result through the existing lineage infrastructure; review and XLSX export reuse the existing services.

Three authored examples are `sample-inputs/SYNTHETIC-gstr1-summary.json`, `SYNTHETIC-gstr1-summary-books.csv` and `SYNTHETIC-gstr1-summary-controls.json`. They contain 23 observations with two deliberately offsetting IGST differences, +1 in B2B and -1 in B2B_4A. The independently authored flat book schedule and literal expected differences remain separate from parser output. These examples are synthetic and do not represent a real client, a filed return or a professionally approved rule pack.

`gst-summary-full-unit-results.xml` records 1,527 passing backend tests (four skipped), including 22 new summary checks. `gst-summary-integration-results.xml` records five passing API tests, covering original retention/download, independent source review, per-metric controls, non-netted differences, export, replacement staleness and UAE exclusion alongside the existing INV-01 and GSTR-2B paths. `gst-summary-frontend-results.xml` records 154 passing frontend tests. Production build, typecheck, scoped lint/mypy and UTF-8 validation pass. API fixtures use the owned disposable database, real API/storage/job processor and explicit scanner/broker doubles.

The three tests in `gst-summary-browser-results.json` exercise numbered GSTR-2B, purchase/sales invoice evidence and the new summary import through the running API and real Redis/Celery worker. The new case checks independent source approval, native-return role filtering, both offsetting differences, count units, XLSX export and UAE workflow exclusion. Three inspected screenshots are `india-gstr1-summary-import-controls.png`, `india-gstr1-summary-hierarchy-comparison.png` and `india-gstr1-summary-document-counts.png` in `screenshots/native-sources/`. The additional passing screenshot run is retained in `gst-summary-screenshots-browser-results.json`. `gst-summary-browser-initial-results.json` preserves the first run, including the evidence-picker selector failure corrected before the passing runs.

This is summary-level GSTR-1 ingestion. Native invoice-level outward sections, invoice-to-summary composition, GSTR-1A/IFF distinctions, independently evidenced filing context, live authorized provider integration, professional qualification and real-client pilots remain open. Earlier entries saying no native GSTR-1 reader was implemented predate this summary-only addition and do not claim invoice-level coverage.


## India GSTR-1 outward invoice/note sections

**india-gstr1-documents-json** imports the explicitly declared `b2b`, `b2ba`, `b2cl`, `b2cla`, `cdnr`, `cdnra`, `cdnur`, `cdnura`, `exp` and `expa` response sections. The India-only **india-gstr1-documents** workflow compares their retained document components with independently reviewed sales-book evidence. It reuses the existing tax-document matcher, immutable source jobs, review, recursive freshness and exports. First-party contracts inspected on 25 October 2026 are the Sandbox [B2B response](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/b2b), [registered notes](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/cdnr), [unregistered notes](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/cdnur) and [export invoices](https://developer.sandbox.co.in/api-reference/gst/compliance/endpoints/taxpayer/gstr-1/documents/exp), with their corresponding amendment schemas. The selected contract field sets are bounded profiles, not a claim of current GSTN portal compatibility.

These section responses omit the taxpayer/period request headers. Preparation therefore requires a separate current clean **request-context evidence version**, an explicit assessed GSTIN/month and a meaningful filtering/pagination/population assessment. Context cannot be the response itself or identical bytes. Its hash, filename, evidence version and contributors become source dependencies; replacement or supersession stales the result. The context document is independently assessed evidence, not an authenticated request log or machine-verified filing proof. No provider session or filing API is called.

Every declared section requires independent document-count, signed taxable-base and IGST/CGST/SGST/cess controls. Whole-source document count, four derived rows per document and the INR sum of tax components must agree to the independent section controls. Required sections must be present even when explicitly empty. Unknown/undeclared sections, aggregate B2CS/HSN/advance data, unsupported wrappers/pagination, unknown document fields, duplicate documents or numbered items, invalid dates and negative raw amounts fail closed. Bounds are ten sections, 1,250 documents / 5,000 component rows, 1,250 records per array, 20,000 rate/item records and the existing 10 MiB original-file limit. Original rate records and all supported document/group metadata remain retained.

Registered groups use their stated counterparty GSTIN. B2CL and unregistered B2CL notes use `UNREGISTERED:POS:<state>`; export invoices/notes use `EXPORT:WPAY` or `EXPORT:WOPAY`. These are declared reporting-category keys, not inferred customer identities. Invoice/debit-note values remain positive; credit-note values are signed negative exactly once. C/D note types are supported; other note-type codes require a separately assessed adapter. Native amounts must be JSON numbers. Rates, differential percentages, IRNs, checksums, source types and source flags are retained without authenticating IRP or recalculating statutory tax.

Amendments retain their original number/date and stay unresolved. Original and amended records are not automatically replaced, netted or treated as incremental tax. Non-neutral record/group flags, source-updater concerns, reverse-charge/pre-GST scope, de-link indicators and unexplained invoice-value differences remain source-review reasons. The published schema defines `d_flag` as **de-link**, so it is recorded as a linkage-review issue. Any remaining source-review reason blocks approval in this workflow. Invoice value is checked against retained taxable value plus tax only to identify additional-amount assessment needs; a difference is not automatically classified as an error or adjusted away. Export-without-payment records carrying tax also require separate assessment.

Both sources must be independently reviewed before calculation. Native GSTR-1 can supply only this workflow's return role; native GSTR-2B stays confined to inward GST. INV-01 sales evidence may supply outward books; purchase evidence is rejected even when its GSTIN/counterparty/amounts would otherwise match. The UI applies the same native-format and role boundaries. Comparisons require INR and a reconciliation date on/after the reporting month end. Result/export metadata retains the selected section controls, request-context reference/hash and assessed retrieval scope, with `NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON` filing status. No withholding, foreign-country rule or payment execution is introduced.

The `SYNTHETIC-gstr1-b2b-*` examples contain separately authored book rows, a retained response, assessed request context and independent controls: one invoice, four component rows, INR 100 taxable value and INR 18 IGST. The `SYNTHETIC-gstr1-ten-section-*` examples retain ten documents, forty component rows and INR 97.20 signed source tax across all ten sections. Their amendments remain unresolved; the signed control is not a resolved liability. Upload/select actual clean context evidence rather than inventing an evidence ID. All seven example files are synthetic; none is client data, provider qualification or professional approval.

Verification receipts: `gstr1-documents-full-unit-results.xml` records 1,549 passing backend tests (four skipped), including 22 new outward-profile checks. `gstr1-documents-integration-results.xml` records eight passing API tests across outward documents and existing GSTR-1 summary, GSTR-2B and INV-01 paths. They verify retained originals/context downloads, review guards, all ten section imports, signed amounts, per-head/base/count controls, XLSX row/metadata preservation, context-replacement staleness and UAE exclusion. `gstr1-documents-frontend-results.xml` records 156 passing frontend tests. Production build, typecheck, scoped ESLint/Ruff, selected-module mypy and UTF-8 validation pass. Integration fixtures use the owned disposable database, real HTTP/storage/job processor and explicit scanner/broker doubles.

`gstr1-documents-browser-results.json` records four passing flows through the running API and real Redis/Celery worker: numbered GSTR-2B, purchase/sales invoice evidence, GSTR-1 summary and the new outward import/review/comparison/export. The new case verifies native return-role restriction, four matched components, retained scope metadata and UAE workflow exclusion. Three inspected screenshots are `india-gstr1-outward-import-controls.png`, `india-gstr1-outward-sales-comparison.png` and `india-gstr1-outward-retained-scope.png` in `screenshots/native-sources/`.

This addition does not close full-return completeness, aggregate-section composition, GSTR-1A/IFF treatment, amendment/current-population resolution, filing-context authentication, live authorized providers, legal qualification or representative client pilots. Earlier summary-only gap descriptions predate this invoice/note increment. The overall roadmap remains open.


## Shared bank booking/value dates — UAE then India

Canonical transaction CSVs now accept `bank_booking_date`, `bank_value_date` and `bank_date_basis`. The comparison `date` must equal a supplied booking date. `BOOKING_DATE` and `ENTRY_DATE_INFERRED_YEAR` require that booking date; `VALUE_DATE_FALLBACK` requires a matching value date and cannot simultaneously assert a booking date. Omitting the new fields preserves the existing declared-transaction-date contract, which still requires independent source review. No account ownership, bank authenticity or payment-execution conclusion is inferred.

CAMT.053 and MT940 reader versions are now `camt053-3` and `swift-mt940-3`. CAMT validates and normalizes separate booking/value date choices, including datetime values; competing or malformed choices fail rather than selecting one silently. A value date may cross the reporting boundary without moving a genuinely booked transaction into a different period. MT940 retains the entry date with an explicit inferred-year label. When no entry date is supplied, the compatibility transaction date remains the value date but is explicitly marked `VALUE_DATE_FALLBACK`. Retained older MT940 entry text without an entry date is also recognized during replay. The distinction between Tag 61 value and entry dates is documented in Citi's [MT940 export guide, section 4.6](https://www.citibank.pl/poland/files/SWIFT_MT940_Export_User_Guide_EN.pdf); this shared adapter does not claim qualification of every bank's profile or year-resolution convention.

The BRS keeps arithmetic and matching results visible but blocks independent approval if either source includes a value-date fallback, even when all amounts match and every financial control is zero. Subsequent-clearance allocations cannot use such a row to establish booking after the reporting cutoff. Explicit booking dates with earlier or later value dates remain separately retained in clearance links. The same guard applies to bank rows allocated against salary/statutory obligations; allocation links retain both dates, and a fallback alone cannot establish a dated obligation settlement. This rule applies to both UAE and India without importing tax rules from either country.

Every bank transaction, including matched items absent from the exception table, has a source-role/row-linked record in the reviewer screen's **Bank transaction dates** table. It has separate bounded API pagination (`date_offset`, `date_limit`, maximum 500), retry/error handling and an untruncated **Bank transaction dates** XLSX sheet. Export summaries preserve the review count and date-record count. Empty exception schedules now show a clear empty-state caption rather than an inverted row range.

Six `SYNTHETIC-{AE,IN}-bank-dates-{books,statement,value-only}.csv` files are saved under `sample-inputs/`. Each file has one signed positive 100 movement in AED or INR. Select account `SYNTHETIC-BANK-1`, reconciliation date 30 June 2026, opening balances zero and closing balances 100. The explicit books/statement pair has booking date 30 June and value date 2 July: zero arithmetic residual, no date blocker. Replacing the statement with the value-only example preserves the arithmetic match but requires booking-date review and blocks approval. These are authored synthetic controls, not independently qualified client expectations.

Verification receipts are under `docs/phase-12/`: `bank-dates-unit-results.xml` records 1,623 passing regression checks with four skipped; this includes 17 focused dual-date checks, the six published CSV examples and UAE salary/India PF allocation-date regressions. `bank-dates-api-results.xml` records eight passing real API/database/job-processor tests across dual dates and existing multipart bank adapters, with explicit scanner/broker doubles. The date tests cover both countries, independent source review, approval refusal, corrected-source approval, 202 date records, independent paging and full XLSX detail. `bank-dates-frontend-results.xml` records 159 passing tests. The production build, selected-module mypy, UTF-8 preflight and scoped Ruff/ESLint checks pass; full ESLint retains its existing unused-variable warning in `uae-business-cases.tsx`.

`bank-dates-browser-results.json` records three passing checks through the running local API: UAE and India fallback blockers, all date pages, independent explicit-date approval, and a read-only check of both countries' reviewed empty schedules after the caption correction. The four inspected screenshots are `ae-bank-date-fallback-page.png`, `in-bank-date-fallback-page.png`, `ae-bank-dates-approved.png` and `in-bank-dates-approved.png` under `screenshots/native-sources/`. The initial browser assertion used `APPROVED` instead of this workflow's actual `REVIEWED` status and was corrected before the passing run; it did not change application review semantics.

This closes the explicit dual-date import/review gap. It does not close bank ownership/authenticity checks, qualification of arbitrary bank PDFs or MT940 variants, client pilot validation, full-return tax composition, legal/rule qualification or the hosted release/rollback gates. The overall roadmap remains open.


## Bank account identity and owner evidence — UAE and India

The new `bank-account-evidence` workflow compares three independently reviewed canonical source populations: the assessed account register, ledger account setup and retained bank evidence observations. It reuses the existing clean-evidence import, CSV column mapping, immutable jobs/events, country selection, source-independence guards, review, recursive freshness and exports. Each source must retain exactly one assertion for the explicitly selected account; duplicate/current-version ambiguity and unscoped extra accounts are rejected rather than silently selected. Non-monetary account evidence uses a row-count control and no money-control total.

The shared record retains the account label, bank country, account scheme/number, routing code, currency, owner country/name, owner-identifier scheme/value, validity interval, declared confirmation status, evidence reference and assessment. The comparison requires an explicit owner-name/identifier scope. The API binds the declared owner name to the engagement legal entity using NFC/case-fold/whitespace name comparison. The owner identifier is independently assessed input evidence; the entity model does not establish its government registration or verify a registry. Legal suffix aliases and punctuation are not silently rewritten. Existing entity-version freshness makes a retained result stale when its entity changes, as verified through the API.

The bank's country selects the syntax profile independently of the owner's engagement country. UAE IBAN observations require the `AE` prefix, 23 ASCII characters, numeric body and valid MOD-97 check digits; an optionally retained three-digit bank identifier must agree to the IBAN. The format is based on the [CBUAE IBAN description](https://centralbank.ae/en/our-operations/payments-and-settlements/regulations-and-standards/iban/). India local-account observations retain their literal account identifier, including leading zeros, and require an IFSC with four ASCII letters, zero in position five and six ASCII alphanumeric characters, following the [RBI NEFT FAQ](https://www.rbi.org.in/Scripts/FAQView.aspx?Id=60). No universal Indian account-number length is invented. ASCII letter case and formatting spaces may normalize; Unicode lookalike letters do not turn into an accepted routing code. An Indian entity's UAE account can therefore use the UAE IBAN profile without acquiring a fictitious Indian routing requirement. Other bank countries or schemes remain explicitly unresolved until their profiles are added.

Wrong owner country/name/identifier scheme/value, account/currency/routing differences, invalid syntax, expired or not-yet-valid evidence, unconfirmed or closed assertions and unsupported bank-country profiles remain visible and block approval. All three source populations must already be independently reviewed. A reviewer cannot override these blockers by accepting an exception; corrected retained sources and a new calculation are required. The selected register is a comparison baseline, not a bank-authenticated owner record.

The reviewer screen presents the three observations side by side, retaining leading zeros and separate source values. A provenance toggle exposes all original fields and assessments. The complete three-row XLSX includes the explicit declared owner scope, syntax-profile references and `bank_authentication_status = NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON`. A declared `confirmed` status, a valid check digit or an agreement across uploaded documents does not establish bank existence, account ownership, signing authority, available funds or payment execution. No bank or registry API is called. This result does not automatically qualify a BRS or release a payment.

`bank-account-evidence-{register,ledger,bank}.csv` provides three synthetic UAE examples. They require an explicitly synthetic engagement whose legal entity name agrees to their declared owner scope; do not relabel real evidence to force a match. The canonical example generator also now saves the existing obligation-allocation examples. The published executable catalogue and pilot example index contain **150 synthetic operational scenarios** (101 UAE, 49 India), including UAE account-observation agreement and an Indian leading-zero mismatch. These are authored expected behaviors, not 150 professionally qualified client cases. Unchanged pilot case files retain their original bytes and historical fixture-source hashes; the index identifies per-file hashes separately from the current generator source hash. Different case content or unexpected metadata still prevents overwrite. Four regression checks verify that preservation behavior.

Verification receipts under `docs/phase-12/`: `bank-accounts-unit-results.xml` records 1,658 passed and four skipped across backend unit, release-gate and deployment-queue checks, including 29 account-profile checks, the two new executable scenarios and four exporter-preservation checks. `bank-accounts-api-results.xml` records eight passing API tests across the new workflow, dual-date BRS and existing country workflows. They use real disposable PostgreSQL, HTTP, private storage and job processing with explicit scanner/dispatch doubles, and verify source-review prerequisites, engagement owner binding, independent approval, wrong-owner blocking, full XLSX scope and entity-change staleness. `bank-accounts-frontend-results.xml` records 161 passing tests. Build, typecheck, scoped ESLint/Ruff, UTF-8 preflight and selected-module mypy pass.

`bank-accounts-browser-results.json` records both UAE and India flows passing through the running local API and real Redis/Celery worker: queue the comparison from current reviewed sources, inspect the side-by-side observations, approve independently, download XLSX, then queue a wrong-owner comparison and verify its approval blocker. Four inspected screenshots are `ae-bank-account-evidence.png`, `in-bank-account-evidence.png`, `ae-bank-owner-mismatch.png` and `in-bank-owner-mismatch.png` under `screenshots/native-sources/`. The local fixtures and source assertions are explicitly synthetic; scanner qualification, real bank/registry authentication, professional/client pilot qualification and hosted release/rollback gates remain open. Full India return composition/amendment resolution and the rest of the original roadmap remain open too.


## Reviewed account links for bank reconciliation and settlements

BRS, subsequent bank clearance and obligation/bank allocations can now retain an explicit `bank_account_review_id` with a meaningful `bank_account_scope_assessment`. The link must identify a current, independently reviewed, unblocked `bank-account-evidence` result in the same authorized engagement. Its selected ledger account, currency and owner country must agree to the financial operation. The account comparison date must equal the operation's review-window end, and all three account-observation validity intervals must cover that window. Lookup reuses recursive source authorization and freshness; callers cannot submit an inline assertion of a verified account review.

The operation defines the relevant evidence window:

- BRS includes the reconciliation date, retained transaction dates and explicit ledger/statement start dates. Nil populations with no retained start date use the reconciliation date; no absent period is inferred.
- Subsequent clearance includes original outstanding-item dates and the declared review-through date. An unrelated broader statement header does not expand the selected clearance window.
- Obligation allocations use the explicitly declared settlement start through the reporting date. Existing allocation checks still require every bank movement to fall within that window; an older obligation month or broader statement header is not a payment date.

This connects the reviewed identity observations to a real ledger/bank identifier difference. For example, books may use `SYN-BANK` while CAMT.053 or MT940 identifies the account by its IBAN or local account number. After the reviewed bank observation agrees to the original native account identifier, the engine maps the statement's account label in an in-memory calculation copy. Canonical bank populations can similarly use the reviewed account number. A canonical population already carrying the selected ledger label is explicitly labelled `DECLARED_LEDGER_ACCOUNT_LABEL_ONLY`; it does not acquire a native-number verification claim. Mixed canonical account identifiers are rejected rather than merged. The bank-country profile remains the account review's UAE/India profile, independently of the engagement's country or currency.

The original source event, account values, native metadata, file bytes, source hashes and row identifiers remain unchanged. The financial result retains the original bank identifier, selected ledger label, mapping basis, covered dates, assessment and the exact account-review event/root/version/SHA receipt. That receipt is a financial-result dependency, and account-result preparer contributors propagate to the financial result's independence checks. Replacing, superseding or withdrawing an underlying account assertion therefore stales the dependent financial result. The immutable historical mapping stays inspectable; it is not silently upgraded to a newer review.

Without a selected link, financial results now explicitly retain `NOT_LINKED_ARITHMETIC_SCOPE_ONLY`. A direct internal calculator call requesting a link without resolving its authorized review retains `LINK_REQUESTED_NOT_VERIFIED` and cannot pass independent approval. A successful link is labelled `REVIEWED_ACCOUNT_DOCUMENTS_LINKED`, while bank authentication remains `NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON`. These states describe retained evidence scope. They do not establish bank existence, signing authority, ownership authenticity or payment execution. Linking does not clear balance-control errors, transaction-date blockers, reversals, partial clearances, late-payment exceptions or statutory qualification.

The UI offers only current reviewed account comparisons, requires a scope assessment when linking, shows paired ledger/original-bank identifiers and the covered window, and opens the exact retained account review. XLSX summary metadata retains the full link receipt and mapping details. Existing workflows and unlinked comparisons remain available with their narrower scope made explicit. Professional review of the financial sources remains separate from the account-document comparison.

Verification under `docs/phase-12/`: `bank-binding-unit-results.xml` records 1,680 passing backend/release/deployment-queue checks with four skipped, including 22 new binding checks. These cover CAMT.053 and MT940 identifiers, immutable originals, all three operation types, date-window boundaries, unqualified/wrong-scope reviews, canonical-label limitations and preservation of native financial controls. `bank-binding-api-results.xml` records 14 passing API tests across account binding, account observations, dual-date BRS and existing country workflows. Six new binding API cases cover UAE and India BRS, subsequent clearance and salary/PF allocations, with explicit scanner/dispatch doubles. They verify original downloads/row values, exact dependencies, independent review, full XLSX metadata, rejection of inline proof data and recursive staleness after source withdrawal.

`bank-binding-frontend-results.xml` records 165 passing frontend tests. `bank-binding-browser-results.json` records two passing UAE/India flows through the running local API and real Redis/Celery worker: map the native bank number to the ledger label, queue and independently approve BRS, download XLSX, inspect the linked account comparison, withdraw its bank assertion and verify that the financial result becomes stale and approval is disabled. Four inspected screenshots are `ae-bank-account-linked-scope.png`, `in-bank-account-linked-scope.png`, `ae-bank-account-linked-stale.png` and `in-bank-account-linked-stale.png` under `screenshots/native-sources/`. Build, typecheck, scoped ESLint/Ruff, UTF-8 preflight and selected-module mypy pass. The initial date-change test expected the old native-control error; the new account-window check rejects it earlier, and its assertion was corrected before the passing API run.

The catalogue remains 150 authored synthetic scenarios. This increment connects retained account evidence to financial workflows; it does not qualify live bank providers, arbitrary statement formats, real client ownership evidence or production release/rollback. Full India return composition/amendment resolution, remaining country-rule qualification, representative consented pilots and the original roadmap's other open requirements remain unfinished.


## Evidenced nil import populations

[UAE nil import review](uae-import-vat.md#explicit-evidenced-nil-import-populations) now supports independently reviewed empty customs/portal/books populations with separate retained scope evidence. Box 6 and Box 7 are declared individually and require exact independently entered zero controls. Undeclared absence remains unknown; current, cancelled or superseded observations contradict nil. Context replacement propagates staleness through derived boxes and downstream VAT201 comparisons. This closes the canonical nil-import bridge gap, while native government qualification and real client evidence remain open.


## India GSTR-1 document series and cancellation counts

The India-only **India GSTR-1 document series and cancellation counts** workflow compares independently reviewed book registers with reported Table 13 series. Each row retains GSTIN, reporting month, document-category code, literal first/last serial identifiers, issued count, cancelled count and net-issued count. Issued less cancelled must equal net issued. Counts are nonnegative integers bounded to one trillion per row and across each controlled source; the bound is an implementation limit, not a legal threshold. Monetary tolerances never excuse count differences. Differences use reported minus books. Duplicate range identities are rejected, and missing ranges remain unknown and block approval. Different ranges cannot offset one another at aggregate level.

The native **India GSTR-1 document issue series JSON** reader accepts the explicit `doc_issue.doc_det[].docs[]` shape with `doc_num`, `num`, `from`, `to`, `totnum`, `cancel` and `net_issue`. Optional `gstin`, `fp` or `ret_period` must agree to the declared request scope; scope missing from a response requires separately retained request-context evidence. A bounded successful `data` wrapper is supported. Unknown fields, other return sections, duplicate categories/row numbers/ranges, changed/deleted flags, inconsistent counts and disagreeing independent controls are rejected rather than silently dropped or combined. Counts may be JSON integers or ASCII integer strings; fractions, booleans and Unicode digits are rejected. Serial identifiers retain leading zeros and letter case.

In **Prepare sources**, select the native profile, the original JSON evidence, GSTIN/month, the separate clean context evidence and a meaningful retrieval assessment. Enter independently checked row count and issued/cancelled/net counts. Count sources have no currency totals. Canonical CSV uses the same `gst-document-series` contract and independent count controls. Both original files are retained and hashed; the context's preparer joins the contributor set, and context replacement makes the native source and downstream comparisons stale. The native source starts UNVERIFIED and can establish only **reported**, never the independent **books** register. Both sources require independent review before matching, and the comparison requires independent review again. Count variances require documented disposition; missing evidence cannot be approved as complete.

The default comparison presents separate book, reported and difference columns for each count, plus literal serial ranges. Full GSTIN/month and source references remain available through the review-details control and exports. This is a document-count reconciliation: it does not expand endpoints into individual invoices, infer serial continuity or overlapping-range validity, map category codes to legally qualified document natures, establish actual cancellation evidence, verify provider authenticity, prove filing or certify complete GSTR-1 coverage. Summary-metric and invoice-value comparisons remain separate workflows. Empty categories do not automatically create zero populations; an explicit zero-count row with blank endpoints can be retained where supported by assessed evidence.

References checked 26 October 2026: the [official GST outward-supplies guide](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm) describes Table 13's total, cancelled and net-issued counts; [WhiteBooks' first-party API profile](https://whitebooks.in/developer/gst-api/put-gstr1-retsave) supplies the document-issue JSON shape. The provider's save-data documentation is not evidence that an uploaded file was filed. Its published example contains placeholders, so the concrete amounts and serial ranges in local examples are independently authored synthetic fixtures, not provider sample transactions. A linked advisory PDF was unavailable; no legal mandatory-filing threshold or date rule is inferred from it.

Examples are `sample-inputs/SYNTHETIC-gstr1-document-series-response.json`, its separate `-context.json` and `-controls.json`, plus `india-document-series-books.csv` and `india-document-series-reported.csv`. Upload the originals and select their actual evidence version IDs; no example contains a fabricated professional approval. The catalogue now contains 152 synthetic scenarios (101 UAE, 51 India), with two new document-series cases; all prior 150 example files preserve their original bytes and source hashes. Counts are synthetic coverage, not representative client qualification.

Verification receipts: `../phase-12/document-series-unit-results.xml`, `document-series-api-results.xml`, `document-series-frontend-results.xml` and `document-series-browser-results.json`. Unit coverage includes cancellation variances despite high money tolerance, offsetting variances across ranges, leading-zero identifiers, explicit zero versus absent category, wrong GSTIN/period/country/currency, exact independent controls, duplicate identity/sequence/category, missing context, unsupported flags/fields/wrappers and prohibited role reuse. Database/API coverage retains original files and context, checks independent review, exports and original downloads, and verifies recursive context-replacement staleness. The two existing bank-date typing errors were corrected with an explicit calendar-date alias; the six changed schema/calculation/parser/service modules now pass mypy without suppressing those errors. Local build, lint, TypeScript and test receipts do not close client, provider, legal or hosted release gates.


Final local checkpoint: 1,677 backend unit tests passed with four skipped; all 170 frontend tests passed; eight retained-file API tests passed across document series and the existing GSTR-1 invoice/summary paths. The browser receipt records one passing real-worker test covering native source preparation, independent review, matching counts, a cancellation variance and XLSX exports. Three inspected screenshots are `screenshots/native-sources/india-document-series-native-controls.png`, `india-document-series-matched-counts.png` and `india-document-series-cancellation-variance.png`. The initial browser attempt used an exact label selector that did not match a wrapped select's accessible label; the selector was corrected before the passing run. Frontend TypeScript, build and scoped ESLint, backend scoped Ruff/mypy and UTF-8 preflight passed. These remain local synthetic receipts and do not substitute for the open country/provider/client release gates.


## India withholding records to split bank settlement

Reviewed `withholding-records` sources can now prepare **expected** or **reported** obligations for the existing **Obligation / reported / bank allocation reconciliation** workflow. This connects TDS/TCS transaction evidence to pooled and partial bank payments without duplicating allocation arithmetic or pretending one cumulative deposit observation represents every challan installment.

In a current independently reviewed India withholding source, expand **Prepare withholding obligations for split bank allocations**. Explicitly select expected or reported purpose and TDS deductor or TCS collector role. Enter the cutoff, independent current-row count and current INR total, plus title and scope assessment. Every observed identity needs exactly one current observation. Superseded/cancelled observations remain linked; a cancelled-only identity, duplicate current observation, future transaction/month or disagreeing control is rejected. The independent current amount excludes historical versions even though the original file's own controls include them. No distinct transaction is silently filtered or aggregated.

Expected rows require current retained rule-assessment evidence, declared transaction coverage and explicit due dates. All source payment dates are rejected: a declared payment date cannot establish bank settlement. Reported sources are separate retained records, not beneficiary certificates. Deductee/collectee credit cannot establish a payer obligation. The bridge preserves registration, counterparty, legal role, TDS/TCS scheme, assessed section/rule reference, tax-year boundaries, reporting month, transaction reference/date and INR. Section, year and transaction remain part of the settlement identity; invoices for the same counterparty and month cannot merge merely because amounts agree.

Derived sources start UNVERIFIED and require independent review. Purpose and cutoff bind each source to its expected/reported role in bank allocation; it cannot establish an unrelated aggregate return workflow. Original source and retained rule evidence remain dependencies. Their withdrawal or replacement makes downstream sources and comparisons stale. The original input-file hash establishes duplicate-file protection. Reusing one parent for both sides is rejected during comparison, even when the derived purpose and row IDs differ and each source was reviewed independently.

Prepare and review expected, reported, bank and allocation sources separately. Use the same cutoff, explicit obligation month range, bank account/currency, settlement window and debit sign. One bank outflow may link to several withholding transactions; one transaction may link to several outflows. Allocations cannot exceed expected liability, reported amount or bank outflow within one review. Approval now checks active obligation allocation reviews within the same engagement against shared bank cash capacity (see the shared cash approval controls below). Firm-wide consumption across separate engagements still needs separate oversight. Partial/overdue residuals remain visible; bank credits and reversed transactions cannot settle liabilities. Bank movements before the withholding transaction and value-date-only fallback observations are rejected. Full scope remains in exports; compact comparisons show section, tax year and transaction reference/date alongside amounts.

This verifies assessed cash allocations. It does not calculate TDS/TCS rates or thresholds, establish legal due dates, generate challans, verify government posting, establish beneficiary credit or map the Income-tax Act, 1961 to its 2025 successor. Literal `206C(1H)` TCS obligations from April 2025 onward retain the withdrawal guard; historical obligations are not rejected merely because bank settlement is later. Other aliases and successor mappings still require professional qualification. The official [TAN challan manual](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/create-challan-tan-login-UM) describes current ITNS 281N and section-wise payments; the [TRACES challan FAQ](https://traces61contents.tdscpc.gov.in/en/faq-dedu-challan-general.html) distinguishes challan consumption from bank payment. The [Finance Act 2025 amendment](https://www.incometaxindia.gov.in/w/section-72-94) supports the retained 206C(1H) boundary. These references do not certify uploaded records or the synthetic due dates.

Examples in `sample-inputs/SYNTHETIC-withholding-split-*` contain fictional expected/reported records, bank debits, allocations and bridge controls. The expected CSV deliberately omits evidence-version IDs/hashes: use the existing retained-rule-document picker to bind a separately uploaded assessment. No example invents an approval or client result. The original source contains three rows totalling INR 1,080; two current observations total INR 180 and the superseded INR 900 remains linked. One INR 150 debit settles INR 100 of transaction 1 and INR 50 of transaction 2; another INR 30 completes transaction 2. Due dates are fictional assessed inputs, not statutory defaults.

The catalogue now has 154 synthetic cases: 101 UAE and 53 India. New cases exercise pooled/split withholding settlement and reject cross-section allocation. All prior 152 example files preserve their bytes and historical source hashes. Verification receipts are `../phase-12/withholding-split-unit-results.xml`, `withholding-split-api-results.xml`, `withholding-split-frontend-results.xml` and `withholding-split-browser-results.json`. Local checks do not close native government-format, legal, consented-client or hosted release gates.


Final local checkpoint: 1,700 backend unit tests passed with four skipped; 173 frontend tests passed; five retained-file API tests passed across the new bridge and existing payer/beneficiary withholding workflows. API checks cover independent review, exports, same-parent reuse rejection, cutoff binding and recursive rule-evidence replacement staleness. One real-worker browser test passed for both TDS deductor and TCS collector preparation, source review, pooled/split cash allocation, comparison approval and exports. Four inspected screenshots are `screenshots/native-sources/india-deductor-withholding-cash-controls.png`, `india-deductor-withholding-split-bank.png` and their collector counterparts. TypeScript, frontend build, scoped ESLint/Ruff, eight-module mypy and UTF-8 checks passed. Shared current-observation selection was reused by the original withholding workflows; the existing pension-scope rejection wording remains compatible. These are local synthetic checks, not client or government-provider qualification.


## Shared bank cash approval controls (UAE and India)

This section records the initial engagement-level checkpoint. The subsequent entity-wide scope is described in the next section.

An obligation allocation calculation records an integrity-bound cash manifest from the original retained bank source. Approval checks other active approved allocation roots in the same engagement under the existing engagement write lock. Concurrent approvals cannot both spend the same available movement. Partial allocations may share its capacity; the same root is excluded when re-reviewed. BRS and clearance assertions do not consume this obligation budget.

Claims survive source staleness and subsequent prepared notes. Explicit rejection or the independent **Withdraw bank cash claim** action releases the claim by appending a new review version with a reason; historical approval is retained. The dedicated action supports stale reviews without revalidating their historical amounts. Tenant, engagement access, maker/checker and expected-version controls still apply. Legacy approvals without manifests are reconstructed from their retained parameters and source; unverifiable claims block approval.

Original source positions protect against remapping row identifiers or account aliases on the same capture. Matching account, currency, date, amount, reference and counterparty conservatively links indistinguishable movements across different captures. Identical rows within one capture remain separate; across captures, ambiguous duplicates may require a combined review or stronger original provenance. Native account headers and linked reviewed bank identifiers improve account identity. Edited transaction fields and unlinked account aliases can prevent economic matching. This is an engagement-level approval safeguard, not a firm-wide bank ledger, bank authentication, government payment acknowledgement or legal qualification.

The review screen displays claim state, conflicts and links to relevant approved reviews, plus the reasoned withdrawal action. Checks are bounded to 1,000 relevant approval roots and 50,000 claims; exceeding these bounds blocks approval for review rather than silently dropping records. Synthetic unit and real PostgreSQL/HTTP tests cover capacity, concurrent approval, stale withdrawal and retained history. Real redacted client comparisons and professional rule sign-off remain pending in `pilot-data/`.


Verification checkpoint, 26 October 2026: backend unit suite **1,722 passed, four skipped**; targeted real PostgreSQL/HTTP suite **six passed** across UAE and India; frontend suite **176 passed**; scoped Ruff/mypy, TypeScript, frontend lint, production build and UTF-8 preflight passed. Lint retains the existing unused-variable warning in `uae-business-cases.tsx`. The real-worker browser scenario passed for both India payer roles, including duplicate-review conflict, independent withdrawal and replacement approval. [Browser result](../phase-12/bank-cash-browser-results.json), [deductor conflict](screenshots/native-sources/india-deductor-shared-bank-cash-conflict.png), [collector conflict](screenshots/native-sources/india-collector-shared-bank-cash-conflict.png), [deductor withdrawal](screenshots/native-sources/india-deductor-shared-bank-cash-withdrawn.png), [collector withdrawal](screenshots/native-sources/india-collector-shared-bank-cash-withdrawn.png). Screenshots were visually inspected. All data remains synthetic; the 154-case catalogue and the real-client/professional/hosted qualification gates are unchanged.


## Bank cash capacity across a legal entity's engagements

The shared approval safeguard now spans every engagement for the same legal entity inside the current tenant, for UAE and India. Audit, tax and payroll engagements no longer obtain separate approval budgets for the same retained bank movement. Each approval, rejection and explicit withdrawal holds an entity transaction lock through commit, in addition to its own engagement lock. Peer inspection does not acquire another engagement write lock. Separate legal entities and separate firms keep independent budgets; no shared bank ownership is inferred from matching account labels across them.

The original version-1 source manifests and historical review bodies remain immutable, including their historical engagement-scope label. New approval markers record `approval_scope=OBLIGATION_APPROVALS_WITHIN_ONE_TENANT_LEGAL_ENTITY` and the entity ID; the live status endpoint reports the effective entity scope. All earlier active approvals participate, including approvals without the new scope marker. Existing cross-engagement conflicts are exposed for review rather than silently releasing or retroactively changing approvals. Source staleness, prepared notes and engagement closure do not release claims. If an engagement is read-only, its existing authorized reopening process is needed before a reviewer can withdraw its claim.

Relevant peer reviews are authorized recursively using their own engagement and source permissions. Authorized reviewers see a link that opens the actual peer engagement and selected retained event, including events outside the first history page. An inaccessible relevant peer blocks approval with a generic authorized-reviewer message; its title, event IDs and engagement ID are not returned. The selected review's claim state remains available so an authorized independent reviewer can still withdraw its own active claim. No additional access is granted by this safeguard.

Entity matching still depends on retained source positions and bank movement fields. Edited movement fields, unlinked account aliases, duplicate legal-entity records, bank authentication, common ownership of bank accounts across entities, provider settlement and government acknowledgements remain outside this control. The 1,000 relevant-root and 50,000-claim bounds apply across the entity. Amount calculations and the frozen 154 synthetic engine scenarios are unchanged.


Verification checkpoint, 26 October 2026: backend unit suite **1,722 passed, four skipped**; targeted PostgreSQL/HTTP suite **eight passed**; frontend **178 passed**; scoped Ruff/mypy, TypeScript, scoped ESLint, production build and UTF-8 preflight passed. Full frontend lint retains the pre-existing unused-variable warning in `uae-business-cases.tsx`. [Two browser scenarios passed](../phase-12/entity-cash-browser-results.json): cross-engagement capacity, related-review navigation, withdrawal and replacement approval for UAE then India; and the existing India TDS/TCS split cash controls through the real worker. The new entity screenshots were visually inspected: [UAE conflict](screenshots/native-sources/ae-entity-bank-cash-conflict.png), [UAE withdrawal controls](screenshots/native-sources/ae-entity-bank-cash-withdrawal-controls.png), [India conflict](screenshots/native-sources/in-entity-bank-cash-conflict.png), [India withdrawal controls](screenshots/native-sources/in-entity-bank-cash-withdrawal-controls.png).

Large retained-history lists remain expensive in this local fixture environment: API logs during the regression showed list requests taking roughly 12–17 seconds under polling load. The direct retained-event link avoids waiting for that dropdown, but this change does not qualify history-list performance. Request-scoped authorization/freshness reuse or bounded batch loading needs its own access, staleness and performance verification. All figures above use synthetic data; real client comparisons, legal/provider qualification and hosted release gates remain open.


## Retained-history request reuse — UAE then India

History listing now opts into a bounded read projection for one actor, tenant, database session and transaction. Repeated read permissions, unlocked read-only engagement lookups, reporting context, immutable-root head versions and operations scope metadata can be reused within that projection. The projection clears on exit, including exceptions; inherited child-task contexts cannot reuse a closed projection. Root transaction or savepoint changes, another actor/tenant/session and subsequent requests bypass or rebuild it. At 512 metadata entries, additional lookups run normally rather than omitting records.

This is not a cache of event authorization results or complete freshness conclusions. Recursive source authorization, record checks, dependency traversal, cycle/depth limits, unsupported-receipt rejection, source integrity and current implementation checks remain in place. Professional write permissions, locked/mutable engagement reads and all approval/rejection/withdrawal requests retain their existing live checks. The source implementation fingerprint includes the new read-projection module, so the existing code-change staleness policy is preserved; historical source/result bodies are not rewritten.

The [paired synthetic benchmark](../phase-12/history-projection-benchmark.json) used the same current implementation and complete 100-row JSON pages with reuse disabled and enabled, in three alternating pairs per country. Every response matched exactly, including historical stale rows, current rows, hashes, labels and pagination cursors. UAE SQL work fell from **2,561 to 350 queries** and local median request time from **1.194 to 0.219 seconds**. India SQL work fell from **2,409 to 349 queries**, with median **1.119 to 0.207 seconds**. These are sequential ASGI/local PostgreSQL fixture measurements for one actor, not a network, concurrent-polling, large-tenant or production capacity qualification. Complex or denied histories can still require substantial uncached work.

Repeat after preparing fresh synthetic preview fixtures and stopping other fixture-changing tests/browser jobs:

```powershell
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py .venv/Scripts/python.exe ../scripts/country_history_benchmark.py
```

The benchmark is guarded to the named disposable test database and explicit synthetic fixtures. It neither changes evidence nor overrides source hashes, implementation receipts or authorization. Only request-local reuse is disabled for the reference. A mismatched response, incomplete/all-stale page, implementation change or insufficient SQL reduction fails the run before saving a new receipt. Prior receipts remain historical evidence and should not be treated as validation of later implementations.

Verification checkpoint, 26 October 2026: backend **1,737 unit tests passed, four skipped**; **11 real PostgreSQL/HTTP regressions passed**, including identical history output, fewer SQL queries, permission revocation without token refresh, evidence replacement, source re-review, cross-engagement permissions and approvals for UAE/India. Scoped Ruff, mypy across seven changed application files and UTF-8 preflight passed. [Three browser regressions passed](../phase-12/history-projection-browser-results.json): UAE/India shared cash approvals, retained sources beyond 100 events, and the India TDS/TCS split-settlement flow through the real worker. The focused older-source browser check also passed after changing its screenshot to capture the retained result panel; its reviewed/current state and source values are visible in the refreshed [older-source screenshot](screenshots/native-sources/older-approved-source-selection.png), which was visually inspected. Frontend application code is unchanged. The 154 synthetic case catalogue, real-client comparisons, legal/provider qualification and hosted release gates remain unchanged.


## Complete text in UAE and India reconciliation XLSX exports

The previous exporter silently shortened a 40,000-character cell to 32,767 characters. This affected large nested allocation links, cash manifests and receipts even when the result population itself was retained. Excel's cell and worksheet limits are documented by [Microsoft](https://support.microsoft.com/en-us/excel/excel-specifications-and-limits). The existing export pipeline now preserves oversized values in continuation records instead of returning a shortened value.

The XLSX text contract is `exact-text-with-continuations/1`. Ordinary source cells retain their existing exact-text convention, including Decimal precision, leading zeroes and formula-like strings. A value exceeding the cell text/line-feed budget receives a reference to **Long values**. That sheet records the value ID, original sheet/cell, ordered part number, part count, original character count, UTF-8 SHA-256 and exact part text. Generated sequence/count columns are integers so Excel sorts them numerically. Source financial values remain text. Parts contain at most 16,000 Unicode code points and 250 line feeds, also staying below a conservative 32,000 UTF-16-unit budget. Arabic, Hindi, emoji and CRLF are preserved without normalization.

To recover a value, select its ID and original source coordinates, require consecutive part numbers from 1 through `part_count`, concatenate `part_text` without separators, and verify the original character count and UTF-8 SHA-256. The value hash covers the exported serialized text; it is distinct from the original evidence hash and result-body hash. Nested dictionaries/lists use the exporter's existing sorted JSON serialization. **Bank cash claims** exposes every retained manifest movement as a separate row for review, including capacity, allocation, account basis and original hash/identity keys. The complete original manifest is still retained through the summary cell or its continuation records. Existing sheet names and source/result bodies are preserved.

Continuation text is bounded to 64 MiB of combined original UTF-8 text per export. Worksheet row/column limits are checked. A limit violation returns HTTP 422 without a downloadable partial workbook; temporary streaming writers are closed through a discarded cleanup archive. Successful downloads expose `X-Export-SHA256`, which the web proxy forwards. The audit event records the actual downloaded content hash and byte count alongside the existing result hash and freshness. The file checksum verifies downloaded bytes; it does not authenticate bank ownership or confer professional qualification. Historical stale exports retain their original values and explicit stale labels.


Verification checkpoint, 26 October 2026: **1,751 backend unit tests passed, four skipped**; **eight PostgreSQL/HTTP regressions passed**; **178 frontend tests passed**; scoped Ruff/mypy, TypeScript, ESLint, production build and UTF-8 preflight passed. Unit cases reassemble 5,000 claims and nested allocations for each country and verify exact hashes, large Decimal strings, leading zeroes, formula-like text, Arabic/Hindi/emoji, line-feed/UTF-16 boundaries, CRLF and explicit limits. HTTP cases verify current and stale 500-payment exports, all original manifest/link records, downloaded-byte checksums, persisted audit hash/size and 422 without partial downloads. [Two browser scenarios passed](../phase-12/lossless-export-browser-results.json), covering actual UAE/India downloads through the web proxy and the existing India TDS/TCS flow through the real worker.

The saved application-generated workbooks were independently imported and rendered for visual inspection: [UAE claim rows](screenshots/exports/ae-claims.png), [UAE continuation records](screenshots/exports/ae-long-values.png), [India claim rows](screenshots/exports/in-claims.png), [India continuation records](screenshots/exports/in-long-values.png). This verifies saved-file readback and the shown ranges, not native Excel application certification. No workbook formulas or existing financial source values were changed. Statutory-report exports retain their separate exporter; this checkpoint covers the shared reconciliation/intelligence exporter. All data remains synthetic, the 154-case catalogue is unchanged, and real-client, legal/provider and hosted release qualification remain open.


## Complete statutory reporting-pack exports — UAE then India

The separate statutory reporting exporter now uses the same complete-text writer as reconciliation exports. It preserves oversized legacy narrative/receipt values and full nested table cells through **Long values**, rather than abbreviating table fields at 30,000 characters. **Complete source chunks** remains the full source-data view. Resolve any continuation reference first, then concatenate chunks in numeric order within each block and parse the JSON. Generated chunk numbers are numeric; original source figures, identifiers and draft status keep their existing representation. Current template narrative and resolved-package limits are unchanged.

Reporting metadata now carries the actual export timestamp, source freshness and historical/current/unknown export status in XLSX, PDF and DOCX. It keeps these separate from template review, report review, framework configuration and **DRAFT — NOT SIGNED OR FILED**. Unknown freshness is not labelled current. Stale reports can be downloaded as historical evidence with their original embedded data; stale templates/sources still cannot generate new reports. Neither signing nor filing is supplied by this change.

Source data reconstructed from the pack is checked against the original retained body and its original dependency receipts. The event SHA-256 binds both body and dependencies; hashing the body alone is not equivalent. The continuation checksum instead covers the serialized value text, while the existing download checksum binds the saved workbook bytes. Export limits use the shared 64 MiB continuation budget and worksheet bounds, returning 422 without a partial download. The existing 20 MiB resolved-report source limit, independent source/template review and country-category checks remain in force.

Verification checkpoint, 26 October 2026: **1,758 backend unit tests passed, four skipped**; **five PostgreSQL/HTTP regressions passed**; scoped Ruff/mypy and UTF-8 checks passed. Tests cover legacy long fields, Unicode/raw source chunks, complete nested cells, original source-envelope hashes, wrong-country rejection, unreviewed and stale template rejection, current/stale reporting packs, explicit export-limit failure and draft/freshness labels in all three formats. Application-generated 500-payment UAE and India workbooks were independently imported and visually inspected: [UAE review metadata](screenshots/statutory-exports/ae-review.png), [UAE continuation controls](screenshots/statutory-exports/ae-values.png), [India review metadata](screenshots/statutory-exports/in-review.png), [India continuation controls](screenshots/statutory-exports/in-values.png). This is saved-file/readback and selected-range rendering evidence, not native Excel application or legal-form certification. The local preview now includes draft statutory reporting-pack examples built from the existing reviewed large reconciliation sources. Frontend application code is unchanged.

All examples remain synthetic; unconfigured reporting frameworks remain visibly unconfigured. These export controls do not qualify complete Section 44AB/Form 3CD, CARO, Schedule III, SOX or UAE audit/filing content. The original country implementation, client validation, provider and professional release requirements remain open.
## Inventory valuation evidence and recorded GL controls — UAE then India

`inventory-valuation-control` complements the existing stock audit and inventory
count bridge. It consumes three independently reviewed sources: books (`stock`),
price assessments (`inventory-valuations`) and recorded GL (`accounting-controls`).
Books require independent directional quantity controls and an account mapping.
Valuations require independent row counts and separate extended cost and NRV
totals per currency. [Synthetic AE and IN inputs](sample-inputs/SYNTHETIC-inventory-valuation/README.md)
include literal controls and clearly fictional supporting documents.

Each valuation binds retained cost and NRV document version IDs and SHA-256
hashes, with source references, observation dates and a human assessment. Shared
document selectors can fill blank CSV IDs/hashes; conflicting supplied bindings
fail. Supporting documents must be distinct from the assessment CSV. Their
actual retained bytes are checked during source preparation and consumption;
replacing them makes dependent results stale. Hashes identify bytes, not
authenticity or the correctness of an assessment.

Exact site/SKU/lot/UOM/currency positions remain separate. Missing evidence,
quantity disagreement, unconfirmed ownership, negative book quantity or a
different book reporting date blocks completion. Unit cost and unit NRV
differences cannot be hidden by GL agreement or monetary tolerance. NRV is the
assessed selling price less completion and selling costs; negative NRV remains
unresolved, with no automatic zero floor or liability recognition. An entirely
empty population does not qualify nil inventory through this workflow.

The reviewer explicitly selects gross recorded cost or recorded lower-of-cost-
and-NRV as the GL basis. Recorded book values are compared separately with GL
account/currency balances at the reporting date; assessed prices are never
substituted into recorded GL values. The declared monetary tolerance applies
to that GL comparison. Missing recorded NRV under a net basis leaves the
recorded value unknown. There is no FX conversion, UOM conversion or netting
between positions. A declared review-through date bounds observations, while
the human assessment explains their relevance to the reporting date.

The UI independently pages valuation tests and GL controls so a GL exception
remains accessible beyond the first 100 positions. Exports and approval operate
on the complete retained result. Tests cover the maximum 5,000-position source,
independent review, document tampering, staleness, scoped pagination and export.

This shared procedure is exercised for UAE before India. Applicable framework,
cost policy, evidence reliability and recognition require independent judgment.
See the official [IAS 2 overview](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/)
and [ICAI AS 2 text](https://indasaccess.icai.org/Volume-III/AS/asb.html?a=105)
for the underlying concepts; neither establishes automatic applicability to an
entity. No tax valuation, title verification, physical count, drawing-power
certification, statutory opinion or posting is supplied. Statutory qualification
remains false. Client pilots and professional country/framework validation remain open.

Verification checkpoint, 26 October 2026: 1,851 backend unit tests passed,
four skipped; four inventory PostgreSQL/HTTP tests and 183 frontend tests passed.
Scoped Ruff/mypy, ESLint and the frontend production build passed.
TypeScript and UTF-8 preflight passed. Both saved country example sets were
parsed back and their controls and expected results verified. The
[real-worker browser scenario](../phase-12/inventory-values-browser-results.json)
passed for UAE then India; the saved valuation and GL views were visually
inspected: [UAE valuation](screenshots/native-sources/ae-inventory-value-tests.png),
[UAE GL](screenshots/native-sources/ae-inventory-value-gl.png),
[India valuation](screenshots/native-sources/in-inventory-value-tests.png),
[India GL](screenshots/native-sources/in-inventory-value-gl.png).

## Complete uploaded-list screening candidates — UAE then India

The existing `sanctions-name-review` workflow previously counted all candidates
but retained only its first 20 hits per subject. It now retains every candidate
within the existing 100,000 subject/list comparison bound. Results identify
`complete-screening-candidates/1`; each hit includes the list row ID, list subject
ID, original list name, list version, publication date, declared evidence reference
and baseline similarity score. Original subject names and evidence references
are retained too. Ordering remains descending score, then exact source row ID.

The review screen has a separate candidate view with 100-hit pages and a subject
selector for the current schedule page. Schedule pagination reaches additional
subjects. This prevents a large candidate list from turning the summary schedule
into one oversized JSON cell. No candidate is cleared by pagination, and zero
hits still require independent review. Subject-level dispositions must assess
all candidates; this increment does not create individual candidate decisions.

XLSX retains the complete nested original and adds a **Screening candidates**
sheet with one row per subject/candidate pair. Existing complete-text continuation
records preserve nested values beyond Excel's cell limit. Historical truncated
results keep their original data: the UI warns that a rerun is required and the
candidate sheet labels their rows `LEGACY_TRUNCATED`. Older results without the
new contract remain `LEGACY_UNQUALIFIED`, never relabelled as complete.
Independent approval rejects truncated or count-inconsistent candidate sets,
even when all visible subject exceptions have documented dispositions. Historical
exports remain available with their original data and incomplete labels.

This is a shared uploaded-list name baseline exercised for UAE before India.
The supplied list is not an authenticated current UAE, India or global provider
feed. References remain declared references; no linked registry verification,
transliteration, identifier-based matching, automatic sanctions clearance,
onboarding decision or legal qualification is added. Source authenticity,
completeness, threshold assessment and independent adjudication remain required.

Verification checkpoint, 26 October 2026: the final serial backend run passed
**1,858 unit tests, four skipped**; both UAE/India PostgreSQL/HTTP tests passed;
**186 frontend tests** passed. Scoped Ruff/mypy, ESLint, TypeScript, production
build and UTF-8 checks passed. Unit tests exercise all 100,000 retained hits at
the comparison bound and reject an excess population. HTTP tests retain all
201 candidates per country, verify the last hit and source reference, and
reassemble the original nested candidate JSON through XLSX continuation hashes.
Historical incomplete retention cannot be approved by documenting visible rows.

An earlier concurrent full-unit run had one local PDF extraction worker failure
(invalid Windows handle followed by timeout). Its two extraction tests passed
on isolated recheck, followed by the clean serial full-suite result above. No
extraction code or timeout was changed; hosted extraction/recovery qualification
remains separate from these local results.

The [real-worker browser scenario](../phase-12/screening-candidates-browser-results.json)
passed for UAE then India, paging through candidates 1–100, 101–200 and 201.
Saved screenshots were visually inspected: [UAE last candidate](screenshots/native-sources/ae-screening-candidates.png)
and [India last candidate](screenshots/native-sources/in-screening-candidates.png).
All names and source records in these checks are synthetic. The frozen
154-scenario catalogue is unchanged; real-client and professional/provider
qualification remain open.

## Independently controlled procurement quantities — UAE then India

The existing `procurement-match` workflow now requires explicit units and
independent quantity controls for order, receipt and invoice sources. Source
preparation verifies row counts and quantity totals separately for each exact
order/line/vendor/currency/UOM/document-type partition. These controls are
separate from the existing per-currency monetary controls. Split receipts or
invoices can share a partition when their independent count and quantity agree.
Payments do not supply goods quantities. All four sources must be independently
reviewed before comparison; old sources without controls require new preparation.

Identical numeric quantities in PCS and KG no longer establish agreement. The
result retains each source row's original unit and quantity, marks the position
`NOT_COMPARABLE`, and leaves its aggregate quantity comparison empty. It remains
blocked even after an exception disposition. Exact units include case and code:
EA and PCS are not silently converted. Source controls are reverified when the
workflow consumes them, not trusted solely from a saved verification flag.

Unit price differences are now exact tests. For example, a change from 100 to
99.999 on one million units is flagged even with a 0.01 money tolerance; the
previous unit-price tolerance could conceal a 1,000 extended-value difference.
The money tolerance still applies to document extensions and invoice/payment
amount comparisons. Quantity differences are exact and cannot be excused by
that tolerance. Draft-payment segregation checks require both nonblank preparer
and approver identities, with distinct trimmed values. Existing document holds,
bank-verification assertions and matching exceptions remain draft holds.

Results identify `controlled-purchase-quantities/1`. Historical procurement
results without this contract remain available, but cannot receive a new
independent approval; regenerate them from current controlled sources. Existing
historical approvals are not rewritten. Independently paged source-control views
and a **Purchase quantity controls** XLSX sheet preserve the full declared
partition population beyond the first 100 rows. Result provenance retains all
original source row IDs and unit observations.

This is shared procurement evidence logic exercised for UAE before India. It
does not calculate UAE VAT/India GST, authenticate supplied approvals or bank
ownership, authorize payments, infer unit conversions, or handle returns,
tax-inclusive pricing and service acceptance automatically. Payment proposals
remain drafts without payment instructions. [Saved AE/IN examples](sample-inputs/SYNTHETIC-purchase-quantities/README.md)
are synthetic and separate from the real pilot folders. The frozen 154-case
catalogue is unchanged; legal/provider, client and hosted qualification remain open.

Verification checkpoint, 26 October 2026: **1,880 backend unit tests passed,
four skipped**; **188 frontend tests passed**; four new PostgreSQL/HTTP tests
and the existing connected procurement/bank-revision regression passed.
Scoped Ruff/mypy, ESLint, TypeScript, production build and UTF-8 preflight passed.
The saved AE/IN CSVs were parsed back with their literal controls and expected
quantities. Unit tests cover 5,000 distinct control partitions, split receipts,
wrong partition/count/quantity controls, absent source controls, different units,
exact price/quantity tests and missing/equivalent preparer identities. HTTP
tests verify independent review, incompatible-unit approval rejection even
after disposition, all 121 control partitions across separate pagination and
the complete control XLSX sheet. The older connected flow was rerun without
rewriting its historical public receipt; the current local receipt is retained
in the private verification runtime.

The [real-worker browser scenario](../phase-12/purchase-quantities-browser-results.json)
passed for valid and incompatible-unit cases in UAE, then India, including the
source-control view. Initial screenshots revealed oversized JSON cells; these
are now labelled role/value lists with wrapped exception text. The final browser
check requires the disposition button to fit entirely in the viewport after
scrolling to the schedule. Final screenshots were visually inspected:
[UAE matched](screenshots/native-sources/ae-purchase-valid.png),
[UAE incompatible units](screenshots/native-sources/ae-purchase-bad_units.png),
[UAE controls](screenshots/native-sources/ae-purchase-controls.png),
[India matched](screenshots/native-sources/in-purchase-valid.png),
[India incompatible units](screenshots/native-sources/in-purchase-bad_units.png),
[India controls](screenshots/native-sources/in-purchase-controls.png).

## Positive party-balance confirmations — UAE then India

`party-balance-confirmations` complements the existing invoice-level
`balance-confirmations` workflow. One explicitly scoped customer or vendor
balance can now cover many invoices and credit notes without inventing a
separate response allocation for each invoice. Three independently reviewed
sources are required: reporting-date `audit-open-items`, `balance-controls`
using the declared subledger normal sign, and current `party-confirmations`
assessments. The source control totals cover requested balances separately
from mandatory independent written-response totals. A zero written response
is retained as zero; a non-response remains absent, not zero.

Each position is exact account/counterparty/receivable-or-payable/currency.
Accounts, parties, sides and currencies cannot offset one another. GL control
agreement does not clear party response differences. The requested amount must
equal the scoped book balance exactly, independently of the response comparison
tolerance. Request, response and follow-up dates cannot be after review-through, and a
follow-up cannot precede its request or response. Duplicate current assessments within the selected source,
unknown parties, different dates/scopes, missing GL control agreement or missing
reliability declarations remain unresolved. A raw credit-signed payable GL is
not automatically flipped to force agreement.
For an unknown party the observed response stays visible, but book balance and
difference remain unknown; no difference is calculated against an invented zero.

Sent requests and observed written responses require retained version IDs,
SHA-256 hashes and source references. Follow-ups require a dated retained
document, reference, procedure kind and meaningful assessment. Shared document
selectors can fill blank CSV bindings; conflicting supplied bindings fail.
The assessment CSV cannot act as its own correspondence. Original clean bytes
and current versions are verified on preparation and consumption. Replacing a
supporting document makes the source and dependent result stale. The existing
50-distinct-document / 100 MiB supporting-evidence bound applies per prepared
source; batch documents may support several explicitly referenced positions.
Partition larger document sets deliberately. Canonical CSV remains bounded to
10 MiB and 5,000 rows per source.

Pending, unsent and undeliverable requests require actual alternative-procedure
evidence. A response classified as unreliable retains its observed amount,
date and document while requiring alternatives. A dispute remains a dispute even
if its amount equals books. Other response differences require documented
investigation. Bound follow-up evidence permits independent disposition; it
never changes these rows to automatically confirmed. A comment alone cannot
clear missing follow-up evidence or hard scope/GL/independence blockers.

The UI separates party evidence and GL control pages. Its evidence panel shows
dates, assessed declarations, references and hashes, and downloads only through
the existing authorized, hash-verified evidence route. All linked item IDs have
their own pages. XLSX preserves the complete original result and adds
**Confirmation item links** and **Confirmation documents** sheets with one row
per item link or contextual document binding. Document rows explicitly identify
retained identity, not authentication or evidence sufficiency.

This contract covers declared positive stated-balance evidence. It does not
send requests, authenticate a respondent, infer country-standard applicability,
qualify negative/blank requests, automatically allocate partial responses,
infer unit/currency conversions, or issue an audit opinion. Completeness of the
client population, response coverage and reliability need professional review.
Positive denotes the request method, not the amount's sign; net credit balances
remain signed. Every book-party position in the supplied population requires
an assessment row. Sampling/exclusions and selection completeness are not inferred.
The [IAASB 2026 Handbook](https://www.iaasb.org/news-events/2026-10/iaasb-2026-handbook-now-available-online-access-and-print-orders)
and [ICAI SA 505](https://kb.icai.org/pdfs/PDFFile5b3b5643c27186.05385959.pdf)
are professional references; their applicability and edition must be selected
for the actual engagement. This source-evidence workflow is not qualification
of ISA/SA compliance or local UAE/India statutory content.

[Saved examples](sample-inputs/SYNTHETIC-party-confirmations/README.md) cover a
received customer response and pending vendor with alternatives in AE/AED and
IN/INR. Every file is synthetic and separate from client pilot evidence. The
frozen 154-scenario catalogue is unchanged. Real-client, professional/provider
and hosted release qualification remain open.

Verification checkpoint, 26 October 2026: **1,913 backend unit tests passed,
four skipped**, **192 frontend tests passed**, and **eight PostgreSQL/HTTP
regressions passed**. Scoped Ruff/mypy, ESLint, TypeScript, production build and
UTF-8 checks passed. Coverage includes customer/vendor positions in both
countries, signed credit balances, confirmed zero, absent/unreliable responses,
equal-amount disputes, offsetting party errors, missing/unknown scope without
invented zeroes, future follow-ups, hash mismatch, self-evidence, independent
review and document replacement staleness. Unit/export checks retain all 5,000
item IDs for one letter. HTTP checks retain 121 party positions, separate GL
pagination, 363 item-link rows and 242 contextual document rows in XLSX.

All four saved example populations were parsed back against their literal
controls and expected states. Supporting TXT files use pinned UTF-8/LF bytes
for portable published checksums; this affects synthetic examples only, not
uploaded client originals. The [real-worker browser scenario](../phase-12/party-confirmations-browser-results.json)
passed customer written-response and vendor alternative-procedure flows in UAE,
then India. Actual browser downloads of response/follow-up files matched their
retained SHA-256 hashes. Final screenshots were visually inspected:
[UAE customer schedule](screenshots/native-sources/ae-party-received_customer-schedule.png),
[UAE customer evidence](screenshots/native-sources/ae-party-received_customer-evidence.png),
[UAE vendor schedule](screenshots/native-sources/ae-party-alternative_vendor-schedule.png),
[UAE vendor evidence](screenshots/native-sources/ae-party-alternative_vendor-evidence.png),
[UAE GL](screenshots/native-sources/ae-party-gl.png),
[India customer schedule](screenshots/native-sources/in-party-received_customer-schedule.png),
[India customer evidence](screenshots/native-sources/in-party-received_customer-evidence.png),
[India vendor schedule](screenshots/native-sources/in-party-alternative_vendor-schedule.png),
[India vendor evidence](screenshots/native-sources/in-party-alternative_vendor-evidence.png),
[India GL](screenshots/native-sources/in-party-gl.png).


### Blank positive requests and partial replies — UAE then India

New party-confirmation runs use `positive-party-balance-confirmations/2`.
Existing saved results retain their original contract. Blank requests require
an explicit assessed scope balance, an absent written request amount and
separate independent controls for scope, actual written request amounts and
actual responses. Neither a missing amount nor a missing response becomes zero.

An optional reviewed `confirmation-item-coverage` CSV declares the exact
assessment/item links for a partially received reply. Links must match the
party, account, side, currency and reporting date, and include a source
reference. Duplicate links, unknown items, other-party items and links to
full-response assessments fail preparation/calculation. Amounts never infer
item membership. A partial reply covering every item remains a classification
error. Missing mappings remain unknown and block approval.

Valid partial replies compare only the explicitly covered items. Remaining
item IDs and their signed book balance remain visible, including a zero-net
remainder. Retained partial-response follow-up and independent exception review
are required. API links have independent `confirmation_link_offset/limit`
pagination; XLSX retains every link and labels membership without claiming
confirmation. The evidence pane distinguishes intentionally blank requests,
actual written zeroes, covered and uncovered items, and retained documents.

These controls support assessed positive requests, not automated dispatch,
sender authentication, negative requests, sampling, client qualification or a
statutory audit opinion. UAE/India professional applicability still needs
qualified engagement review. Synthetic examples do not close those gates.


Verification on 26 October 2026: 1,941 backend unit tests passed (four skipped),
195 frontend tests passed, and 12 owned PostgreSQL/API tests passed, including
independent approval after partial-response disposition. TypeScript, production
frontend build, targeted ESLint, Ruff, mypy (68 source files) and UTF-8 checks
passed. One real-worker browser test exercised eight cases in UAE-then-India
order and verified downloaded document SHA-256 values. The eight new blank and
partial screenshots were visually inspected. The four saved example sets also
parse through the canonical source/calculation path under unit tests.
See [browser receipt](../phase-12/confirmation-extensions-browser-results.json).
The frozen authored synthetic catalogue remains 154; these checks do not
constitute 154 qualified client engagements or professional sign-off.


### Explicit expense cut-off allocations and posting schedules — UAE then India

The existing `expense-cutoff` workflow now supports `explicit-schedule`
documents, alongside its existing single-date path. This closes the supplied
schedule comparison gap for invoices spanning recognition periods, split
expense postings, signed reversals, credit notes and subsequent posting dates.
It does not calculate service-period proration or choose legal recognition.

Prepare three independently controlled and reviewed CSV sources:
`cutoff-documents`, `cutoff-recognition-lines` and `cutoff-posting-lines`.
The latter two use optional `recognitions` and `postings` roles; both are
required when assessing an explicit schedule. A genuinely nil posting
population needs an independently reviewed nil source, not an absent role.
The API rejects unreviewed inputs before comparison. Source revisions make
results stale through the existing retained-source dependency graph.

Each recognition row identifies its exact document, counterparty and currency,
with a signed amount, assessed recognition date, basis and source reference.
Allocations must equal each document amount exactly; monetary tolerance cannot
mask an incomplete or overallocated invoice. Invoice amounts are nonnegative,
credit-note amounts nonpositive. Explicit schedules cannot compete with
single-date recognition or posting fields on the scope document. Duplicate
supplied document identities are rejected. Unknown, wrong-party or wrong-
currency links fail rather than becoming guessed allocations.

Each posting identifies its allocation, document, counterparty, currency,
expense account, signed amount, actual posting date, journal reference and
evidence reference. Partial entries and reversals stay as separate original
links. Current, prior and subsequent posted amounts remain distinct; postings
after the review-through date fail. Assessed future recognition allocations
are labelled as schedules rather than evidence of future completed services.
Missing or wrong-period postings cannot become matches through a large money
tolerance. Document control failures block approval; other period/amount
exceptions need documented disposition and an independent authorized reviewer.

UAE and India share this arithmetic. The server enforces each engagement's
actual period start; it does not infer a universal country financial year,
VAT/GST treatment, deductibility, proration or FX conversion. Supplied expense
postings do not reconcile prepayment, payable, tax or cash control accounts.
Population completeness, source authenticity, sufficient audit evidence and
professional/legal recognition still require engagement-specific work.

New results retain `explicit-cutoff-schedules/1`. Document controls and original
posting links have separate API pagination (`cutoff_control_offset/limit` and
`cutoff_posting_offset/limit`), screen tables and complete XLSX sheets. The
compact comparison shows expected/current posted amounts by allocation;
source provenance, dates, prior/subsequent amounts and every original posting
ID remain available through the expanded result and export. The existing
single-date path remains readable and supports explicitly signed credit notes.
Historical source rows without the new mode/kind fields keep their original
single-date invoice meaning, including when nil optional schedules are supplied.

Verification on 26 October 2026: 1,971 backend unit tests passed (four skipped),
197 frontend tests passed and five owned PostgreSQL/API tests passed. The API
checks include refusal before source review, actual India/UAE engagement
periods, independent exception approval, source-change staleness and independent
pagination/export across 121 documents and 363 original postings. The maximum
5,000-allocation/5,000-posting unit case exports every row and link. Four saved
synthetic input sets also parse and reproduce their expected period amounts.
Production frontend build, TypeScript, scoped ESLint/Ruff, mypy across 69 source
files and UTF-8 checks passed. One real-worker browser test exercised both
split/reversal and late-credit cases in UAE-then-India order; all 12 screenshots
were visually inspected. See [browser receipt](../phase-12/cutoff-schedules-browser-results.json)
and [saved examples](sample-inputs/SYNTHETIC-cutoff-schedules/README.md).
A [verification summary](../phase-12/cutoff-schedules-verification.json) retains
counts, tested bounds and hashes of the owned local execution logs.
The frozen authored synthetic catalogue remains 154. This extension does not
close real-client, professional, native-provider or hosted-release gates.


### Retained exact economic ownership paths — UAE then India

`ownership-lookthrough` now retains every supplied natural-person path and its
original source-edge steps, not only final economic totals. The shared engine
uses exact rational arithmetic over canonical decimal shares. Deep-chain
products and threshold comparisons therefore avoid rounding a fraction just
below an illustrative threshold up to equality. Decimal exports retain every
digit. Path IDs connect the person totals to their detailed chains and original
references; result row IDs remain distinct when source identifiers contain
separators.

Both ownership and country/date policy sources must be independently reviewed
before comparison. The selected policy supplies its threshold and comparison
operator; no UAE or India legal default is manufactured. The UI displays the
country, as-of date, threshold, operator and retained policy reference. Voting
rights, control, nominees, trusts and legal UBO conclusions require separate
assessment. A reviewed uploaded policy does not authenticate a publisher or
qualify current local law.

Cycles, missing corporate-owner evidence, incomplete ownership sums and duplicate
current owner edges retain explicit graph-gap paths with source references.
Observed successful paths are also retained, but incomplete roots have an
unknown full threshold decision and visibly partial fractions. Graph-gap
person identities and economic fractions remain absent, not zero. Documenting
an exception cannot override an incomplete graph's approval block. Sources
must be corrected, independently reviewed and recomputed. Historical results
without `economic-ownership-paths/1` require regeneration before approval.

The graph remains bounded: 5,000 rows per canonical source, 100 distinct exact
company subjects, at most 20 edges per retained path, 10,000 explored transitions
across the selected subject scope, and 50,000 retained source steps. A bound
failure stops calculation rather than truncating evidence. Economic agreement
describes the supplied graph; it does not prove complete ownership disclosure,
registry verification, legal status, onboarding approval or an audit opinion.

Paths and steps have independent API pagination (`ownership_path_offset/limit`
and `ownership_step_offset/limit`), screen views and full XLSX sheets. Canonical
sources retain their original hashes and dependency history; a revised source
or policy makes the calculated result stale. See [saved synthetic UAE/India examples](sample-inputs/SYNTHETIC-ownership-paths/README.md).


Verification completed 27 October 2026: 1,989 backend unit tests passed (four
skipped), 199 frontend tests passed and five owned PostgreSQL/API tests passed.
The API flows test refusal before independent source review, candidate review,
incomplete-graph approval refusal despite documented dispositions, policy
revision staleness, complete exports and separate pagination over 128 paths and
256 steps. The maximum 5,000-edge source case retains all 9,996 derived paths
and 19,992 source steps; exceeding a configured traversal/retention bound fails.
A 20-edge precision case stays below its policy threshold without Decimal
round-up, and preserves the exact fraction in XLSX. Four saved UAE/India sets
reproduce their expected complete/partial states and counts. Historical approval
and source-identifier delimiter collision regressions also pass.

One browser test ran complete and incomplete cases in UAE-then-India order
against the production frontend build and real local worker. All 12 screenshots
were visually inspected. Production build, TypeScript, targeted ESLint/Ruff,
mypy across 70 source files and UTF-8 checks passed. See the
[browser receipt](../phase-12/ownership-paths-browser-results.json) and
[verification summary](../phase-12/ownership-paths-verification.json).
The frozen authored synthetic catalogue remains 154. Real-client, legal-policy,
registry/provider, professional and hosted-release qualification remain open.


### Offsite inventory custody quantities and condition — UAE then India

`inventory-custody-confirmations` compares independently reviewed offsite book
positions with retained quantity/condition correspondence. This is a shared
custody-evidence procedure, separate from customer/vendor financial balance
letters, physical count attendance, title authentication and cost/NRV testing.
Custody is not ownership: an entity-owned item may be held externally, while
third-party-owned goods are not silently included in entity inventory.

Prepare canonical `inventory-custody-positions` and
`inventory-custody-confirmations` sources. Both require independent quantity
controls for every exact position ID, custodian, site, SKU, lot and unit. On a
response source, control quantity means the stated request quantity;
response_quantity means the actual written reply, or null for an unanswered
request. Money totals are empty. Controls are verified at preparation and
calculation. Duplicate physical position/response scopes, missing controls and
incorrect quantities fail. No cross-unit netting or automatic conversion occurs.

Each response retains request, response and follow-up versions, SHA-256 values,
references, assessed dates, contact/direct-receipt declarations and scope
assessment. Shared actual retained files can bind a batch; mixed documents need
per-row bindings. The correspondence and control infrastructure reuses the
existing verified-source, retained-file and independent-review paths. Bound
correspondence-file integrity is checked again before calculation. A document change makes
its source and dependent comparison stale. Source CSVs cannot masquerade as
their own retained correspondence. Hashes establish identity, not sender or
content authenticity; dates and source-to-document interpretations remain
independently assessed declarations.

A received full-position reply needs quantity, condition and held-for-entity
scope. Book/request/date/unit/custodian differences, unknown positions,
unassessed direct receipt and ownership/held-for-entity gaps block approval.
Monetary tolerance cannot hide a quantity difference. Quantity/condition
exceptions require retained investigation before documented exception and
independent final review. Pending, undeliverable and unreliable replies require
retained alternative procedures and remain visibly unconfirmed. Those
procedures do not turn an absent or unreliable reply into a matched quantity.

An affirmative zero is distinct from missing data. `none-held` custody and
`not-applicable` condition are allowed only with an explicit written zero.
A zero reply against positive books retains the entire quantity difference.
An empty schedule does not qualify entity-wide nil offsite inventory; named
zero-position responses do not establish that no other inventory exists.
Requests may be issued before the reporting date, but a written response cannot
purport to confirm future reporting-date holdings. A different-date physical
observation needs a separately assessed bridge, not an inferred quantity.

The screen retains separate book/reply quantities, condition and raw scope,
plus downloadable correspondence. Independently paged quantity controls use
`custody_control_offset/limit`. Full XLSX retains every position, quantity
control and request/response/follow-up link. New results retain
`offsite-inventory-confirmations/1`.

As a design reference for India reviewers, [ICAI SA 501 paragraph 8](https://kb.icai.org/pdfs/PDFFile5b3b56931ba5b3.25548018.pdf)
addresses quantity/condition evidence for inventory held by third parties and
other appropriate procedures. This reference does not automatically apply an
Indian standard to UAE engagements or qualify either country's methodology.
Actual framework adoption, procedure sufficiency, title, liens, consignment,
completeness, physical attendance, valuation and professional conclusions
remain separate engagement assessments. Canonical CSV and synthetic examples
do not qualify native custodian-file extraction, live confirmation dispatch,
sender authentication or real-client coverage. See [saved UAE/India examples](sample-inputs/SYNTHETIC-inventory-custody/README.md).


Verification completed 27 October 2026: 2,032 backend unit tests passed (four
skipped), 202 frontend tests passed and 19 owned PostgreSQL/API tests passed
(seven custody flows plus 12 party-confirmation regressions for the shared
correspondence path). Tests cover independent source review, exact units and
quantities, explicit zero versus absent replies, zero against positive books,
condition and ownership gaps, preissued requests, reporting/review windows,
retained follow-up, independent final approval, source/document staleness,
original download bytes and complete exports. The 5,000-position maximum case
retains all 10,000 controls and 10,000 correspondence links. Separate API
pagination/export preserves 121 positions and all 242 controls/document links.
Six saved UAE/India input sets parse and match their expected outcomes and
published document checksums.

One browser test exercised received, pending and explicit-zero cases in
UAE-then-India order against the production frontend and real local worker,
including exact downloaded-document SHA-256 checks. All 18 screenshots were
visually inspected. Production build, TypeScript, scoped ESLint/Ruff, mypy
across 71 source files and UTF-8 checks passed. The first build attempt hit a
Windows lock held by the owned preview server; after stopping it, the build
completed successfully. See the [browser receipt](../phase-12/inventory-custody-browser-results.json)
and [verification summary](../phase-12/inventory-custody-verification.json).
The frozen authored synthetic catalogue remains 154. These checks do not
establish 154 qualified client engagements. Real-client, native-provider,
professional/legal and hosted-release gates remain open.


## Permission conflicts during an audit period

The shared GRC SoD workflow now supports an optional inclusive analysis period,
in addition to its existing assessment-date view. A permission revoked before
year-end can therefore remain a conflict candidate for its actual overlap
interval. Regrants preserve every original one-based assignment index and
assignment-pair link; overlapping/adjacent days are merged only for interval
presentation. Distinct scope pairs remain separate findings. These are
permission combinations, not evidence of transactions or fraud.

The default compares exact opaque scope identifiers. An independently approved,
effective-dated policy can explicitly declare direct scope relationships and
retain their rationale and supporting policy reference. There is no automatic
wildcard, global scope, role expansion, identity equivalence, cross-system
comparison or transitive hierarchy. A policy must cover the complete requested
window; policy changes need explicitly partitioned workpapers. Dates are ISO
calendar dates, inclusive, without inferred timestamps or ERP timezone semantics.

Historical analysis requires a retained hashed CSV, explicit history coverage,
a source-scope assessment, independent assignment/principal counts and a separate
approved control record/reference. Reviewed cross-scope analysis also requires
the hashed CSV and separate counts controls. Calculations re-read clean approved
source files, check actual file hashes and compare every ordered assignment
against the CSV before returning a cached result. Definition and control records
remain independently approved, current dependencies. Legacy exact point-in-time
approved references remain readable as explicitly unverified CSV bindings;
they do not silently acquire history completeness.

New immutable runs retain `permission-overlap-intervals/1`, implementation hash,
source receipts, coverage declarations, all conflict intervals and all original
assignment-pair links. Existing GRC review, import, calculation and monitoring
paths are reused; monitoring keeps source dependencies and returns candidates
for review. A changed source blocks recalculation; an implementation change
creates a new snapshot. The import form exposes history and population controls;
the generic policy editor exposes effective dates and direct scope mappings.
The professional SoD read model now provides independently paged row collections,
a saved-snapshot selector and a complete workbook. Compact calculation/history
requests omit the large assignment/result collections while the frozen snapshot
retains them. See the reporting contract below.

Bounds are 10,000 input assignments, 100 incompatible permission pairs, 1,000
direct scope relationships, 1,000,000 interval comparisons and 10,000 retained
assignment-pair links. An exceeded bound rejects analysis with a partitioning
requirement; it never silently truncates. The 10,000-assignment test retains
all 5,000 logical conflicts and original assignment-pair links.

[Saved UAE/India synthetic source sets](sample-inputs/SYNTHETIC-sod-history/README.md)
include actual CSV/policy/count-memo bytes, checksums and expected point/period
outcomes. They do not establish client source completeness, ERP-native adapter
qualification, country framework adoption, verified compensating controls,
SOX/IFC conclusions or a real-client pilot. The original authored catalogue
remains 154 synthetic scenarios. Real pilot folders and manifest templates are
saved under `pilot-data/UAE` and `pilot-data/India`; supplied private inputs,
independent expected results and review records are excluded from Git.

Verification completed 27 October 2026: 2,068 backend unit tests and 11 existing
GRC calculation tests passed (four skipped); 204 frontend tests passed. Three
owned PostgreSQL/API tests passed: UAE and India source/review/history/cache/
monitoring flows, plus the existing GRC approval/owner-isolation regression.
API tests reject changed source bytes and edited assignment bodies despite an
unchanged declared hash, check source reopening, and verify that an
implementation change produces a new immutable calculation. A production-browser
test exercised both import-form modes with empty coverage defaults and required
independent controls; it does not submit a browser CSV. All four screenshots
were visually inspected. Production build, TypeScript, scoped ESLint/Ruff, mypy
across 16 GRC modules and UTF-8 checks passed. See the
[verification receipt](../phase-12/sod-history-verification.json) and
[browser receipt](../phase-12/sod-history-browser-results.json).


## Professional SoD reporting

The same reviewed SoD calculations now have a compact summary and eight separately
paged collections: conflicts, conflict intervals, original assignment-pair links,
original input assignments, direct scope mappings, permission pairs, source
receipts and record dependencies. API pages default to 100 rows with a maximum
of 500; the screen requests 50 at a time and preserves independent page positions.
The imported workpaper population is also rendered 50 rows at a time, including
before approval. Its original one-based indices match the frozen assignment
links. The screen presents evidence at full workspace width with bounded,
keyboard-focusable table scrolling instead of rendering the entire population
inside the narrow generic workpaper panel.

Saved calculations are selectable separately from freezing a new calculation.
A historical snapshot remains readable after a source is reopened. Current
record-version status and calculation-implementation status are separate labels.
The read model does not re-read original file bytes or represent source receipts
as current verification; file checks were recorded at freeze. A source change
still blocks a fresh calculation pending reassessment. Permission-pair definitions
are retained for newly frozen runs. An older interval snapshot without the full
pair definition is explicitly labelled rather than filled from today's policy.

The complete XLSX includes Scope, Conflicts, Conflict intervals, Assignment links,
Assignments, Scope mappings, Permission pairs, Source receipts and Dependencies.
Every retained row is exported independently of the displayed page. Conflicts
retain counts and links rather than large nested arrays in individual cells.
Scope metadata recursively retains optional nested workpaper source references.
Formula-prefixed identifiers remain literal text. Absent values stay blank,
explicit false remains false, and generated nonnegative indices/counts are
numeric. The existing exact-text writer retains oversized or newline-heavy text
in ordered Long values parts with hashes. XML-incompatible characters use a
separate Encoded values sheet with exact UTF-8 base64, hash and source coordinate.
The shared continuation bound is 64 MiB; an exceeded representation bound
rejects export with an explicit partitioning requirement, never truncation.

Read and export authorize the exact tenant, engagement and SoD run. Owner-scoped
and board roles cannot use the professional read model, and unassigned audit
roles do not gain engagement access. Export records an audit-log receipt. The
legacy full calculation/history response remains available; new SoD screens
request compact responses and fetch retained collections separately.


Verification completed 27 October 2026: 2,074 backend unit tests and 11 existing
GRC calculation tests passed (four skipped); 210 frontend tests passed. Five
owned PostgreSQL/API tests passed: two reporting flows, the two existing
history/source/monitoring flows, and the existing GRC approval/owner-isolation
regression. The maximum-input workbook test retains all 10,000 assignments,
5,000 conflicts and 5,000 original assignment-pair links. Tests preserve literal
formula-prefixed identifiers, false versus absent values, newline-heavy text,
XML control characters and nested workpaper source references. Authorization
tests reject owner/board roles, unassigned auditors and a different tenant.
Historical exports preserve snapshot data/hash after a source is reopened.

One production-browser test exercised UAE then India using 242 assignments and
121 conflicts per country. It verified independent conflict/link/assignment
paging, the final assignment index, and all rows in four complete workbook
downloads before and after independent source reopening. Hyphenated collection
paths pass through the application gateway. All six screenshots were visually
inspected. Production build, TypeScript, scoped ESLint/Ruff, mypy across 18 source
files and UTF-8 checks passed. The first broad backend run had a Windows OCR
child queue handle failure; both an isolated retry and the full repeated suite
passed. No OCR implementation change or extraction qualification is claimed.
See the [reporting verification receipt](../phase-12/sod-reporting-verification.json)
and [browser receipt](../phase-12/sod-reporting-browser-results.json).

These are controlled synthetic tests. They do not supply real client inputs,
independently checked client expectations, native ERP qualification, country
framework adoption or hosted release validation. The authored catalogue remains
154 scenarios, with real pilot evidence still pending in `pilot-data/`.

## Restricted grant expenditure and utilisation

The shared `grant-utilisation` workflow adds mandate-based book expenditure
allocation, exercised for UAE first and India second. Four independently reviewed
canonical schedules supply budgets, expenses, allocations and utilisation controls.
Budgets retain donor/project/country/currency, category and whole-fund ceilings,
validity dates and original mandate file-version/hash bindings. Negative allocations
also retain recovery document bindings. Original documents must be current, clean,
distinct from the schedules and byte/hash verified before calculation; existing
limits of 50 documents and 100 MiB apply.

An explicit review window must fall inside the engagement. Every fund/category
requires declared opening utilisation dated the preceding day; absent openings
remain missing. Expense-period controls independently compare account/currency
row counts and positive, negative and net amounts exactly. Allocations must reconcile
each expense, including shared expenses across funds, without exceeding declared
capacity. Currency, project, source references and credit signs must agree.
Category and whole-fund limits are tested separately against opening plus signed
period expenditure. Credits always need documented recovery review. Expired
mandates, budget excesses and credit observations require individual dispositions
and independent approval; unresolved population or allocation controls block it.

Budget import totals sum category ceilings, not available cash. Mixed control-row
file totals establish import integrity only. These schedules do not establish cash
availability, donor authentication, prior-charge validity, legal eligibility or a
utilisation certificate. UAE charity/licensing and India CSR/FCRA assessments
remain separate country procedures. No country fiscal period is inferred.
Allocation capacity applies within the declared population, not an entity-wide
posting ledger. Keep complete fund/currency populations together; controlled
adjacent periods need independently supported openings. Overlapping partial
reports cannot establish complete fund capacity.

Each source supports 5,000 rows. The maximum-size test preserves all 10,003 result
rows in XLSX (10,004 with header). Results retain original document receipts,
scope and review limitations; the UI provides authenticated original downloads.
[Eight synthetic UAE/India examples](sample-inputs/SYNTHETIC-grant-utilisation/README.md)
cover matched expenditure, credit recovery, nil activity and budget excess.
Their published hashes and expected outcomes are checked by tests. They are
examples, not client qualification evidence.

Verification on 27 October 2026: 2,132 backend tests passed (2,121 unit plus 11
existing calculation regressions; four skipped), 213 frontend tests and 11 grant
API tests passed. A production-browser test ran ten real-worker UAE/India cases,
including unallocated expenditure, and verified 12 original-document downloads.
Twenty screenshots were saved and reviewed as a contact sheet, with representative
scope, blocked approval and document captures inspected at full size. Production
build, TypeScript, scoped ESLint/Ruff, mypy across 72 source files and UTF-8 checks
passed. See the [verification receipt](../phase-12/grant-utilisation-verification.json)
and [browser receipt](../phase-12/grant-utilisation-browser-results.json).
The authored catalogue remains 154; real pilots, native provider qualification,
professional country review and hosted release validation remain open.

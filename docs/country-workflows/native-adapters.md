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

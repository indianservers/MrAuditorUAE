# Dated gratuity service-day checks

The UAE `uae-benefit-review` workflow can now select an optional independently
reviewed `service_calendar` source. It compares dated, source-assessed exclusions
with the employee's declared excluded-service-day total. Existing inputs without
this source keep their calculation and are explicitly labelled
`EMPLOYEE_DECLARATION_ONLY`. Selecting the calendar does not classify leave or
determine legal eligibility.

## Evidence contract

Upload canonical `benefit-service-exclusions` CSV with separate rows for each
original assessed exclusion. Every row retains its source ID, exact employee ID,
service start/end, regime, cohort, work model and gratuity scheme, evidence
reference and meaningful assessment.

- `EXCLUDED_CALENDAR_DAYS` requires start/end dates within that service spell and
  an explicit day count equal to the inclusive interval. Adjacent intervals are
  accepted. Overlap, including a shared endpoint or duplicate period, is rejected.
- `NO_EXCLUDED_DAYS_ASSESSED` has no exclusion dates and exactly zero days. It must
  be the employee's only calendar record. An empty file or missing employee is
  never interpreted as a zero exclusion.

Supply independent `benefit_service_controls` with integer `employee_count` and
`excluded_days`, plus the existing independent source row count. The UI starts
these controls blank and preserves an explicitly assessed zero. This is a day
and population control, not a monetary total; `control_totals` must be empty.
Files remain bounded to the existing canonical 5,000-row and cell-size limits.
An interval is bounded to 36,500 days. No partial-day or working-day conversion is
inferred. Where only selected calendar days qualify, retain those assessed
intervals rather than assuming all dates in a leave request are excluded.

When a calendar is selected, employees, rules and calendar sources must all be
current and independently reviewed before calculation. The source is restricted
to the `service_calendar` role of UAE benefit review. Each retained employee must
match the exact service identity; extra employees and conflicting scopes are
rejected. Missing employees and a difference between dated and declared days
block the result, with no calculated benefit for those rows. They cannot support
the expected-gratuity settlement bridge until resolved.

For matching rows, the existing supplied-rule benefit calculation is unchanged.
The result retains declared and dated days, all original exclusion records,
control totals and its `benefit-service-calendar/1` contract. The review screen
distinguishes zero from unknown and displays individual dates/evidence references.
It shows at most 20 detail records per employee with an explicit count; the
original result and XLSX **Benefit service exclusions** sheet retain every record.
XLSX writes individual rows rather than silently truncating a large nested cell.

Withdrawing the calendar review or replacing its original file makes dependent
benefit results stale. Existing dependency tracking also makes derived expected
settlements and bank comparisons stale without rewriting saved
financial rows. Independently resolve and recalculate before approval.

## Country and professional scope

The date/count foundation is reusable, but this consumer is UAE gratuity only.
It does not activate an India benefit calculation or apply gratuity exclusions to
UAE pension periods. The UAE government's [private-sector benefit guidance](https://u.ae/en/information-and-services/jobs/employment-in-the-private-sector/end-of-service-benefits-for-employees-in-the-private-sector)
identifies unpaid absence as a service-calculation consideration. Separately,
[GPSSA's article published 19 May 2022](https://www.gpssa.gov.ae/pages/en/media-center/news/gpssa-leaves-included-contribution-scheme)
describes pension contribution treatment for different leave circumstances. That
historical article illustrates why the two procedures cannot share an automatic
exclusion rule; it is not a complete current pension-cohort pack.

Both sources were checked on 29 October 2026. No leave classifications, eligibility
rules, gratuity rates, year bases, salary definitions or thresholds are supplied
by this calendar feature. The original HR records, legal treatment, employee
scope and source completeness still require independent assessment. Paid leave,
part-time hours, government service, alternative schemes, changing work models
and India entitlements must not be inferred from this comparison.

## Synthetic example

`sample-inputs/SYNTHETIC-benefit-service-calendar/` retains two original CSVs,
their byte hashes, declared controls and authored expectations. Reuse the existing
synthetic full-time/part-time benefit parameter file and retain its supporting
document separately. Under those supplied fixture parameters, E1 has 730 inclusive
days less five assessed exclusions, giving 725 eligible days and AED 4,171.23;
E2 has an explicit zero exclusion and AED 1,050.00. These values are authored
mechanical examples, not independently approved client or legal results.

## Retained verification

Application source `2d108f6` passed 3,232 local backend unit tests (five skipped),
four focused database/API workflows and 315 frontend tests. The API receipt covers
the new zero/nonzero calendar cases and two prior gratuity bridge regressions,
using real HTTP, storage, database and job processing with explicit scanner and
dispatch doubles. It verifies that calendar review withdrawal makes a current
benefit, derived expectation and bank comparison stale without changing financial
bodies. Replacing original calendar evidence is also covered.

The presentation follow-up `2cbb680` changes three frontend files; backend code is
identical to `2d108f6`. All 316 frontend tests, TypeScript, lint and production build
passed. Compact results now show exact eligible days. Full service-year precision
remains in source provenance and XLSX, verified by a frontend test.

All three hosted browser cases passed on `2cbb680` in 1.8 minutes, including the
new UAE calculation, independent final approval, exact XLSX and calendar-source
withdrawal. Source setup/reviews use APIs with the real scanner, broker and worker.
The original artifact digest was verified and both exact images inspected:

- [Reviewed dated calendar and benefit](screenshots/browser-workflows/AE-benefit-service-calendar-reviewed-2cbb680.png)
- [Withdrawn calendar source and stale approval](screenshots/browser-workflows/AE-benefit-service-calendar-withdrawn-stale-2cbb680.png)

Both titles are unobstructed. The images show June 1–5 evidence, an explicit zero
summary, controls for two employees/five days, eligible-day counts of 725/365 and
benefits of 4,171.23/1,050.00. The visible preparation form in the reviewed image is
unfilled and is not evidence of a new expected settlement for these employees.
The earlier passing `2d108f6` receipt retains its obscured heading and long-decimal
display as explicit visual shortcomings. All six hosted jobs passed on `2cbb680`.
Its full backend suite passed 4,135 tests with nine skips in 2,775.88 seconds;
overall coverage is 86.30% and the existing calculation/validation core is 89.35%.
[The full backend receipt](../phase-12/2cbb680-hosted-verification.json) binds the
source, successful jobs and exact original JUnit/coverage files to the verified
artifact digest. The nine hosted skips comprise four authorized live-provider
checks, four opt-in isolated connector cases and one Windows-only runtime case.
Synthetic operational records performed no external requests or filing
submissions. These results establish application regression coverage, not
independent clients, qualified legal cohorts or production deployment.

The five cases skipped by the original local full-unit run also passed in
separate opt-in executions: four connector PostgreSQL/Redis checks in a fresh
UUID database/role with owned quota keys, and one real built TensorFlow CPU-worker
test. [The supplemental receipt](../phase-12/calendar-supplemental-infrastructure.json)
retains their exact JUnit files. The original full-unit skip count is preserved;
these runs do not establish live vendor authentication or client control totals.

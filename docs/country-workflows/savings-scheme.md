# UAE savings basic contributions and fund observations

`uae-savings-review` handles assessed MOHRE alternative-scheme employer basic
contributions. It is available for UAE engagements and remains separate from
gratuity, pension, employee voluntary savings, investment returns and benefit
redemptions. It installs no statutory rate or automatic membership classification.

## Review inputs

Three independently reviewed canonical sources are required:

- `savings-bases`: employer, employee, fund, membership reference, enrolment date,
  covered wage dates, regime, cohort, work model, assessed service-rate band and
  contributory basic wage. A separately retained enrolment document UUID/hash is
  required. The source form can bind one shared supporting document to blank
  references; conflicting references fail.
- `savings-rules`: exact fund, regime, cohort, work model and assessed rate band,
  effective dates, supplied rate/rounding, version and retained source-document
  UUID/hash. A single policy must cover each full covered interval. Missing,
  split or competing policies leave the expected amount unknown and block review.
- `savings-reported`: original fund-observed basic contributions using the same
  participant, fund, membership and coverage identity. Missing observations are
  distinct from explicit zero observations. Amount equality cannot clear a
  different fund or membership.

Source preparation and calculation verify the actual retained enrolment and
policy bytes, current evidence versions and contributor identity. Reviewers must
assess document meaning, fund approval, eligibility and applicable law separately.
The `RETAINED_DOCUMENT_BYTES_VERIFIED` marker does not establish those conclusions.

Full-time bases use assessed contract basic wages without an hours factor.
Supported part-time/job-share bases require an explicitly assessed full-time
salary comparator and positive comparable annual contract/full-time hours. Apply
the hours ratio once, then round once per covered contribution record using the
reviewed rounding method. Actual part-time salary cannot masquerade as that
comparator. The source control sums supplied contract/comparator bases before
rates and ratios; it is not gross payroll or a fund-contribution total.

`FULL_MONTH_BASIC` requires an entire calendar month. A partial covered period
requires `ASSESSED_COVERED_PERIOD_BASIC` and a documented supplied wage assessment;
no day-proration rule is inferred. Enrolment cannot precede assessed employment,
coverage cannot precede enrolment or exceed an assessed employment end, and wage
months must be closed. Overlapping basic-coverage records for the same employee
cannot double count wages across funds or work models.

## Reuse in settlement

After independent final approval, the result form accepts separate fund-specific
row counts, expected amounts and supported due dates. Controls remain blank until
entered, cover complete selected employer/month/fund groups and persist across
result pages. `contribution-obligation-source` reuses the existing remittance
bridge and creates an unverified **expected** obligation source. Different funds
cannot share a pooled amount control.

A current reviewed `savings-reported` source has a separate form for independently
entered full-population count and AED amount. The endpoint
`savings-reported-obligation-source` creates an unverified **reported** obligation
source, retaining the original fund-source dependency, row references and typed
fund/enrolment/coverage scopes. An empty source requires its original reviewed nil
declaration. This representation never establishes expected liability or bank
payment.

Both sources require independent review before the existing
`obligation-bank-allocations` workflow can link them to separate bank evidence.
Typed savings scopes cannot be substituted for pension, gratuity, another month,
another currency or another fund. Fund and membership remain visible in compact
bank results; XLSX retains full scope and provenance. No payment is executed.

Replacing enrolment or policy evidence stales the contribution result, its
expectations and dependent bank comparison while preserving saved bodies. The
independent fund-observation derivative stays current when its own original
evidence is unchanged. Withdrawing/replacing the original fund population also
stales that derivative and its dependent comparisons.

## Sources and qualification

Policy background is published in [Cabinet Resolution 96/2023](https://www.mohre.gov.ae/assets/download/c7ea6970/cabinet-resolution-no-96-of-2023-regarding-an-alternative-end-of-service-benefits-system-en.aspx)
and [Ministerial Resolution 668/2023](https://www.mohre.gov.ae/assets/download/f8a59b10/ministerial-resolution-no-668-of-2023-regarding-subscription-under-the-alternarive.aspx).
Indexed official text was available during research, but direct complete-document
retrieval timed out or was forbidden. The indexed English worked hours example
contains an arithmetic inconsistency; neither that illustration nor ambiguous
service-boundary wording is promoted to an approved rule. Operative original
language, version, salary comparator, service bands, rounding and cohorts require
professional qualification against retained authoritative documents.

[Saved examples](sample-inputs/SYNTHETIC-savings-scheme/README.md) are authored
synthetic mechanics covering two funds, full-time and part-time comparators,
explicit covered-period bases and exact contribution controls. They are not
independent client expectations. Fund-provider layouts, live approval/registry
verification, pre-enrolment gratuity preservation, voluntary contributions,
investment/NAV, withdrawal entitlements and actual remittance execution remain
separate work. DIFC/other schemes are not silently treated as MOHRE savings.

## Retained application verification

The [local receipt](../phase-12/savings-validation.json) retains the original
3,306-pass/four-skip backend unit run, including 39 savings cases, nine API
workflows and 338 frontend tests across 68 files. TypeScript, lint, production
build and current API contracts passed. Four API cases verify scoped dependency
staleness; five prior payroll/contribution flows remain passing. Scanner and
dispatch are explicit doubles in those API tests.

The first hosted savings attempt passed calculation, independent approval and
XLSX but failed locating a document select. The
[correction receipt](../phase-12/savings-document-label-correction.json) retains
the original failure image and an offline browser reproduction: adding explicit
accessible selector names changed an exact label match from zero to one. The
follow-up passed all 338 frontend tests, types, lint and production build.

All three hosted browser cases then passed on `f172168` in 2.2 minutes, using
the real scanner, broker and worker. The original artifact digest and both
captures were verified and visually inspected:

- [Reviewed contributions with filled separate fund controls](screenshots/browser-workflows/AE-savings-contributions-reviewed-f172168.png)
- [Withdrawn source and stale approval](screenshots/browser-workflows/AE-savings-contributions-withdrawn-stale-f172168.png)

The [browser receipt](../phase-12/savings-browser-f172168.json) distinguishes the
filled-form image from later executed source preparation, API source setup from
UI actions, and API bank-allocation proof from browser scope. Full current hosted
backend verification remains running. None of these receipts establish actual
client data, live fund verification or professional legal qualification.

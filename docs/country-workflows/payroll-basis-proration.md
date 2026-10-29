# India dated PF wage bases

`india-payroll-basis-proration` compares dated assessed PF wage segments with
independent monthly component-basis controls. It is available only for India;
UAE pension and gratuity use their separate workflows. This fills the wage-basis
part of mid-month membership or ceiling changes while reusing existing India
contribution review, remittance expectations and bank allocations.

## Sources and review

Three independently reviewed canonical sources are required:

- `segments`: `payroll-basis-segments`, with employee, establishment, wage month,
  component, inclusive dates, monthly reference basis, allocated uncapped amount,
  explicitly assessed eligibility and evidence reference.
- `rules`: `payroll-cap-rules`, with component, rule group, jurisdiction, effective
  dates, explicitly capped or assessed-actual-basis mode, version and original
  retained policy document UUID/hash. Selected document bytes are verified during
  source preparation and calculation through the existing rule-document checks.
- `controls`: `payroll-bases`, containing independently checked post-ceiling
  monthly component bases and aggregate assessed eligibility.

Only PF employee, EPS and employer bases are supported. All three must be explicit
for every employee/month, including assessed excluded zeros. Segments must cover
the entire calendar month without gaps or overlap. The month must lie fully in the
engagement period and close by the calculation date. Missing controls or policy
coverage block the result and leave the computed monthly basis unknown.

The named method is `ACTUAL_CALENDAR_MONTH_PAISE`: allocated uncapped wages equal
monthly reference basis × inclusive segment days ÷ actual month days, rounded
half-up to paise. A capped segment uses the lower of its monthly reference basis
and assessed monthly ceiling before the same proration. An explicitly excluded
segment contributes zero. A blank ceiling is permitted only with explicit
`ASSESSED_ACTUAL_BASIS`; no absence of policy is interpreted as unlimited wages.
One policy must cover each entire segment, with no competing intersecting policy.

Dates, ceilings, membership, higher-wage choices and rounding applicability remain
assessed inputs supported by retained documents. No statutory rate, ceiling,
membership classification or due date is automatically supplied by this feature.

## Contribution and payment bridge

After independent final approval, the monthly-source form requires a separately
entered row count and INR total for the full result. This counts component bases
separately; it is not gross payroll or a contribution total. The endpoint is
`POST /api/v1/intelligence/engagements/{eid}/prorated-payroll-basis-source`.
It creates an unverified `payroll-bases` source with retained segment/policy links,
protected `prorated-payroll-bases/1` provenance and a dependency on the reviewed
calculation. A source review is still required.

The source can feed only the `bases` role of `india-payroll-rules`. Contribution
rules must cover the whole wage month and use an uncapped rate or employer-minus-
EPS formula without wage slabs. Reapplying a salary ceiling, selecting a slab on
the prorated amount or using a fixed slab is blocked. This guard also applies
when preparing rules from the existing published payroll-profile library.

Existing contribution expectations preserve the wage month and require separately
assessed due dates, independent contribution totals and retained supporting
evidence. Authority-reported amounts, payment statements and bank allocations
remain separate sources. Salary recovery in a later month does not automatically
move the assessed wage-month liability.

Withdrawing a reviewed segment source or replacing its original file makes the
dated result, monthly basis source, contribution result, remittance expectation
and bank comparison stale. Their saved financial bodies remain unchanged.

## Evidence and limits

The UI shows a compact monthly comparison and an explicitly bounded segment
preview. XLSX has a separate `Payroll basis segments` sheet with every segment
and selected policy, avoiding nested-array cell truncation. The exporter does
not modify saved result bodies.

[Synthetic files](sample-inputs/SYNTHETIC-payroll-proration/README.md) cover three
distinct assessed membership/ceiling options. They are authored mechanical
examples, not independent client expectations or published legal packs. Tests
cover calendar coverage, exact controls, eligibility, competing policies, double
ceilings, legacy contribution reuse, full XLSX, review independence and recursive
staleness. Hosted browser execution and its screenshots require source-specific
observed results; adding the test alone does not prove that execution.

ESI/PT, EDLI and establishment-level administration minima, contribution rates
changing within a month, interest, damages, native ECR schema qualification and
actual portal submission remain separate work. Real client pilots and
professional country/cohort qualification remain open.

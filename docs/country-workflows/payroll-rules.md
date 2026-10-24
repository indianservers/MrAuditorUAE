# India payroll contribution rules review

Implemented 25 October 2026. This workflow calculates an expectation from assessed component bases and independently reviewed rules, then compares it with ECR or other reported obligations. It uses the existing evidence store, country binding, immutable sources, worker queue, review, export and staleness controls. No database migration is required.

## Workflow

1. Retain the source documents supporting the rule, cohort, wage base and exemption assessments. Files must be clean and current.
2. Prepare `payroll-bases` CSV: one employee/establishment/month/component per row, with its assessed base, rule group, jurisdiction, explicit eligibility decision, evidence reference and assessment. Base controls sum component bases; they are not gross payroll totals.
3. Prepare `payroll-rules` CSV. Each rule contains effective dates, a half-open base band, formula, cap where applicable, rounding, source URL/version, retained source-document version/hash and applicability review. The source-document selector can fill blank document references and hashes from a retained file; conflicting CSV references are rejected. Multiple documents may be referenced explicitly in the CSV.
4. Independently review the prepared rule source. Its preparer cannot self-approve it. The contribution workflow rejects an unreviewed rule source.
5. Prepare `obligations` for the reported amounts, or use the native monthly ECR reader. Select **India payroll contribution rules review**, the three sources and the reconciliation date. The workflow requires INR and a closed wage month.
6. Review differences and unresolved rules. All source populations require independent review before final result approval; source review changes require regeneration. Export retains per-row formulas, rounding, source references, assessed/expected/reported values and totals. Payment evidence remains a separate statutory-dues workflow.

The UI defaults to the contribution comparison and totals. **Show rule provenance and source references** reveals the supporting formula and receipt fields. Incomplete rule resolution marks the expected total as partial and blocks approval.

## Calculation scope

- PF: employee and EPS amounts use their independently specified rates, bases, caps and rounding. Employer PF can use rounded total employer contribution less the separately resolved EPS amount for the same establishment, employee, month and jurisdiction. Missing or ambiguous EPS is not silently replaced by zero; a negative residual blocks calculation.
- ESI: employee and employer rates and rounding are independent. Eligibility is explicit for each component, so an employee exemption does not automatically exempt the employer. Contribution-period continuity must be assessed in the inputs; the engine does not terminate coverage merely because wages increase.
- PT: state/cohort-specific source-defined fixed or rate bands use inclusive lower and exclusive upper boundaries. Missing or overlapping bands block approval. Special months and exemptions require their own dated rules and explicit assessments.
- Advance refunds can be assessed separately as a component. EDLI and administration charges, interest, damages, filing and payment execution are outside this contribution-review workflow.

Rules must cover the whole selected wage month. Mid-month changes require a separate supported assessment rather than an automatic prorating assumption. Source-based rounding options are nearest whole rupee, ceiling, floor or paise. These are calculation options; no option is automatically selected as legally applicable.

## Source controls

Preparing a rule source verifies every cited retained-document hash and links its evidence receipt to that source. Calculation rechecks original-file integrity. Superseded or quarantined documents make rule sources and dependent results stale. At most fifty distinct cited documents and 100 MiB of cited content are verified per preparation/calculation. Ordinary source CSV bounds still apply.

Professional approval determines whether a cited document and its interpretation apply. The engine does not authenticate a publisher, resolve membership law or grant a statutory-compliance conclusion. Results remain `UNVERIFIED` until the existing independent workflow review; `statutory_calculation_qualified` remains false.

## Evidence

- `tests/unit/test_payroll_rule_workflow.py`: PF/EPS split, voluntary employee rates, ESI rounding/continuity and employee-only exemption, PT band/state boundaries, missing/overlapping/partial-month rules, pension mismatch, country/cutoff boundaries and reported differences.
- `payroll-rule-integration-results.xml`: independent rule review, native ECR comparison, original rule-document linkage, export, document-supersession staleness, invalid hash rejection and source-document selector binding.
- The same integration receipt verifies final independent approval after all input populations are reviewed and the result is regenerated; replacing the cited document subsequently makes that approved result stale.
- `native-india-regression-results.xml`: current shared/country regression receipt.
- `native-country-integration-results.xml`: current database/API regression receipt.
- `browser-results.json` and `screenshots/native-sources/india-payroll-*.png`: browser/worker verification.

Sample base/rule CSVs are synthetic fixtures. Their rates, cohorts and citations do not constitute a production country rule pack. Actual legal source qualification, state/cohort coverage and consented payroll pilots remain required work.

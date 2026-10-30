SYNTHETIC annual GST candidate example - not a client pilot

This packet exercises the optional India annual assessment on the existing
tax-turnover-bridge workflow. It does not prepare or file GSTR-9 or GSTR-9C,
verify a registration, or establish a professional tax conclusion.

Use an India engagement for 1 April 2025 to 31 March 2026. The financial
reconciliation date is 31 March 2026. The separately declared rule review date
is 30 October 2026; do not substitute it for the financial reporting date.

Retain each CSV as its own clean evidence version and prepare one source:
- scope.csv: turnover-scope, expected_rows 1, control_totals {}.
- books.csv: turnover-amounts, expected_rows 1, control_totals {"INR":"30000000"}.
- return.csv: turnover-amounts, expected_rows 1, control_totals {"INR":"30000000"}.
- adjustments.csv: turnover-adjustments, expected_rows 1,
  control_totals {"INR":"0"}. The explicit assessed-nil row is part of the
  declared population; an absent adjustment source is not equivalent to zero.

An independent reviewer must review all four source populations. Choose the
reviewed source versions in the scope/books/return/adjustments roles of the
turnover bridge. Keep the account/reporting currency INR.

In the annual GST candidate fieldset, enter the facts from
parameters-and-expectations.json. Enable the assessment explicitly. PAN-wide
aggregate turnover is 30000000 INR; other PAN turnover is an explicit zero.
Population completeness is a synthetic declared fact in this packet, not
proof of real PAN-wide client completeness. For real work, substantiate it and
the taxpayer classification with retained evidence and independent review.

Expected synthetic mechanics:
- The registration turnover bridge agrees exactly at 30000000 INR.
- GSTR-9 is CANDIDATE_REQUIRED.
- GSTR-9C is CANDIDATE_THRESHOLD_NOT_EXCEEDED.
- Statutory qualification is false and filing status is NOT_ESTABLISHED.
- Blank turnover fields remain null; they are not converted into zero.
- Clear the aggregate/other turnover and completeness declaration to exercise
  pending review and blocked approval.
- An author cannot approve their own result. Independent approval records the
  reviewed comparison/candidate assessment, not a statutory filing or opinion.
- XLSX Source and review metadata retains annual_gst_assessment and the exact
  declared scope. Rejecting a depended-on source makes the saved result stale
  without rewriting its historical body.

Profile limits: assessed FY 2024-25 and 2025-26 only; contiguous full-year
registration partitions; PAN-form GSTINs accepted by the existing bridge.
New/cancelled registrations, mixed regimes, composition status, other identifier
profiles, missing facts and out-of-profile review dates need separate review.
Legal source retrieval limitations are recorded in
../../legal-sources/india-annual-gst-candidate-review.json.

The hosted annual-gst-release.spec.ts uses the real BFF login, evidence upload,
configured ClamAV, source jobs, form submission, independent review and export.
Source setup/review is through APIs; the annual calculation and approval flow
is exercised through the UI. This is synthetic engineering validation only.

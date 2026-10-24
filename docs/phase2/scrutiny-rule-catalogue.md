# Population scrutiny rule catalogue

Reuses `app.modules.audit_analytics.engine`, version 2.0.0. The engine operates on the selected actual population in DuckDB with DECIMAL monetary values; floating point is limited to distribution statistics. Outputs retain source journal IDs, rule/version, parameters and applicability. Findings are investigation candidates, not fraud conclusions or performed procedures.

- J01 Weekend postings — posting date and configured weekend days.
- J02 Public holidays — explicitly configured calendar.
- J03 After-hours postings — reliable source timestamp, timezone and business hours required.
- J04 Round amounts — actual amount and configured rule.
- J05 Duplicate journals — journal/account/amount.
- J06 Near duplicates — journal/account/date/amount.
- J07 Unusual descriptions — actual source descriptions and parameters.
- J08 High-value entries — configured amount threshold.
- J09 Materiality exceedance — supplied materiality.
- J10 Manual year-end entries — source manual flag and year end.
- J11 Post-year-end reversals — actual reversal reference/year end.
- J12 Unusual debit/credit combinations — normal account classification.
- J13 Rare accounts — population account frequency.
- J14 Unexpected account pairings — approved expected pairings required.
- J15 Dormant accounts reactivated — prior activity required.
- J16 Suspense postings — approved suspense mapping.
- J17 Unexpected negative balance — normal classification/sign convention.
- J18 Large activity changes — prior activity required.
- J19 Sequence gaps — confirmed numeric source sequence required.
- J20 Posting/document-date gap — actual document date required.
- S21 Benford first digit — suitable naturally occurring monetary population required; applicability is not universal.
- S22 Amount frequency — source amounts.
- S23 Amount outliers — selected distribution/threshold parameters.
- S24 Unusual daily velocity — actual posting dates.
- S25 Counterparty/user concentration — actual counterparty or source user required.

Missing inputs produce explicit applicability/coverage limitations rather than invented fields. Use the existing Analytics workspace for detailed parameters, source drilldown, working-paper references and sampling. The new transaction investigation graph adds real account/journal posting edges, not a separate scrutiny engine. Existing TensorFlow.js anomaly/classification suggestions remain advisory and cannot override deterministic reconciliation or review decisions.

The Phase 2 ledger aggregate performance receipt does not benchmark all 25 rules. Existing QA corpus and analytics rule tests remain relevant, but new provider/native schemas, sparse source metadata, concurrent million-row runs and all requested scrutiny variants still need qualification.

# Audit analytics catalogue — ruleset 2.0.0

All 25 rules operate on the full non-opening journal-line population supplied by one committed snapshot. PostgreSQL streams rows into a temporary disk-backed DuckDB database; this workspace is deleted after the run. Rule definitions, versions, parameters, mapping context, snapshot, tested population, counts, severity, calculation predicate/evidence and timing are persisted. All flagged line exceptions are stored in audit_findings; individual rule responses preview at most 20 exception IDs. Results are indicators requiring professional investigation, never fraud or misstatement conclusions.

- J01 weekend: configured Python weekday indices, Monday=0. Default Saturday/Sunday is configurable business context, not an assertion about every UAE organization.
- J02 public holiday: explicitly supplied applicable holiday dates. Missing calendar is not_testable. This release does not guess lunar holiday dates or fetch an authoritative calendar automatically.
- J03 after-hours: reliable timezone-aware source timestamp plus declared business timezone/hours; otherwise not_testable.
- J04 round amounts: positive multiples of a configured round unit above the unit threshold.
- J05 duplicate journals: repeated account/debit/credit signatures under distinct journal references.
- J06 near duplicates: account-set-partitioned neighboring journal amounts/dates within configured ratio/day bounds, excluding exact signatures. This scalable heuristic is not exhaustive fuzzy matching.
- J07 description irregularity: configured case-insensitive keyword matches.
- J08 high value: amount >= high_value.
- J09 materiality: amount > materiality; this is a reviewer-supplied threshold, not an ISA materiality computation.
- J10 manual year-end: known source manual indicator within year_end_window before/on the configured year end.
- J11 post-year-end reversal: source reversal reference and posting after the configured year end within the window. A subsequent-period snapshot may be needed; do not claim the test ran without reversal metadata.
- J12 debit/credit pattern: entries opposite the approved account's usual balance direction, adjusted for contra accounts. Ordinary legitimate movements can trigger this broad review rule.
- J13 rare account: account line count <= rare_count.
- J14 pairing: source journal account pairs outside explicitly configured allowed pairs.
- J15 dormant reactivation: activity beyond dormant_days from a supplied prior last-activity date.
- J16 suspense: postings to a source/approved group explicitly named suspense.
- J17 unexpected negative balance: negative aggregate balances in normally debit-balance categories, with contra handling.
- J18 activity change: current absolute activity exceeds a configured multiple of supplied prior activity, or activity against an explicit zero prior base.
- J19 voucher gaps: numeric sequence gaps only when the caller asserts that numbering should be sequential within this snapshot. Resets, multiple series and intentional voids need professional investigation.
- J20 document-date gap: absolute date difference exceeds configured days; missing document dates are not tested.
- S21 Benford: explicit natural-population eligibility, positive-value count, distinct-value minimum and range/span checks precede chi-square analysis. It reports a population-level result, never individual fraud allegations or transaction risk factors.
- S22 frequency: a repeated amount exceeds configurable minimum count and frequency ratio.
- S23 outliers: amounts above Q3 plus a configured multiple of IQR, using DuckDB DECIMAL quantiles.
- S24 velocity: daily posting counts exceed a configured threshold.
- S25 concentration: counterparty/user line counts exceed a configured share of the population. Missing identities are not silently treated as one party.

Public-holiday calendars, prior-period activity, reliable timestamps, source numbering semantics and approved pairings are inputs, not synthetic assertions. Missing prerequisites yield not_testable and zero tested population. Full-population coverage means all eligible records are considered; it does not establish source extraction completeness. False positives are expected for routine closing entries, legitimate repeated postings, recurring counterparties and normal credit/debit movements. Thresholds and evidence require professional review.

Results store the mapping snapshot used at execution, so later mapping edits do not rewrite historical evidence. The mapping-profile history, original financial snapshot and stored parameters support independent reproduction. A future replay UI can reconstruct these archived parameters; no UI was added.

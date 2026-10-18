# Evidence matching

Invoice or bank-style extracted fields can be compared with authorized active journal lines. Signals are exact Decimal amount, currency, posting date, counterparty and reference substring. Weights are 4, 2, 1, 1 and 2 out of ten. Missing information lowers the score. The score is rule agreement, not a calibrated probability and not a confirmed accounting match.

The general UI compares the first fifty active ledger lines; the API can evaluate a specifically authorized journal ID. This is bounded candidate comparison, not a full-population fuzzy search. Accept/reject decisions require evidence-review permission, an exact signals hash and current extraction/ledger sources; immutable decision records preserve rationale and lineage. Accounting records never change.

The fifty synthetic matching cases have independently specified agreement/mismatch amounts. Acceptance is a recorded reviewer judgment, separate from an unconfirmed machine suggestion. Loan-master, lease schedule, credit-note, asset-master and VAT-claim specialized matching adapters are not implemented.

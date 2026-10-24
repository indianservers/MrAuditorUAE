# Transaction reconciliation rules

The existing balance reconciliation engine remains unchanged. The additional transaction engine compares selected actual ledger lines with a retained supporting bank table or another authorized snapshot. It performs no accounting postings.

1. Currency, explicit Decimal tolerance and date tolerance must agree. Conflicting known counterparties prevent matching.
2. Unique reference + amount + date candidates take precedence.
3. Unique amount/date candidates can be proposed when reference matching is absent. Competing source or destination rows remain unresolved.
4. One-to-many/many-to-one/bounded many-to-many groups require the same nonempty normalized reference, currency and counterparty, bounded dates, and sum agreement. Default maximum group size is three, configurable up to six. Aggregate agreement does not assert individual payment allocation.
5. Equal candidates remain ambiguous; every unmatched source/destination row is retained. Totals are separated by currency. There is no implicit currency conversion or cross-currency netting.

Exact amount and tolerance candidate searches use sorted amount indexes. There is no unrestricted subset-sum search. Maximum 20,000 transactions/side; larger sources require deliberate partitioning. Match state is a machine proposal; independent reviewer decisions are immutable result versions.

Auditors can accept a proposed match with a recorded rationale, or create an existing finding/evidence request from an actual unmatched source/destination row. These actions create new immutable result versions; they do not rewrite the original proposal. Independent result approval stays separate from auditor acceptance. Same-snapshot self-reconciliation is rejected.

Bank, cash, receivables, payables, confirmations, intercompany, inventory, payroll and fixed-asset modes share this accounting comparison engine. These labels do not establish specialized statutory reconciliation qualification. UAE VAT mode requires the package capability. India GST and TDS/TCS statutory modes return an explicit not-qualified error and remain Phase 3 work.

Ageing consumes uploaded authoritative open amounts and due dates. It never assumes every GL debit is unpaid. Buckets, as-of date and any explicit document-date fallback are recorded. Credit items remain signed; totals are per currency. Optional control-account comparison uses actual source balances and records differences without posting adjustments.

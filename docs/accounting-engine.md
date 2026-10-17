# Phase 2 accounting engine

The original Phase 1 identity, tenant context, permission checks, metadata APIs, AI transport, workers and audit events remain in use. Accounting adds scoped immutable source facts and deterministic calculation services. PostgreSQL remains authoritative; DuckDB is a temporary per-operation analytical workspace that is closed/deleted afterward. No permanent secondary ledger or frontend exists.

## Convention and scope

Debits and credits are separate nonnegative NUMERIC(28,8) values. Signed amount = debit − credit. Transaction and functional currency values are retained separately. Functional amounts require either the same currency at rate 1 or an explicit positive source exchange rate; there is no inferred FX rate. Unsupported precision is blocked instead of silently rounded. Source-provided base amounts are preserved separately from source currency amounts. Ownership/monetary calculations never use binary floats. Statistical distribution calculations may use floats, without altering ledger amounts.

Every fact links tenant, client, legal entity, financial period, creating identity and batch/snapshot. Scope composite FKs enforce tenant/client/entity and tenant/entity/period alignment. Journal lines link to an account, journal, source record and snapshot. Accounts are entity-wide masters; their period reference records the origin period, while ledger facts identify their own period. Source account code prefixes do not determine classifications.

## Ingestion and activation

POST an accounting import with a private source file and JSON options. File content is hashed and versioned before parsing. The upload response is a batch reference; GET the batch for its source snapshot ID. Preview is bounded to 20 rows. Validation parses incrementally, normalizes records and bulk-inserts source rows in batches of 1,000. Raw source rows and canonical staged values are separate JSONB fields and immutable. Invalid rows are retained with row-level blocking results; an invalid file can never be activated.

Commit locks the population scope, requires validated state, inserts canonical accounts/journals/lines set-wise and activates the batch atomically. No partially active ledger survives failure. One active journal/GL population exists per period; concurrent GL and journal commits share a lock. A replacement requires an explicit supersedes_id. Historical source and ledger facts remain available through their snapshots. Exact file/config re-import returns the existing batch and avoids a second object write; a different approved mapping can create a separate version requiring explicit replacement.

Chart-of-accounts and trial-balance imports are supported separately. TB-only sources do not create invented journals. TB reports include a journal_level_testable flag. Account metadata includes parent code, source group, standard classification, statement group and contra-account flag. Approved code and source-group mapping profiles append versions, record an explicit mapping-profile reference and update account classification metadata. Approved rules are reused for newly encountered unmapped accounts; AI never writes the ledger.

## Trial balance

Opening = sum(opening base debits − base credits). Period debit/credit exclude opening lines. Closing = opening + period debit − period credit. All grouping is by the selected snapshot and functional currency. Reporting exposes exact amounts plus a currency-specific rounded display value. Babel supplies default currency precision; POST /accounting/currencies configures explicit precision and ROUND_HALF_EVEN or ROUND_HALF_UP. The exact values remain the reconciliation inputs.

The accounting_period_balances and general_ledger_transactions security-invoker views expose active populations. GET ledger/journals defaults to active batches; an explicit snapshot permits historical inspection. Reports and resource lists paginate. Trial-balance account aggregation is performed in PostgreSQL; account lists, rather than all journal lines, are materialized for report assembly.

## Performance boundaries

CSV parsing, source-row staging, set-based ledger activation, server-side result cursors, disk-backed DuckDB and streamed findings/sample insertion avoid population-sized Python ORM object lists. DuckDB has a 1 GB memory setting, two execution threads and a spill directory. The million-line file/engine benchmark is separate from the 10,000-line PostgreSQL benchmark; see evidence JSON and phase-2-report.md. Connection synchronization currently retains bounded native XML packages and temporary derived connector CSVs; it is not certified for million-line live Tally/Zoho extraction. No partitioning has been introduced without workload evidence.

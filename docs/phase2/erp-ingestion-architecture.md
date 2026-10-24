# ERP ingestion architecture

One application, PostgreSQL tenant database and accounting engine remain authoritative. Existing connection secrets, raw source objects, import batches, source records, account identities, snapshots and validation receipts are reused. No new financial ledger or second ERP database was introduced.

The integration center reads `/connectors/catalogue`. Eleven provider families are visible. Zoho has an existing regional OAuth/API adapter; Tally has an existing local agent/XML path. Both still require authenticated environment qualification. Busy, Marg, SAP Business One, SAP S/4HANA, NetSuite, QuickBooks, Dynamics and Xero have **no implemented live adapter**. They explicitly offer normalized CSV/XLSX import. File upload is never represented as authenticated API connectivity.

The existing import wizard retains source preview, column/convention mapping, validation and explicit commit. Ingestion owns duplicate/supersession handling and immutable original-source receipts. Intelligence operations only select committed active snapshots in the engagement's entity and financial period. Comparative schedules require an earlier period. A chart of accounts is not treated as transaction evidence.

Source-table ingestion is separate from the accounting ledger: a CLEAN retained evidence CSV becomes an immutable supporting-table result, not a posted journal. Bank table columns: `reference,currency,amount,date`; open-item table columns: `reference,currency,open_amount,due_date,document_date`. Counterparty/account-code columns are optional. Date/decimal conventions are explicit. Invalid records fail the run; there is no silent row discard. Bound: 20,000 rows.

Credential-free parser/adapter tests do not qualify a provider. Required remaining work includes vendor-specific native schemas and adapters for the eight unimplemented live providers, sandbox contract tests, OAuth lifecycle/rate-limit tests and provider reconciliation certificates.

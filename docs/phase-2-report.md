# Phase 2 implementation and verification report

Verified 18 October 2026, Asia/Calcutta. Phase 2 only; no frontend or Phase 3 work was started.

## Architecture and implemented modules

Extended the existing Phase 1 modular monolith. Authentication, shared users/memberships, tenant RBAC, client/entity/engagement APIs, AI provider transports, jobs and audit events remain in use. New modules are accounting (schema/scope/activation and pure Decimal calculations), ingestion (CSV/XLSX/native Tally normalization), reconciliation, audit_analytics (25 rules/risk/sampling), connectors (Zoho/Tally/encrypted secrets), financial_ai (four structured suggestion tasks) and lineage (private immutable objects/hashes). DuckDB is per-operation temporary storage; PostgreSQL is the system of record. New approved source-group/code mappings record their exact profile/version and are reused without inferred account-code-prefix classifications.

## Database and migrations

The unchanged initial migration is followed by additive `0002_accounting.py`: 28 new physical tables, four security-invoker views, scope alternate keys, job metadata and account mapping-profile provenance. There are now 50 application tables plus Alembic's version table. The requested source-record-version, canonical GL, period-balance and lineage concepts use normalized views; two additional tables support resumable uploads and reviewed financial AI suggestions.

Upgrade â†’ downgrade â†’ upgrade succeeded on PostgreSQL 16.4, including after Phase 2 data existed. `alembic check` reported no new upgrade operations. Migration downgrade removes Phase 2 facts and retains historical prompt/permission catalogue rows referenced by Phase 1 execution history. All new tables have forced tenant RLS. The verified runtime role is NOSUPERUSER/NOBYPASSRLS. Composite FKs enforce tenant/client/entity and entity/period alignment; immutable source/journal tables reject UPDATE/DELETE. Exact table/view inventory and checks are in `evidence/phase-2-schema.json`.

## Implemented and tested

- CSV/XLSX and native Tally package upload, bounded preview, configurable mapping/encoding/separators/dates, source hashing/versioned snapshots, structured row validation, source controls, bulk normalization, controlled atomic ledger activation and explicit supersession. Exact file/config replay is idempotent; failed imports cannot become partially active ledgers.
- Debit-positive Decimal convention, separate source/functional amounts, explicit FX checks, opening/debit/credit/closing TB computation, currency display policies, accounts/groups/categories/contra metadata and approved mapping reuse/history. TB-only imports never fabricate journal-level validations.
- GL/TB comparisons, independent source count/total controls, source-to-normalized totals, journal/ledger counts, roll-forward, comparative movements, mapping/currency checks and scoped exception persistence. Missing controls stay insufficient_evidence/not_testable.
- All 25 analytical indicators, configurable thresholds, prerequisite checks, stored rule versions/parameters/mapping evidence, full eligible-population execution, persisted findings and deterministic weighted risk scores. Rule catalogue and false-positive limitations are in audit-analytics.md. Benford is suitability-gated and population-only; flags are not findings of fraud.
- Six reproducible sampling methods: random, systematic, MUS, high-value, risk-targeted and full selection. MUS discloses excluded negative/zero values and retains repeated-hit multiplicities. No ISA assurance is inferred from a caller-provided sample size.
- Four structured AI tasks: account classification, anomaly explanation, audit procedure suggestions and movement commentary. Suggestions cite supplied records, require human review, retain execution/template metadata and cannot alter immutable ledger facts. Token/request limits apply; a monetary cost ceiling is not claimed without provider pricing.
- Tenant-scoped resumable chunks with integrity validation, encrypted connector credentials, OAuth state/refresh/organization selection, supported Zoho pagination/resources/journal details, native Tally XML masters/voucher parsing and the Windows agent foundation.
- Authorized Celery operations for import validation (including parsing/normalization), analytics/risk scoring, reconciliation, sampling, financial AI and Zoho synchronization. Jobs persist operation/progress/result references, support explicit failed-job retry and pending cancellation, restore tenant context and reauthorize current permissions. Ledger activation remains explicit and transactional.

## API inventory and native smoke

Generated OpenAPI exposes **64 paths / 77 operations**, including preserved Phase 1 endpoints. Exact method/path/schema/security inventories are in `evidence/phase-2-openapi.json` and `evidence/phase-2-endpoints.json`.

Accounting routes cover imports/preview/validation/commit, private resumable uploads, accounts/journals/ledger/TB, mappings, currencies and lineage. Analytics covers runs/rules/findings/risk-scores; reconciliation covers runs/exceptions; sampling covers runs and paginated selected items. Connector routes cover Zoho OAuth/organization/sync manifests and Tally capabilities. Four financial-AI routes plus explicit review are available. Resource lists support bounded pagination and suitable client/entity/period/account/date/sort filters.

A native Uvicorn HTTP server returned 200 for liveness, readiness, Swagger and OpenAPI. A separate Celery solo worker consumed real Redis messages, validated a synthetic native HTTP upload, and processed/persisted a 25-rule analytics run in PostgreSQL. Evidence is `evidence/phase-2-live-smoke.json`; this is separate from in-process worker tests. Temporary verification processes are stopped after validation.

## Tests and static checks

Final run: **168 passed, 0 failed, 0 errors, 2 intentionally skipped**. Of the passing cases, **138 are unit/transport/security tests and 30 are PostgreSQL/API integration tests**. The original **52 Phase 1 tests pass**, with 116 additional passing Phase 2 cases. The original table-count assertion now explicitly checks the original 22 mapper classes while compiling all 50 tables, preserving its Phase 1 guarantee under an additive schema.

Overall statement coverage: **92.35%**. Explicit calculation/validation core coverage: **90.34%**, excluding ORM/schema declarations; the 85% core gate passes. Ruff check/format and mypy for 75 application files pass. Scripts/agent lint and agent CLI help were also checked. JUnit, coverage and summary evidence are saved alongside source artifacts under docs/evidence; a remote CI run was not triggered.

Tests exercise all 25 rules positively, clean populations, missing prerequisites and threshold boundaries; exact monetary behavior/FX/openings; corrupt/multi-sheet/macro/formula/archive inputs; mapping reuse; duplicate/superseded/blocked imports; reconciliations; deterministic samples/MUS edge handling; mock/failed provider transports; encrypted credentials; OAuth refresh/state replay/pagination; realistic Tally XML and native package imports; tenant/client-scope denial; resumable chunks; immutable ledger behavior under AI; and worker reauthorization/retry/cancel. The two skipped tests require explicit authorized live Zoho/Tally environments.

## Performance measured on this host

Environment: Python 3.12.10, Windows-11-10.0.26200-SP0, 12 logical CPUs, 31.84 GiB RAM. Sources are clearly labelled synthetic two-account workloads, not observed client data or an SLA.

The repeatable file/engine benchmark measures streaming CSV parsing/normalization, Decimal TB validation, independent source-control comparison and transient DuckDB analytics. It does **not** measure PostgreSQL writes. Results:

- 10,000 lines: normalization 0.404s; TB validation 0.034s; reconciliation 0.000017s; analytics 0.340s; peak process RSS 74.4 MiB. All rows processed and independent source totals matched.
- 100,000 lines: normalization 3.815s; TB validation 0.326s; reconciliation 0.000012s; analytics 1.793s; peak process RSS 123.4 MiB. All rows processed and independent source totals matched.
- 1,000,000 lines: normalization 38.122s; TB validation 3.365s; reconciliation 0.000011s; analytics 14.389s; peak process RSS 682.4 MiB. All rows processed and independent source totals matched.

The synthetic benchmark supplies insufficient context for 13 of 25 rules; those return not_testable instead of fabricated results. All 25 rule implementations have separate positive tests with appropriate inputs. An initial 256 MiB DuckDB run failed at the million-line signature stage; the bounded configuration was adjusted to 1 GiB with disk spill and rerun successfully. This failure is not counted as a successful benchmark.

A separate real PostgreSQL service benchmark processed **10,000 lines**: private upload 0.019s, validation/source staging 1.348s, ledger activation 5.915s, reconciliation 0.048s and persisted analytics 5.769s. Peak Python RSS was 150.2 MiB. These operation timings exclude final transaction-commit overhead and database-server memory; they are not HTTP latency figures. PostgreSQL throughput at 100k/1m lines has not been benchmarked. Raw evidence and repeatable scripts are provided.

## Implemented but not live integration-tested

Docker images/Compose and the GitHub Actions job were authored and structurally checked; Docker is unavailable on this host. Compose uses PostgreSQL 16/Redis 7 and a shared private source volume. Native verification used real PostgreSQL 16.4 and Redis 5.0.14.1 Windows runtimes on loopback. The database initialization shell script passes syntax validation and uses LF endings enforced by .gitattributes for Windows/Docker compatibility.

No authorized Zoho/Tally instance or paid AI credential was supplied. Real compatible AI transport is implemented/configurable and exercised with controlled HTTP success/failure/schema/timeout tests. No live provider connection is claimed. The Windows agent CLI/source/XML parsing and server resumption path are verified, but its customer-machine credential-vault/Tally/HTTPS flow is not end-to-end verified. S3 versioning/KMS/public-block requirements have mocked adapter tests; live IAM/KMS/version-retention behavior is unverified.

## Partial capabilities and explicit limits

Zoho stages supported chart data and published manual journals and preserves invoices/bills/credit notes/contacts as native evidence. This does not establish a complete auditable GL; every sync remains insufficient_evidence and provides the GL/TB report-upload fallback. Incremental watermark synchronization and full native report reconstruction are not implemented. A failed partial extraction retains received source objects and cannot masquerade as a reconciled population.

Holiday/prior-activity/pairing/source-timestamp/numbering contexts must be supplied and approved. Automatic authoritative holiday-calendar retrieval is not implemented. Source-group/code classification rules and approved mappings are deterministic; mock AI returns conservative reviewed suggestions, not validated accounting conclusions. Exact provider-currency cost ceilings, production object retention/legal holds/orphan housekeeping, separate non-owner runtime database grants and full professional approval workflows require further production work. A scheduled pending-job outbox sweeper and automatic Windows service installer are not included; explicit retry/resume/manual sync are available.

## Intentionally not implemented and Phase 3 readiness

No frontend, dashboard, UI images, final audit report, complete engagement procedure workflow, full IFRS disclosure engine or UAE tax/VAT/TP/DMTT computation was added. The tested accounting, source, permission, job and typed API boundaries are ready for Phase 3 backend/frontend integration. Customer deployment still depends on live connector/provider tests, production role separation, secret/object retention controls, backup/restore drills and load/security review. Phase 3 has not begun.

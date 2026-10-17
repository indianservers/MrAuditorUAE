# Architecture

AuditOS UAE is a Python modular monolith. FastAPI HTTP adapters use explicit Pydantic input/output schemas. Dependency injection obtains one SQLAlchemy async transaction, authenticates the identity, resolves an active membership and loads effective permission codes. A verified tenant context is set transaction-locally in PostgreSQL. Services query by tenant as well as resource ID; forced RLS adds a second isolation boundary.

## Boundaries

- `core`: settings, token/password primitives, permission catalogue, authentication dependencies, error contract and logging.
- `db`: declarative SQLAlchemy schema, async sessions and transaction-local tenant context. Alembic exclusively owns schema installation.
- `modules/identity`: first-run bootstrap, credential authentication, rotating refresh families. Shared users can belong to multiple firms.
- Metadata resources: clients, entities and engagements share `modules/clients/service.py` for tenant-scoped retrieval, whitelisted sorting, pagination, parent validation, version checks and audit writes. Route modules keep HTTP concerns separate. Separate domain services can replace the shared metadata service as Phase 2 business rules grow.
- `modules/ai_engine` and `infrastructure/ai_providers`: constrained diagnostic gateway, approved configuration, structured output contracts and provider transports.
- `modules/jobs`, `workers`: durable job rows, Redis delivery and independently running Celery workers.
- `modules/audit_log`: content-free append-only resource events in the same transaction as successful mutations.

The API execution flow is request limit/correlation → authentication → membership/permissions → tenant transaction context → service validation and SQL → explicit response schema → commit before response delivery. Database constraint violations return 409; request validation returns 422. Failed service transactions roll back. Refresh reuse is exceptional: family revocation commits before returning 401. Job submission commits the durable pending row before broker publication.

## Jobs and delivery

POST `/jobs/diagnostic` requires an idempotency key. A PostgreSQL advisory lock serializes creation for the tenant/key; a unique constraint provides additional protection. Repeating a pending submission republishes it, permitting recovery from publication failure. Completed jobs return the same job without re-execution. Delivery is at least once; a row lock and terminal-status check suppress duplicate execution.

Workers restore tenant context, recheck user/membership/tenant status and `jobs.execute`, and verify job ownership. Terminal completion or failure and timestamps are stored in PostgreSQL. The diagnostic only runs a connectivity query. Pending rows need client/operator redispatch after a broker outage; no scheduled outbox sweeper is supplied. Worker health uses Celery inspect ping and Compose's worker health check. API readiness checks database role safety, migration-table access and Redis; it does not claim workers are healthy.

## Future interfaces

A deterministic engine must accept typed facts and rule versions and return Decimal calculations plus reproducible validation evidence. It must not depend on a model-generated number. The AI interface accepts a bounded diagnostic request and returns validated explanatory content plus provenance/usage. A future approval service must accept a professional's identity, finding version and decision and append a decision event before any finding becomes authoritative. Phase 1 intentionally exposes no calculation or professional approval endpoints.

Future RAG/tool/computation modules can depend on these contracts and tenancy/authorization primitives. Retrieval must enforce tenant and source authorization before model context is assembled. Intensive engines may later move behind typed service interfaces; shared state and queue fan-out do not need premature microservices.

## Phase 2 extension

The Phase 1 boundaries above remain. Accounting, ingestion, reconciliation, audit_analytics, financial_ai, connectors and lineage now implement the next layer. See accounting-engine.md and the Phase 2 report for the canonical model, private object storage, explicit snapshot activation, bulk data paths and scoped worker jobs. The deterministic calculation interface is now implemented for trial balances/reconciliation/sampling; tax engines and complete audit workflows remain future work.

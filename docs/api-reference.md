# API reference

Swagger `/docs` in development and `/openapi.json` expose generated request/response schemas, OAuth2 security and shared error schemas. Versioned resources are under `/api/v1`. JSON errors use `{"error":{"code":"403","message":"Permission denied","request_id":"..."}}`. Invalid fields return a generic 422 without echoing potentially sensitive submitted values. Unique/FK conflicts and stale versions return 409; unauthorized tenant membership/permissions return 403; unavailable or cross-tenant resources return 404.

## Authentication and organizations

- POST `/auth/bootstrap`: JSON email/password/tenant_name, header X-Bootstrap-Secret; 201 Tokens, or 403/409. Explicit first-run setup only.
- POST `/auth/login`: OAuth2 form username/password; 200 Tokens or 401/429.
- POST `/auth/refresh`: JSON refresh_token; 200 new Tokens, replay/expiry 401.
- POST `/auth/logout`: JSON refresh_token; idempotent 204. This revokes the token family.
- GET `/auth/me`: Bearer JWT; id/email/status.
- GET `/tenants`: Bearer JWT; caller's active memberships and tenant metadata. Use one returned tenant ID in X-Tenant-ID.

All business/AI/job routes require Authorization: Bearer ACCESS and X-Tenant-ID. An unverified header alone never selects an accessible tenant. Access JWTs do not carry tenant privilege claims.

## Metadata

GET/POST `/clients`, GET/PATCH `/clients/{id}` require clients.read/write. Create example: `{"code":"CLIENT-001","name":"Your client","kind":"company"}`. Response includes id/tenant_id, status, timestamps and version. PATCH example: `{"name":"Updated name","version":1}`. Null updates are rejected.

GET/POST `/entities`, GET/PATCH `/entities/{id}` require entities.read/write. Create example: `{"client_id":"CLIENT_UUID","name":"Your legal entity","country":"AE","jurisdiction":"Dubai mainland","functional_currency":"AED","presentation_currency":"USD"}`. Country and currencies are validated against ISO catalogues.

POST `/financial-periods` requires entities.write. Body: `{"entity_id":"ENTITY_UUID","start_date":"2026-01-01","end_date":"2026-12-31"}`. Reversed dates fail schema/database validation.

GET/POST `/engagements`, GET/PATCH `/engagements/{id}` require engagements.read/write. Create example: `{"entity_id":"ENTITY_UUID","name":"Annual external audit","engagement_type":"External Audit"}`. Optional period_id must match the entity. Supported types: External Audit, Internal Audit, IFRS Review, Corporate Tax, VAT, Transfer Pricing, Pillar Two, General Compliance. Statuses: draft, active, completed, cancelled. Phase 1 accepts lifecycle metadata only and does not certify professional approval.

All three list routes support offset>=0, limit=1..100 (default 50), status, search (case-insensitive literal name substring), and sort=name/created_at/updated_at with optional '-' descending. Responses contain items/total/offset/limit. Sorting includes UUID tie-breaking. Updates require a version; conflicts return 409.

## AI

GET `/ai/health`, `/ai/models`, `/ai/executions/{id}` require ai.read. Health states configuration status and `real_provider_connectivity: not_probed` rather than claiming a provider connection. Executions expose metadata only.

POST `/ai/execute` requires ai.execute. Example: `{"task_type":"summarize_text","model":"mock-diagnostic","input":{"text":"Example non-confidential text"}}`. Response: `{"execution_id":"UUID","status":"completed","output":{"summary":"Mock diagnostic excerpt: Example non-confidential text"},"error_category":null}`. Provider failure returns a persisted execution with status failed, output null and a safe error category. Unsupported tasks/unapproved models return 422. Provider configuration unavailable returns 503. It never runs generated commands.

## Jobs and health

POST `/jobs/diagnostic` requires jobs.execute and header Idempotency-Key; 202 with durable job metadata. Retry a pending submission with the same key after publication failure. GET `/jobs/{id}` requires jobs.read and the same tenant authorization; it returns status/start/finish/error category. Jobs are diagnostic-only.

GET `/health/live` checks process liveness. GET `/health/ready` verifies PostgreSQL connectivity, safe DB role, migration-table access and Redis; failure is 503. GET `/api/v1/system/version` returns version/environment. These public diagnostics never expose secrets. Worker health is separately verified with Celery inspect ping.

## Phase 2 route families

Accounting: connections, imports (upload/list/get/preview/validate/validations/commit), resumable uploads (create/status/chunks/complete), accounts, journals, ledger, trial-balance (get/persist), mapping profiles (append/list/get), currencies and per-line lineage.

Analytics: runs (create/list/get), rules, findings and risk-scores. Reconciliation: runs (create/list) and exceptions. Sampling: runs (create/list/get with paginated selection). Long operations accept background=true and return a persisted job ID; poll the existing jobs API for status/progress/resource references. Job retry/cancel routes require the original identity and operation permission; cancellation is restricted to pending jobs.

Connectors: Zoho authorize/callback/organizations/organization/sync/sync-runs and Tally capability information. Financial AI: account-classification, anomaly-explanation, audit-procedures, financial-commentary and explicit suggestion review. See the generated phase-2-openapi.json and phase-2-endpoints.json under docs/evidence for exact methods, schemas and permission parameters. JSON decimal values are serialized as strings to preserve precision.

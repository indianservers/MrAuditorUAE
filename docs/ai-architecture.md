# AI architecture

`AIProvider` is a Protocol with `async generate(AIRequest) -> AIResponse`. Transport adapters depend on typed contracts, not audit/tax rules. The Phase 1 diagnostic route supports `summarize_text`; Phase 2 adds separately secured structured financial suggestion routes described in financial-ai.md. Unknown task types are rejected by Pydantic. Requests have a 12,000-character text limit, 64 KiB total HTTP body limit, and a configured output-token ceiling. Structured summaries have a 4,000-character output limit. No code or SQL execution, generated tool invocation or financial calculation exists.

The gateway requires verified tenant membership plus `ai.execute`. Models must be enabled in PostgreSQL; users cannot supply arbitrary model endpoints. Prompt templates are database-versioned. The gateway persists an execution row, validates the adapter output, records usage/duration and appends an audit event. A failed execution is returned as status `failed` with no generated content and a safe category; it remains auditable. No prompt or response content is stored by default. The response itself is available only to the authorized caller.

`MockProvider` is credential-free and returns an explicitly labelled deterministic excerpt. Its usage counts are word estimates identified by `usage_source=mock_word_estimate`. OpenAI-compatible transports use `/chat/completions`, server-injected credentials and JSON schema output. Local compatible endpoints may use the same adapter configuration. A provider must support strict JSON schema; compatibility with every local server is not promised. Network failures, 429 and 5xx receive bounded exponential-backoff retries; other HTTP failures are not retried. Transport timeouts and an outer execution deadline bound retries. Invalid JSON/schema is a failure, never a successful mock substitution. Provider content beyond 64 KiB is rejected; prompt/output content is omitted from error responses and logs.

Provider-reported counts are recorded when available. Missing usage remains NULL with source `unavailable`, not fabricated zero consumption. Cost accounting awaits a versioned price catalogue; no fabricated costs appear. AI health indicates configuration only and explicitly reports real connectivity as `not_probed`.

## Credentials and operator configuration

AI_PROVIDER configuration stores `env:AI_API_KEY`, not the API secret. Inject secrets using a managed secret store with encryption at rest and access-controlled runtime delivery. `.env` is for local development, excluded from Git, and is not an encrypted production vault. Only the deployment CLI `python -m app.manage` registers an environment-selected real model. There is no public credential/provider administration API. Rotating a runtime secret requires service recreation. Real provider connectivity was not verified without credentials.

## Separation and future extension

Deterministic computation owns all calculations/reconciliation and must return typed Decimal results with rule/input provenance. AI owns bounded interpretations, draft explanations and retrieval assistance. Human approval owns professional acceptance and sign-off; no model output is an accepted audit finding. Future approval records must bind reviewer, source evidence, content version and decision. No actual calculation or approval engine is included in Phase 1.

Future RAG should add approved source records, effective-dated regulatory documents, tenant-scoped chunks, embeddings and retrieval provenance. pgvector is optional today. Future tool requests should be declarative typed proposals processed by an allowlisted authorization layer; the current gateway has no tools parameter and rejects extra fields. Full-content retention requires a distinct explicitly authorized policy and migration, encryption, access auditing and retention enforcement.
# Phase 12 execution hardening

Enterprise AI worker authorization/source denial now writes a durable FAILED state and immutable stop receipt, preventing endless outbox dispatch of revoked work. Background services recheck current tenant/subscription entitlements. Tenant AI/ML quotas count admitted API operations; they are not provider charges or complete monetary budgets. Existing source permissions, human approvals and fixed tools remain mandatory.

ML immutable source/metadata reads avoid holding engagement write locks through Node training; final result publication rechecks authorization and deployment version. Synthetic benchmarks do not establish representative model/semantic quality. See `phase-12/ai-agent-evaluation.md` and `tensorflowjs-validation.md` for limits and production restrictions.

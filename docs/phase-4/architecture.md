# Phase 4 architecture

Phase 4 extends the existing FastAPI / PostgreSQL / Next.js application. It reuses users, memberships, clients, entities, financial periods, engagements, accounting snapshots, findings, sampling, private object storage and the provider gateway. Phase 5 reporting is excluded.

`audit_execution` is the service boundary for engagement access, typed preparation records, deterministic materiality, review decisions, source validation, completion checks and lifecycle transitions. Routes are under `/api/v1/engagements/{id}/audit`. Admin and client portal routes use the same identity system. The frontend uses the existing HttpOnly cookie BFF, shell, tokens, financial grids and query invalidation.

The relational envelope contains tenant, engagement, kind, reference, status, preparer and optimistic version. Strict task-specific Pydantic models validate the JSONB record body. Fifteen record kinds implement the logical entities requested in the brief without creating duplicate tenant/client/engagement tables. Each change creates an immutable snapshot and audit event; review actions also create immutable decision records. Source references are resolved against actual scoped records before persistence.

Ten new physical tables cover grants, tenant role policies, engagement policies, typed audit records, revisions, review decisions, evidence versions, client organization access, invitations and immutable methodology versions. Forced RLS and tenant foreign keys complement application authorization. Tenant role overrides replace global role defaults without modifying source or another firm's policy.

The frontend provides a reusable register/editor workbench, structured working-paper sections, financial table JSON, assertion selection, source selection, review actions, version history, evidence versions, review queue, completion controls, sampling selection and the 20-task AI catalogue. Lists load server pages of at most 100 records. Queries refresh while work is open; this is polling, not WebSocket collaboration.

Limitations: some advanced bodies and methodology editing still use structured JSON; evidence has attachment downloads rather than an active-content preview; there is no distributed document collaboration or durable audit-AI job queue. Read paths currently use conservative engagement locking; portfolio-scale load testing remains outstanding.

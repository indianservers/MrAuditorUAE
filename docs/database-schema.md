# Database schema

PostgreSQL 16+ is mandatory. The original 22 Phase 1 tables are implemented in `backend/app/db/models/platform.py`. Every entity table has a UUID key; the two role association tables use composite foreign-key primary keys. Record tables include UTC-aware created/updated timestamps. Tenant-owned records include `tenant_id` and an optional creating-user reference. Financial precision uses NUMERIC(7,4) / Python Decimal for ownership percentages. No financial amounts or tax calculations are implemented.

## Identity and organizations

`tenants` owns organization identity/status. `users` holds globally normalized email, Argon2id hash and active state. Email has unique and lower(email) unique indexes. `tenant_memberships` links user/tenant with a unique pair, status and tenant/id alternate key. `roles` and `permissions` form a global technical catalogue; `role_permissions` maps capabilities, and `membership_roles` assigns roles to an already tenant-specific membership. This permits one identity to hold different roles in multiple firms.

`refresh_sessions` stores only SHA-256 hashes of cryptographically random opaque refresh secrets, with user, family UUID, expiry and revocation state. Token hashes and family IDs are indexed. A user row is not proof of membership or client access.

## Metadata

`clients` has tenant-unique code, name, individual/company/group kind and status. `legal_entities` belongs to a client with a composite tenant/client foreign key, country, jurisdiction, functional/presentation ISO currencies and status. `entity_relationships` has composite tenant parent/child references, exact ownership percentage and effective dates. Self-ownership, invalid percentage and reversed dates are database-rejected. No relationship editing API is exposed yet.

`financial_periods` has entity/date boundaries, a unique tenant/entity/date range and a database check rejecting reversed dates. `engagements` has entity and optional financial-period references, engagement type/status and a version. Services ensure a chosen period belongs to the engagement entity. `engagement_team_members` references both engagement and membership with composite tenant foreign keys and a unique engagement/membership pair. Team assignments are schema foundations only.

Clients, entities and engagements use SQLAlchemy optimistic versioning. PATCH requires the current version; stale updates return 409. Database foreign keys prevent cross-tenant client/entity, relationship, engagement/team and AI-usage associations. Tenant-leading indexes support scoped retrieval; unique tenant/id keys support composite references. Audit events also have tenant/created timestamp indexing.

## AI and infrastructure

`ai_providers` contains adapter kind and a credential reference, never credential values. `ai_model_configurations` contains approved provider/model names, enable state and output limits. `ai_prompt_templates` versions technical prompts uniquely by name/version. `ai_executions` references model/template with tenant/requester, status, correlation ID, duration and safe error category. `ai_usage_records` belongs to a same-tenant execution and stores nullable provider token counts and usage source. Mock counts are labelled word estimates. Unknown provider usage remains NULL.

`background_jobs` stores status, tenant/user, idempotency key, start/finish and error category. `audit_events` contains action/resource/request correlation and limited JSONB details. A PostgreSQL trigger rejects UPDATE/DELETE. `system_settings` stores versionable-by-migration platform JSONB settings; no editing API exists.

## Isolation and migrations

Every tenant-owned data table except the identity membership directory has ENABLE and FORCE ROW LEVEL SECURITY. Its policy compares tenant_id with transaction-local `app.tenant_id` for both USING and WITH CHECK. No context means no rows. Identity directories remain accessible to authentication queries, and are never exposed via unrestricted APIs. Permission checks precede tenant context establishment. Queries also include explicit tenant predicates. Tests use a NOSUPERUSER NOBYPASSRLS role and verify direct SQL RLS denial, cross-tenant FK rejection, missing membership, and context reset across transactions.

`0001_foundation.py` freezes complete PostgreSQL DDL, indexes, constraints, policies, audit trigger and technical mock/prompt configuration. It does not import mutable ORM metadata or use create_all. Downgrade reverses the schema. New releases require reviewed forward migrations; never regenerate the initial migration of an existing installation. The authoring helper was a one-time implementation tool.

The stock postgres image does not ship pgvector; Phase 1 has no embeddings/RAG and does not require the extension. Install a vetted pgvector-enabled PostgreSQL image and enable the extension through a reviewed future migration when retrieval is implemented.

## Phase 2 additive schema

Migration 0002 adds 28 physical tables plus four security-invoker views, retaining all original tables. It also adds composite entity/client and period/entity alternate keys and operation/payload/result/progress fields to background_jobs. See accounting-engine.md and data-lineage.md for the new relationships. Source versions, canonical GL, period balances and record lineage use views to avoid redundant authoritative copies. Downgrade removes Phase 2 financial tables and job fields while retaining historical prompt/permission catalogue records referenced by Phase 1 execution records; back up before any destructive downgrade.

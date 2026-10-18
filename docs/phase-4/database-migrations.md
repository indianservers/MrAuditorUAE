# Database migrations

0003 adds nine tenant-scoped tables: audit_access_grants, audit_role_policies, audit_engagement_policies, audit_records, audit_record_versions, audit_review_decisions, audit_evidence_versions, audit_client_access and audit_invitations. It installs the expanded role/permission catalogue idempotently. 0004 adds immutable audit_methodology_versions.

The audit-record JSON bodies represent the logical acceptance, independence, planning, materiality, risks, programs, procedures, test execution/items, working papers, findings, review notes, completion, client requests/responses and AI suggestions. Version snapshots preserve all historical bodies. Dedicated relational tables hold identity/access, evidence object versions and immutable review decisions. This intentionally uses the brief's permission to reuse generic models.

All ten tables have forced tenant RLS. Engagement/member/client references use composite tenant foreign keys where applicable. Record revisions, decisions, evidence versions and methodology versions reject updates/deletes through the existing append-only trigger function. UUID keys and indexes cover tenant, engagement, kind/status and history lookups.

Verified on disposable PostgreSQL: upgrade 0001→0004, fresh preview installation and bootstrap, runtime role without superuser or RLS bypass, `alembic check` with no schema drift. Downgrade intentionally refuses destructive erasure of professional history; use verified backup restoration with a reviewed rollback plan.

The retained Phase 3 database was not reset. Tests use auditos_phase4_test; browser demonstrations use auditos_phase4_preview. Production backup/restore drills and deployment migrations remain operator responsibilities and were not represented as tested.

# Phase 4 implementation plan

Baseline: main cb94d52; clean checkout. Inspected authentication, live role joins, tenant RLS, generic engagement CRUD, 0001/0002 migrations, accounting analytics/sampling, private object store and structured AI gateway. Frontend baseline: 18 passing tests. Backend without integration opt-in: 138 passed, 36 skipped. Database-backed tests must be rerun against a disposable database, not the retained demo database.

1. Add scoped engagement roles, tenant-controlled role overrides and active/expiring membership checks. Preserve existing financial services; close generic engagement status bypass.
2. Add versioned methodology, engagement configuration, typed audit records, immutable revisions/review decisions, evidence metadata and client requests under forced RLS and composite tenant foreign keys.
3. Implement lifecycle, deterministic materiality, acceptance, independence, risks, programs/testing, working papers, review chains, findings and completion gates through one service boundary.
4. Integrate source references, private versioned evidence, client portal and modular AI tasks with citation validation and explicit human decisions.
5. Extend existing shell with administration and engagement workbenches. Read Next.js bundled documentation before editing frontend. Preserve reference design and existing routes.
6. Run migration, regression, security, concurrency and end-to-end checks; capture actual screens; report each capability's verification limits honestly.

Methodology is original guidance, not licensed standards text. Reporting-period applicability and local UAE adoption require independent professional validation. Phase 5 reporting is excluded.

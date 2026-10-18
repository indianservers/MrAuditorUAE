# Phase 5 architecture

Phase 5 extends FastAPI/PostgreSQL, preserving source imports, financial normalization, audit analytics, provider gateway, identity, engagement access and the React shell. Reporting assumptions use Phase 4 AuditRecord, AuditRevision and ReviewDecision. Migration 0005 adds a global immutable standards registry and tenant-owned immutable CalculationRun snapshots. Runs retain input JSON, dependency IDs/versions/status, methodology version, Decimal-string results and SHA-256. Triggers reject UPDATE/DELETE; forced RLS applies even to the non-superuser table owner.

Flow: committed import → approved profile → approved weighted mapping → independently approved journals → adjusted balances → immutable financial run → validation → independent Manager/Partner review → reviewed export. Calculators never alter source journals. Dependencies are rechecked before release/export; stale runs remain available as drafts.

Calculations are synchronous with bounded inputs: 20,000 exposures/assets/accounts and 100 group members. No new calculation worker or shared result cache is implemented. Existing background jobs remain operational. Run listings are paginated; grids virtualize rows. See benchmarks.json for local CPU measurements excluding database/network/concurrent exports. Exports are authenticated, generated in memory and audited. No Phase 6 work was started.

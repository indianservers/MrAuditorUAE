# Database migration review

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Head: 0012. Clean disposable database auditos_phase12_migration_test migrated from zero. Guarded existing synthetic database upgraded from 0011 to 0012 without recreating ledger data; current ledger count is 250,024. verify_phase12_recovery.py restored the complete migrated schema/data and compared every table. clean-migration-check.txt records Alembic metadata comparison when run.

0012 adds encrypted MFA fields/session assurance and four operational tables; tenant-owned subscription/usage tables FORCE RLS, platform operations are immutable. Existing access tokens are session-bound on new issuance; development-only old fixtures are not a production migration strategy. Review production session expiration/sign-in communications before rollout.

Migrations preserve regulated histories. Downgrade refuses destructive archival. Production large-DDL lock timing/index strategy and exact previous-release compatibility require staging rehearsal; no live production upgrade or rollback was executed. Snapshot before change, maintain migration journal, test forward repair and restore. Never use ORM create_all in a deployment.

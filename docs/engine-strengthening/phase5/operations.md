# Configuration, migration and recovery

No Phase 5 SQL migration is required: obligations use typed existing audit JSONB bodies and immutable revisions; notifications use existing GRC snapshots; AI uses existing execution records; connectors use existing runs/checkpoints. Alembic head `0020_foundation_periods` is required. The isolated verification runner creates/migrates only `auditos_final_verification_test`; it never migrates the working application database. The restore script creates a fresh timestamped `auditos_final_restore_test_*` database and does not overwrite existing databases.

## Reproduce locally

From repository root, with the existing local PostgreSQL/Redis QA configuration available privately:

```powershell
.\backend\.venv\Scripts\python.exe scripts/final_verification_run.py prepare
.\backend\.venv\Scripts\python.exe scripts/final_verification_run.py .venv/Scripts/python.exe -m pytest tests -q --tb=short --junitxml=../docs/engine-strengthening/phase5/backend-results.xml
.\backend\.venv\Scripts\python.exe scripts/final_restore_check.py
.\backend\.venv\Scripts\python.exe scripts/build_final_readiness.py
```

The test runner disables external AI and uses an ephemeral connector-encryption key when none is supplied. That key is test-only, never printed, and is not a production credential-backup strategy. Synthetic databases and dumps remain inside local runtime storage for inspection. Do not use the destructive integration fixtures on an ordinary application database. Live smoke opt-in flags must remain disabled for this campaign.

Run `npm test` in `ml-engine`; run `npx vitest run`, `npx tsc --noEmit` and scoped ESLint in `frontend`. Model tests use actual TensorFlow.js JavaScript CPU training, not a mock model. Native `tfjs-node` binding qualification remains separate.

## Deployment prerequisites

1. Freeze scope and release hashes. Review backend/frontend failures and intentional skips in retained reports; no absence-of-errors readiness inference.
2. Back up the database, private versioned object storage, model artifacts and separately protected encryption keys. Restore to an isolated destination and verify row/control totals, object hashes, evidence downloads, approvals and authentication. Establish and rehearse production RPO/RTO independently; the included local test checks counts and object hashes only.
3. Apply migrations as a separate controlled job with a rollback/restore point. Test populated upgrades and previous-release compatibility in staging; no new Phase 5 schema change is a substitute for this rehearsal.
4. Run API, workers and a single scheduler with the queues required by `docker-compose.yml` and the existing phase12 deployment runbook. Deploy a real scanner and verify fail-closed quarantine, durable outbox recovery, job cancellation and private storage. Synthetic scanner/broker doubles are test-only.
5. Configure signing/MFA/connector keys through the secret store, TLS/origin allowlists, least-privilege DB/RLS, private S3/KMS, persistent model storage, resource limits, monitoring, retention and redacted logs. Local configuration currently does not prove these production services are configured.
6. For language assistance, set `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, timeout/token caps and approved DB model/provider records. Enable `AUDIT_AI_EXTERNAL_APPROVED` only after disclosure approval. Exercise the scoped runtime endpoint and approved evidence workflow; a recent success observation is not an ongoing health guarantee.
7. For each connector, use the provider/edition-specific requirements in `connector-register.json`. Configure `CONNECTOR_ENCRYPTION_KEY`, registered callbacks and `CONNECTOR_ALLOWED_ORIGINS` as applicable. OAuth and session/basic/partner credential flows differ. Reauthorize expired/revoked grants. Verify origin-pinned pagination, rate limits, partial failures, retries, reversals/deletions and independent GL/TB/COA controls before activation. QuickBooks webhooks require the configured signature verifier; webhook hints are not a complete ledger.
8. Review production professional, security and customer acceptance gates. Existing release-gate controls remain in force. No external deployment was performed.

## Known operational boundaries

Compliance reminders are explicit in-app records; external delivery and scheduled reassessment are not enabled by this change. The calendar is bounded to 200 obligations per response and reports the bound. Connector success lookup is bounded to 100 attempts; an older successful run can exist beyond that window. Lag is time since an observed successful extraction, not proof of source-data freshness. Rules, model validation and live-provider controls must be qualified for actual client scope.

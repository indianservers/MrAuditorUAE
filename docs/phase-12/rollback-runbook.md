# Rollback runbook

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Application deployment rollback remains NOT_TESTED. The successful local database/object recovery drill does not replace it.

Before rollout, record previous image digests/configuration, schema compatibility and reversible feature-flag changes; take a consistent backup and pause scheduled actions. On failure: stop traffic/writes/Beat, preserve immutable events and task IDs, switch to the verified prior artifact only if compatible with the current schema. Verify health, session revocation, tenant isolation and exact financial smoke fixtures. Reconcile outbox receipts before restarting workers.

If schema/data incompatibility requires recovery, restore a verified snapshot into a new isolated destination and reconcile any later professional work; obtain acceptance before traffic change. Existing immutable-history migrations intentionally refuse destructive downgrade. Record actual service recovery duration, data loss/window and approver. Do not run DROP/TRUNCATE or discard regulated histories to force a rollback pass.

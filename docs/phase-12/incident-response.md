# Incident response

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

SEV1: suspected tenant exposure, material financial corruption, unauthorized approval/action, unrecoverable service/data. SEV2: major module/queue degradation or failed backup. SEV3: limited nonmaterial defect. Appoint commander and evidence custodian, preserve immutable receipts, restrict affected features, record request/release/tenant IDs without copying client content into alerts. Follow controller/legal communication decisions.

- Database outage: fail readiness, stop mutations/Beat, inspect private connectivity/role/storage, restore only via DR acceptance.
- Redis outage: auth/rate controls fail closed; preserve pending outboxes, restore broker, replay idempotently.
- Failed migration: stop rollout, retain snapshot/logs, use reviewed forward repair or isolated restore; no automatic destructive downgrade.
- Failed backup: page on freshness, stop declaring recoverability, rerun isolated restore before resolution.
- Object-store failure: quarantine/unavailable state; verify exact object version/hash, never replace evidence silently.
- Scanner failure: preserve quarantine; block approval/download; refresh signatures and test scanner recovery.
- Worker stall: inspect queue/heartbeat/resource limits, restart current image, replay committed receipts without duplicate action.
- AI/provider failure: fail/partial status with missing evidence; disable affected provider, never invent completion or billing.
- ML resource exhaustion: terminate bounded child, mark job failed/cancelled, restrict feature and review dataset/model limits.
- Tenant exposure/compromised identity: suspend affected sessions/tenant, preserve logs/object versions, assess scope and notification obligations with counsel.

Paging, escalation contacts and incident-system integration require named operational owners; the console does not fabricate zero incidents when disconnected.

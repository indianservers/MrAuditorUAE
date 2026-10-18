# Observability

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Implemented logs allowlist timestamp, event, request ID, status, duration_ms, method, route template and release. Request bodies, credentials, prompts, headers and query strings are not serialized. Runtime request IDs are validated and returned to callers. Existing durable job/AI/ML receipts retain governed lineage. Health checks distinguish live from DB/Redis/schema/role readiness.

Operator services report measured DB/Redis readiness and explicitly NOT_MEASURED/NOT_CONNECTED for worker/backup/tracing integrations. deploy/alerts.yml contains readiness/backup/queue examples requiring actual exporters. Do not deploy empty alert expressions against nonexistent metrics and call monitoring complete. Connect logs/metrics/traces to an approved UAE-residency pipeline; add DB/queue/provider/ML-resource dashboards, error sampling/redaction and actual pager receivers. Test outages, stale backups, queue stalls and alert resolution in authorized staging. No tracing or alert-delivery success is claimed.

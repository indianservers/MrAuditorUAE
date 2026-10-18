# Disaster recovery

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Owner: designated service incident commander; customer/controller and professional engagement owners approve data restoration. Proposed targets (unaccepted): database RPO <=15 minutes with managed PITR; service RTO <=4 hours after declared regional outage. Local 43-second restore is not a hosted RTO promise.

1. Freeze writes/Beat, preserve queue/outbox and incident timestamps; identify clean recovery point.
2. Verify encrypted database backup, object version manifest, keys, configuration and previous immutable release.
3. Restore in an isolated permitted region/account; never overwrite source evidence.
4. Compare row hashes, RLS/role properties, immutable histories and object SHA/version references; run financial and authorization smoke tests.
5. Reconcile completed/queued jobs by idempotency, keep schedules paused, invalidate old sessions, rotate compromised credentials.
6. Obtain independent professional and incident-owner acceptance before DNS/traffic switch and write enablement.
7. Record actual RPO/RTO, data differences, communications and follow-up defects.

Region changes, cross-border copies and legal holds require controller/legal review. Production regional recovery and paging tests remain unexecuted.

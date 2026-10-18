# Findings and fixes

- HIGH, reproduced: IFRS reported current after real source replacement. Active source validation now propagates staleness and blocks old-profile recalculation; historical SHA is unchanged.
- HIGH, reproduced: ML extraction counted superseded and replacement journals (12 instead of 6). Active-batch extraction fixes the row count.
- HIGH, verified regression: ML lacked verifiable snapshot/mapping freshness. Receipts, read-time freshness and use-time guards now prevent stale consequential use. Legacy live-ledger datasets without receipts are conservatively stale.
- MEDIUM, reproduced listing gap: archived clients appeared in default active views. Default list filtering and explicit history filters are implemented. Parent guards and unfinished-engagement protection are tested; the original reason-field 422 probe is not misrepresented as an observed successful bypass.
- MEDIUM, lifecycle gap: safe draft archive/restore was absent. Explicit allowlist, prior-review/reference protection, reasons, permissions and restore revalidation now preserve history.
- MEDIUM, browser integration: a new record-detail read returned 405; a scoped GET endpoint now supplies the current record and is API/browser tested.
- MEDIUM, reproduced fast-action conflict: an action immediately following save could use the old version. Actions remain disabled until save invalidation finishes.
- MEDIUM, cache gap: mutation invalidation was confined to one tab. Tenant-only BroadcastChannel invalidation now refreshes other tabs; stale open forms still receive 409.
- LOW, source mismatch: audit search advertised reference or title but searched title only. Escaped reference/title OR filtering is implemented.

The raw before/after JUnit and browser logs remain available. Selector, missing-Origin and overlapping-fixture failures are harness failures, not additional application defects. Scope-wide residual risks are recorded separately, not marked fixed.

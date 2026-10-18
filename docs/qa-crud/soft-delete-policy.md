# Soft delete and retention

Clients and entities use reasoned status archival/restoration with optimistic versions. New children require active parents. Unfinished dependent engagements block archival. Default client/entity lists exclude archived records; explicit status filters retain access to history.

Only working papers, risks, VAT invoices, requests, planning records, programs and procedures support the new unused-draft archive/restore actions. Eligible states are DRAFT/IN_PROGRESS; referenced or previously approved/locked records cannot be archived. The same record id, immutable revisions and actor/reason audit events are retained. Restore revalidates links and owner access. Specialist records outside this allowlist require their own governed workflow. Source snapshots, journals, reviewed adjustments, evidence objects, review decisions, calculation runs and ML artifacts remain protected from generic hard deletion.

Current implementation uses status plus append-only revisions/events rather than new deleted_at/deleted_by columns. Archived draft references remain unique, so archival cannot free identifiers for duplicate history.

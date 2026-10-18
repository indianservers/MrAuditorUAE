# Model Registry

ml_registry_events is an append-only typed ledger for datasets, evaluated models, approval requests/approvals, per-family deployment history, inference, feedback and curated dataset versions. Composite tenant/engagement references, forced RLS and immutable triggers enforce scope/history. Private storage holds binaries. Earlier approved versions can be redeployed as explicit rollback. Lifecycle is reconstructed from events rather than mutating trained metadata. Rejection/deprecation UX, global production models and confidential cross-tenant pools are not implemented.

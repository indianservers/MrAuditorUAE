# Dependency propagation

Source replacement uses actual upload → validation → commit with `supersedes_id`. The regression first demonstrated IFRS `dependencies_current=true` after replacement; it now reports false, preserves the original SHA and blocks recalculation from the superseded profile. A newly reviewed profile and mapping produce a new run. Both small amounts and AED 1,000,000 → 1,100,000 revenue replacement are tested; the latter independently asserts AED 100,000 profit movement.

Read-time checking prevents delayed invalidation gaps. `CURRENT` and `STALE` are emitted by the new registry; stale items require controlled regeneration and independent review. `RECALCULATION_REQUIRED`, `REVIEW_REQUIRED`, `BLOCKED` and `SUPERSEDED` are not falsely claimed as a universal persisted status machine. Existing module transitions enforce review/lock/block states separately. No asynchronous automatic recalculation or automatic retraining was added.

See crud-final.xml and full-backend.xml. Exhaustive ownership, tax-group and monitoring event propagation across all 38 families remains partial.

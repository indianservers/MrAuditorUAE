# Regulatory rules architecture

Status: operational versioning and assessment foundation; professional regulatory content qualification remains incomplete.

`regulatory_rule_versions` and `regulatory_rule_actions` (migration 0017) are tenant-scoped, append-only, FORCE-RLS protected. Unique root/version and action sequence constraints plus transaction advisory locks prevent competing revisions. Proposals, independent approval, publication, rejection and controlled reversion append history. Reversion creates a new proposal; it never edits an earlier version. Firm Administrator publication follows independent review; the proposer cannot approve their own content.

Rules include country, framework, period basis, effective interval, declarative predicates, input/output requirements, legal citations, document hashes, retrieval dates and professional attestation. Official-domain checks and attestation requirements are safeguards, not legal validation. No numeric statutory rates are seeded by this phase. Unsupported or missing facts remain pending. Numeric predicate facts require exact paths into current reviewed intelligence events or approved records. Flat-rate assessment additionally requires its exact tax base to agree to a current reviewed lead schedule. Decimal arithmetic uses precision 80.

Selection uses the engagement's approved country/framework/entity and actual financial period. A future-period publication does not obsolete a prior-period receipt. A replacement applicable to the same period makes downstream work stale without changing its original values. Graph receipts include rule IDs and hashes. Permission checks are reapplied when reading retained results.

API prefix `/api/v1/regulatory`: GET/POST rules, rule detail, decisions, compare, impact; engagement assessments, checklists, India statements, report templates and reports. Lists are paginated. JSON rule editing is functional but requires professional curators; a richer typed authoring interface remains future work.

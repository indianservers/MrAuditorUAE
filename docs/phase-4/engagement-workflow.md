# Engagement lifecycle

The authoritative transition graph is `backend/app/modules/audit_execution/catalogue.py`. Statuses: DRAFT, ACCEPTANCE_PENDING, ACCEPTED, PLANNING, RISK_ASSESSMENT, FIELDWORK, REVIEW, QUALITY_REVIEW, REPORTING, COMPLETED, ARCHIVED, CANCELLED.

Generic CRUD can rename an engagement but cannot update its status; new records must start in draft. The transition API checks actor, live engagement permission, expected version, allowed edge and prerequisites. It preserves the prior/new state, reason, version and request ID in the append-only audit log. Completed, archived and cancelled engagements reject ordinary record edits.

Acceptance requires a completed structured questionnaire and independent approval. Entry into planning requires current reviewed independence declarations for all assigned members. Planning and materiality approvals precede risk assessment; approved risk and program records precede fieldwork. Review/reporting/completion evaluate outstanding work, notes, findings and required approvals. A human completion record addresses subsequent events, going concern, unadjusted misstatements and the human evidence assessment. No opinion is generated.

Quality review is policy-driven. An assigned Quality Reviewer cannot also hold a delivery-team grant or have prepared professional records. The endpoint requires the quality-review stage and a reviewed declaration. Subsequent record changes invalidate the quality decision. Firm administrators configure review chains before acceptance.

The integration scenario `test_complete_statutory_audit_human_workflow` executes the complete statutory-audit lifecycle through APIs with separate preparer and reviewer identities. It uses explicitly synthetic evidence and a declared scanner test double. Additional E2E tests use real frontend and backend services.

Legacy `draft` states work through uppercase normalization at the service boundary. Legacy `active` engagement metadata has no automatic Phase 4 approval mapping; an authorized data migration/re-acceptance decision is required for such records. Previously recorded completion is not retrospectively represented as Phase 4 assurance.

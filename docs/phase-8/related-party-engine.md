# Related Party Engine

Party and relationship workpapers reuse existing tenant/entity identity and normalized EntityRelationship ownership facts where both parties reference existing entities. Decisions distinguish RELATED, CONNECTED, UNRELATED and REVIEW_REQUIRED. Relationship type, ownership, control facts and effective dates are retained in immutable audit revisions.

GET /tp/engagements/{eid}/graph/{profile_id}?on=YYYY-MM-DD returns approved dated nodes and edges. Arithmetic ownership paths multiply ownership along each simple path, retain relationship IDs, expose common direct owners and flag cycles. Paths do not establish legal control, combine circular holdings or automatically apply a universal percentage test. Path growth is bounded at 10,000. The React Flow viewer supports zoom, pan and node repositioning; relationship editing uses reviewed workpaper forms. No graph edge changes a legal conclusion automatically.

Exact approved party names/identifiers and description keywords create ledger candidates. Fuzzy aliases, beneficial-owner registry integrations and automatic indirect-control determinations are not implemented. tests/phase8/test_relationships.py covers indirect ownership, common ownership, cycles and bounded growth.

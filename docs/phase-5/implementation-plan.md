# Phase 5 initial audit and plan

The working tree contains the completed local Phase 4 changes on top of main cb94d52. Preserve them; no reset or replacement of existing modules is authorized. Baseline verification: 218 backend tests pass with two live-connector skips; 22 frontend tests pass.

Inspected actual FastAPI routes, migrations 0001–0004, Decimal trial balances, functional/presentation currencies, immutable imports, Phase 4 grants/review chains/history/evidence, the provider gateway and financial grids. Missing foundations: no IFRS registry, approved reporting overlays, statement generator, specialized accounting schedules, group calculation snapshots or exports. Phase 4 has reusable strict records and approval services, but accounting approvals need additional permissions and source-dependency checks.

Implementation sequence:

1. Add a versioned standards registry with explicit coverage/status and period elections; do not treat reference metadata as implemented accounting.
2. Reuse engagement-scoped records/revisions/decisions for profiles, mappings, adjustments, assumptions, disclosure responses and financial approvals. Add immutable numerical calculation snapshots with forced tenant RLS.
3. Implement pure Decimal engines with hand-computed benchmark fixtures, then scoped services connecting real source balances and approved records.
4. Implement individual statements, comparatives, notes, cash reconciliation and deterministic consolidation within documented scope. Gate approval/export on checks and current dependency versions.
5. Extend the common AI adapter with sourced, review-only IFRS output; do not invent licensed content or paragraph citations.
6. Build the 16 requested workspaces using the existing shell/grids/editor, plus a financial designer and real exports.
7. Test migration, regression, financial accuracy, roles, concurrency and five API/browser demonstrations. Render sample exports, capture actual screenshots, build production and publish a candid scope report. Stop before Phase 6.

Official IFRS sources confirm IFRS 18/19 effective periods beginning 1 January 2027 with permitted early application. IAS 1 remains the earlier-period presentation unless a justified election applies. IFRS 19 eligibility and election are separate from recognition/measurement. Full IFRS for SMEs, authoritative text reproduction and automatic certification are excluded.

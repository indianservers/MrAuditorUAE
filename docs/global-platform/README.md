# Global audit foundation — UAE first

This increment retains one application, PostgreSQL database and codebase. It adds a per-user, per-firm working-country preference, frozen software country manifests and immutable engagement package bindings. It does not claim that every country's regulatory modules are implemented or legally qualified.

## Country context

Open **Country & regional settings** from the user menu (`/settings`). The selected country persists on the server, filters entity and engagement directories, clears incompatible browser scope selections and supplies defaults for new legal entities. Existing entities, currencies, engagements and historical approvals are unchanged. Portfolio dashboard summaries remain firm-wide.

All ISO countries can use shared audit workflows. UAE has the existing scoped UAE engines; other countries are explicitly `CORE_ONLY`. UAE corporate tax, VAT, transfer pricing, DMTT and e-invoicing preparation are rejected for non-UAE engagements. Reporting standards and functional currency still require an explicit entity/profile decision.

## Versioned packages

`backend/app/modules/jurisdictions/releases/2026.10.1.json` is a frozen software capability release. Each new engagement receives its legal entity's country, full manifest, version and canonical SHA-256. Database triggers prohibit updating or deleting these bindings. New audit revisions carry the package version and hash. Existing calculation rule versions remain independently recorded.

Future releases must add a new frozen manifest and an explicit registry selection; never edit released manifests. Updating a user's country or publishing a package must not repin existing engagements. An engagement upgrade workflow is deliberately not included in this first increment: it needs a reviewed, append-only transition and impact assessment.

Migration `0014` creates tenant-isolated tables and backfills bindings from existing legal entities using a migration-owned frozen manifest. It does not rewrite audit records, revisions, decisions or calculations. Downgrade is blocked to retain package history. Before migrating the local synthetic QA database, a private database backup was taken. `history-before.json` and `history-after.json` record matching full-row hashes for existing entities, engagements, working papers, revision history, review decisions and IFRS results.

## Functional dependency graph

Open **working-paper dependency graph** from an engagement audit workspace (`/engagements/{id}/graph`). Saved source references generate directed links; the view includes authorized working papers, immutable import snapshots and calculation/ML runs. Search, freshness filters, connected relationship tracing, source details and record/history navigation operate on persisted records. It does not accept decorative or unsaved links.

New working-paper revisions record input versions and snapshot hashes. Submission and approval preserve the saved input baseline. A changed or archived source marks consumers stale or blocked; this propagates through working-paper dependencies. Approval/locking rejects changed, cyclic, excessively deep or unverified dependencies until reassessed through the draft workflow. Approved status and history remain intact even when current freshness changes. Legacy records with references but no saved receipts are shown as `UNVERIFIED`; their historical snapshots are not retroactively recertified.

The graph is a bounded projection (300 records by default, maximum 1,000; up to 100 runs per calculation module). It reports truncation, excludes inaccessible records and does not expand dependencies outside the authorized engagement view. Full record registers remain available. It is not an automatic recalculation or automatic approval engine.

## API and checks

- `GET /api/v1/jurisdictions/packages`: country capability catalogue.
- `GET/PATCH /api/v1/jurisdictions/settings`: authenticated user's tenant-scoped preference; writes require the current version.
- `GET /api/v1/engagements/{id}/audit/graph`: permission-filtered dependency graph and pinned package receipt.
- Optional `country` filters on entities, engagements and workspace directory.

Meaningful regressions are in `backend/tests/qa_crud/test_global_platform.py` and `frontend/e2e/global-platform.spec.ts`. Browser verification uses the existing private synthetic QA credentials; no credentials are committed. Current verification results are recorded alongside this document. This increment does not replace the wider production release gates recorded in the previous QA campaigns.

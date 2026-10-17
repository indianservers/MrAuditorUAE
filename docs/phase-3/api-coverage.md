# Implementation contract established before coding

Authoritative API: Phase 2 OpenAPI, refreshed from the running app after additive Phase 3 read endpoints. Generated TypeScript schemas live in `frontend/src/types/api.generated.ts`.

- Authentication: existing OAuth form login, refresh rotation, logout, me, tenants. Same-origin Next BFF holds access and refresh in HttpOnly SameSite cookies. Mutations require same-origin checks. Tokens never enter localStorage or browser JSON responses.
- Access/context: add permission discovery and a tenant-checked context directory with bounded pages. Existing client/entity/period IDs are checked by backend RLS and service scope. Context switches reset dependent UI and query cache.
- Dashboard: add tenant-scoped SQL counts and bounded activity read; no invented progress, hours, deadlines or compliance ratings.
- Clients/entities/engagements: existing GET/POST/PATCH APIs, optimistic version on edits. Unsupported industry/TRN/team/deadline fields explicitly unavailable. No deletion contract exists.
- Integrations: existing connection list/create, Zoho authorize/callback/organization/sync, Tally capability, uploads/preview/validate/commit, job state and retry. QuickBooks/Xero are unavailable. Live credentials are required for actual provider verification.
- Trial balance: existing snapshot-based balance calculation; add backend totals and mapped counts. Browser only formats decimals. Prior-period variance not supplied; show unavailable.
- Ledger: existing paginated endpoint extended with parameterized search, amounts and journal filters; source detail via lineage. Filtered-page CSV exports accurately labeled; no full-population browser fetch.
- Analytics: existing run/25 rules/findings/risk APIs; backend aggregate charts added to avoid aggregating incomplete browser pages. Risk is an indicator, never proof of fraud. No reviewer-note persistence endpoint exists.
- Reconciliation: existing runs and exceptions. Checks/results from backend; no invented adjustments or resolution progress.
- AI: existing four structured tasks, approved model catalogue, suggestion review and source citations. Mock provider clearly identified. No invented conversation history, unrestricted chat or SQL.
- Compliance/audit programs: Phase 4/5 unavailable states; no financial/tax engines added.

Backend remains authoritative. Permissions on UI controls improve usability and never replace backend enforcement. All list fetching is bounded; dashboard charts use scoped backend aggregates.

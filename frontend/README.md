# AuditOS UAE frontend

Next.js App Router, React, strict TypeScript, Tailwind v4, local Inter variable font, Radix dialogs/menus/tooltips, TanStack Query, React Hook Form/Zod, Zustand layout preferences, Lucide, ECharts, React Flow, Motion, AG Grid Community, Vitest/Testing Library and Playwright.

## Local operation

Node 24 is required. `npm ci`; copy `.env.example` to `.env.local`; set the backend origin and exact public browser origin; `npm run dev`. The default browser origin is `http://127.0.0.1:3000`. `localhost` is a different origin and needs its own configured value. Backend and Redis must be running for login. Celery must be running for import validation, analytics and reconciliation jobs.

Provision an account using the Phase 1 bootstrap flow or existing firm administration. Client → detail drawer → add entity → add financial period. The entity drawer can create engagement metadata. Choose client/entity/period in the header; Integrations accepts source files; activation requires a separate confirmation. Then open Trial Balance, General Ledger or Risk Investigation.

No synthetic records are embedded in runtime code. The repeatable seed tool is `scripts/seed_frontend_demo.py`, explicitly gated by `DEMO_SEED=1`, targeting the disposable loopback integration backend at port 58000. It creates labeled synthetic records and writes a non-secret browser fixture manifest. It requires the existing disposable integration-test account. Never use backend integration tests against customer data: they reset identity/business tables.

## Authentication and deployment

The browser talks only to `/api/session` and the same-origin BFF `/api/backend`. Access and refresh tokens live in HttpOnly, SameSite Strict cookies; cookies are always Secure in production. Nothing sensitive is persisted in localStorage. Configure HTTPS and `AUDITOS_WEB_ORIGIN` to the exact public origin in production. Configure `AUDITOS_API_ORIGIN` as a trusted server URL; it is never a browser-controlled destination. Mutations reject missing or cross-origin Origin headers. Backend permissions and RLS remain authoritative.

The BFF counts upload bytes, restricts paths, forwards tenant headers, normalizes errors, disables caching and supports cancellation/timeouts. Login bodies are limited to 4 KiB. Uploads are limited to 64 MiB plus multipart overhead. Source files and secret credentials never receive public URLs.

Refresh rotation is serialized per token within a single Node process, with a short-lived result cache for concurrent tabs. **Multi-instance deployments need shared refresh serialization/session infrastructure before horizontal scaling.** Cookie transport is implemented; production HTTPS/proxy infrastructure has not been certified here. The CSP retains inline script/style support required by the current rendering/grid stack; a stricter nonce-based deployment policy is future hardening. `unsafe-eval` is limited to development in the configuration.

`npm run build` produces a standalone server. The Dockerfile copies standalone/static/public assets into a non-root Node 24 image. Compose supplies the internal backend origin and an explicit public origin. No cloud publication is part of Phase 3.

## Data grids and charts

`FinancialDataGrid` owns AG Grid modules, column definitions, density, page CSV export, layout persistence, pinning, resizing, reordering, filtering and row drill-down. Server pages are labeled; sorting/filtering inside the grid affect the loaded page. Ledger date/search/account/amount/journal-type filters and the separate sort selector execute on the server. No million-row download occurs. CSV export includes the filtered loaded page, with formula-injection protection.

Community modules are installed, with no Enterprise key or package. To enable licensed capabilities later, install the matching AG Grid Enterprise version, configure its valid license and register selected modules in the shared grid module. Expose grouping/pivot/Excel controls only after that integration is implemented and tested. No hidden Enterprise functionality is simulated.

ECharts is dynamically loaded. `FinancialChart` supports bar, line and donut views with accessible data alternatives; `RiskHeatmap` exposes keyboard-operable count cells. Data comes from scoped SQL aggregates. React Flow renders real source-record/snapshot/journal-line identifiers. No graph claims a supporting document exists if the API does not expose one.

Monetary values remain backend decimals. The formatting utility handles exact large integers, decimal strings and Decimal scientific-zero notation without floating-point financial calculations. Closing display values use backend currency rounding; other values are presentation strings. Entity functional currency supplies ledger/analytics labels. Prior-period balances/variance, full time-series account movements and reconciliation waterfalls are not invented.

## Verification

`npm run typecheck`; `npm run lint`; `npm test`; `npm run build`; `npm audit`.

For browser tests, start the local disposable backend on 58000 (seed) / configured API port (UI), Redis, Celery and frontend on 3000, run the backend tests first, then seed the browser fixture. Run `npx playwright install chromium` once and `npm run test:e2e`. The Playwright suite uses real backend mutations, creates synthetic clients/entities/imports, captures screenshots and writes evidence into `docs/phase-3`. `FRONTEND_URL` selects a different UI origin; set matching `AUDITOS_WEB_ORIGIN` before starting that server. The BFF-boundary test uses the same configurable origin.

Screenshots are not pixel-diff assertions: the supplied references contain fictional financial information, collage fragments and unavailable future-phase modules. The visual audit records matching structure and deliberate deviations. Chromium is the tested engine; other browsers and assistive technology require further validation.

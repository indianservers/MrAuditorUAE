# Interaction audit

Verification uses the real local Next.js BFF, FastAPI, PostgreSQL, Redis and Celery, with clearly labeled synthetic records. Provider integrations are not represented as live connections.

Verified in Playwright:

- Form login, protected workspace, HttpOnly/SameSite cookie properties; BFF rejects cross-origin mutations and unauthenticated data requests; session JSON contains no bearer tokens.
- Command palette navigation, Ctrl+K/Escape, sidebar collapse/expand and active navigation.
- Create client; view in a searchable grid; edit with optimistic version; client/entity/period selection; legal entity and period creation through actual APIs.
- Open real engagement, inspect a future Planning tab, set engagement context.
- Trial balance from the backend; select account; open linked ledger; open/close source drawer; lineage details.
- Ledger server pagination and description search, bounded page size; source-backed vouchers and debit/credit values.
- Run analytics as a real job; poll actual status; refresh run; select deterministic finding; request a clearly marked mock-provider explanation through the real AI gateway.
- Run reconciliation as a real job; display its actual insufficient-evidence result without converting it into success.
- CSV and XLSX import flows: source preview, worksheet selection for XLSX, custom column mapping, background validation, explicit activation and resulting backend trial balance.
- All ten main routes render; screenshot capture at desktop and native reference dimensions; responsive body bounds at six sizes.

Vitest covers buttons, pagination, tabs, unavailable/error states, accessible drawer, exact decimal formatting, CSV injection guards, scope reset, layout-only persistence, API errors/cancellation, grid controls and empty charts. Backend integration tests cover directory/period validation, summary counts, ledger filters and escaped wildcard searches, chart/finding aggregates, foreign-tenant denial and XLSX formula/worksheet guards.

Not live verified: Zoho OAuth/provider sync, Tally/Windows-agent connectivity, paid AI, production S3, Docker networking, production HTTPS, horizontal BFF refresh coordination. The UI exposes honest configuration states. Field export is loaded-page CSV; full-population/Excel exports are unavailable. Reviewer notes, document sign-off, obligation management and tax calculations are future-phase states.

Screenshots and result JSON/XML are the execution evidence. Accessibility testing is automated Chromium/axe plus keyboard checks, not a complete WCAG certification or screen-reader audit.

# Phase 3 reference and route mapping

All ten PNGs were opened individually before frontend implementation. References are design specifications only; no pixels are embedded in the product.

- 01 Executive Dashboard → `/dashboard`: four compact indicators, engagement list, insights, paired lower panels.
- 02 Client & Company Management → `/clients`: page tabs, search and status controls, dense client grid, creation and detail dialogs.
- 03 Accounting Integration Center → `/integrations`: connector cards, explicit pipeline, import history and validation drawer.
- 04 Trial Balance Explorer → `/financials/trial-balance`: dominant pinned-account grid, compact toolbars, right intelligence panel and bottom balance bar.
- 05 General Ledger & Journal Explorer → `/financials/general-ledger`: paginated transaction grid and source detail drawer. `/financials/journals` shares the population explorer.
- 06 AI Audit Risk Intelligence → `/audit/risk-intelligence`: charts above findings grid, selected investigation panel. `/audit/analytics` and `/audit/journal-testing` share the rules workbench.
- 07 Financial Reconciliation Studio → `/financials/reconciliation`: source cards, checks pipeline, exception grid and source details.
- 08 Audit Engagement Workspace → `/engagements/[id]`: selected real engagement, lifecycle and phase-specific tabs. Index `/engagements` provides selection.
- 09 AI Audit Copilot → `/ai-copilot`: contextual task list, structured execution cards, source context. No free-form unsupported chat.
- 10 Compliance Command Center → `/compliance`: obligation categories, configured-state cards, unavailable deadlines and future services.

Additional shell routes: `/financials/mapping`, `/audit/sampling`, `/evidence`, `/tax`, `/reports`, `/settings`, `/login`.

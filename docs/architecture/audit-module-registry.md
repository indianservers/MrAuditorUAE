# Audit module registry

The typed registry in `backend/app/modules/jurisdictions/module_registry.json` contains all **165 requested submodules across 13 categories**. `workspace.Module` validates definitions and rejects duplicate identifiers. The two Deferred Tax entries have country-specific identities.

The registry covers Engagement Setup; Scrutiny & Forensics; Reconciliation; Balance Sheet & P&L; Planning & Risk; Findings & Controls; Tax Practice; Group & Multi-Entity; Reporting; Client Collaboration; Report Studio; AI & Automation; Administration.

Each entry records a stable ID, category, name, description, country applicability, required permission, capability state, existing route and optional audit-record kind. Existing typed working-paper routes are reused. No operational route is emitted when permission, country support or required engagement context is missing.

States are `AVAILABLE_SCOPED` for an existing workflow still subject to historical QA gates, `PHASE1` for the new shared group workflow, `PLANNED` for future engines, `RESTRICTED` when not authorized, and `UNAVAILABLE_COUNTRY` when the package does not support it. A record count is computed only from authorized engagement records. An available generic workbench is not evidence that a statutory engine is qualified.

`GET /jurisdictions/modules` supports country, engagement and search. `/modules` provides searchable category navigation, availability and working links; the sidebar and global search link to it. Individual future features have informative registry descriptions, not fabricated operational screens or inert execution buttons.

Global search matches modules, authorized clients/entities/engagements, ledgers and audit records (papers, findings, IFRS reports), across all authorized engagements before applying result bounds. Specialist record permissions are checked again for each result. Result limits/truncation are explicit. Existing full registers remain available for exhaustive searches.

The catalogue version identifies graph definitions. The database remains authoritative for records, legal context, permissions, source receipts, review decisions and layouts. A second mutable copy of working-paper data is not introduced.

Future engine additions must provide a real route, server authorization, applicable country capability, deterministic tests and honest qualification status before changing a planned entry to available.

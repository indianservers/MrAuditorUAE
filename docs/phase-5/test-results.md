# Phase 5 validation evidence

Full regression: **238 passed, 2 skipped**, PostgreSQL/Redis, 83.18 seconds. The skipped tests require opt-in live connector credentials. See backend-results.xml. The Phase 5 subset contains 20 tests, including 13 independent calculator benchmarks and seven database workflows/parameter cases. A subsequent Phase4/5 run verifies final access/export refinements; see ifrs-results.xml.

Frontend: **22 unit tests passed**. Five Playwright tests passed in 24.0 seconds against real preview data, including all sixteen workspaces, generated designer/source drill-down/PDF download, approved lease/ECL calculations and AI drafting/mobile capture. See playwright-results.json and screenshots/. These browser tests supplement five service scenarios: company reporting/reviews/exports, lease journal overlay, ECL journal overlay, two-entity translation/elimination/NCI, and sourced AI review. Consolidation and independent professional-review scenarios are primarily verified by the backend workflow suite, not five full browser journeys.

Ruff and mypy pass. Frontend ESLint and TypeScript pass. Production Next.js build passes. Alembic upgrade from an empty disposable database through 0005 succeeds; alembic check reports no drift. Runtime tests use a NOSUPERUSER/NOBYPASSRLS role with forced RLS.

Security checks include preparer self-approval rejection, separate Manager/Partner stages, role restrictions, cross-tenant empty calculation reads, immutable calculation UPDATE rejection, stale assumptions, unauthorized exports and IFRS source-access enforcement through audit AI/source routes. The broader existing Phase4 security suite remains included.

Local CPU benchmarks: 20,000 ECL exposures/two scenarios in 0.2647s, 10,000 assets in 0.1160s, and 10,000 mapping validations in 0.0394s. Each numerical benchmark checks independent expected totals. These exclude database/network/concurrent export load and are not production capacity guarantees. See benchmarks.json.

Exports: real authenticated PDF/XLSX/DOCX/JSON endpoints are exercised with file signatures. PDF pages are rendered and inspected. Excel cells/ZIP structure and exact strings are verified; formulas cannot be injected through narratives. DOCX ZIP/XML and table/page-field construction are checked, but visual rendering is blocked by missing LibreOffice. No production server smoke test or semantic external-provider assessment is claimed.

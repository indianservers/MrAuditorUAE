# Verification — 24 October 2026

Implemented and exercised locally against the existing synthetic QA dataset and a separate disposable regression database. No production certification is asserted.

- Full backend suite: **489 passed, 2 skipped** in 525 seconds. See `backend-tests.txt`.
- Final focused country/dependency and audit lifecycle suite after the last guard changes: **21 passed**, including all three new global-platform integration tests. See `focused-tests-final.txt`.
- Frontend unit suite: **25 passed**. See `frontend-tests.txt`.
- Browser integration: **1 passed**, covering persisted Settings selection, saved dependency edges, source edits causing stale consumers and navigation to the saved working paper. See `browser-tests-final.txt` and `working-paper-graph.png`.
- Production Next build, TypeScript check, ESLint, Ruff and mypy passed; mypy checked 189 source files. Build and tool receipts are included in this directory.
- Alembic `0014` applied successfully to the disposable test database and the existing synthetic QA database. `alembic check` reported no new upgrade operations. Live backend `/health/ready` returned `ready`.
- Before/after migration full-row digests matched for 440 audit records, 1,350 immutable audit revisions, 901 review decisions, 14 IFRS calculation runs, 46 legal entities and 119 engagements. The comparison was taken immediately around migration, before subsequent browser fixtures were added.

The new integration tests verify an approved working paper's full history remains identical after switching the user's working country; user preference isolation; optimistic conflicts and invalid countries; immutable engagement package bindings; transitive source staleness and rejected approval; and India core audit with UAE tax/e-invoicing preparation blocked.

The full suite ran before the final additional India test and final permission/cache refinements; the final focused run covered these changes. Two conditionally skipped backend tests were not executed. Wider specialist browser coverage and prior production release gates remain outstanding as documented in the previous QA campaigns.

Commands used: the existing `scripts/qa_crud_run.py test` wrapper with pytest, Alembic and mypy/Ruff in the backend; `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` with a separate Next output directory; and `npx playwright test --config playwright.global.config.ts`. Private runtime credentials and the pre-migration database backup remain ignored under `.local-runtime`.

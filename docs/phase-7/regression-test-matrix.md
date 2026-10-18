# Regression Test Matrix

Backend: 294 passed, 0 failed, 2 skipped; measured statement coverage 88.74%. Frontend:22 passed,0 failed. Playwright:5 passed,0 failed,0 skipped.

- ai: 13 passed, 0 failed, 0 skipped.
- integration: 11 passed, 0 failed, 0 skipped.
- phase2: 116 passed, 0 failed, 2 skipped.
- phase3: 4 passed, 0 failed, 0 skipped.
- phase4: 46 passed, 0 failed, 0 skipped.
- phase5: 20 passed, 0 failed, 0 skipped.
- phase6: 33 passed, 0 failed, 0 skipped.
- phase7: 23 passed, 0 failed, 0 skipped.
- security: 20 passed, 0 failed, 0 skipped.
- unit: 8 passed, 0 failed, 0 skipped.

Backend command from backend: `.venv/Scripts/python.exe -m pytest --cov=app --cov-report=term-missing --cov-report=json:../docs/phase-7/coverage.json --junitxml=../docs/phase-7/regression-results.xml`. Set explicit disposable DATABASE_URL, INTEGRATION_TESTS=1, development/test mode, JWT_SECRET and Redis URL. Full run268.61 seconds; source evidence regression-results.xml/regression-log.txt. Final targeted Phase7 rerun:23 passed in24.31 seconds after final applicability/parser changes; vat-results.xml/vat-test-log.txt. Baseline271 passed,2 skipped. Counts are test cases, not assertions, task variants or demo records.

Frontend: `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`. Playwright: `npm run test:e2e:phase7` against production3001 and actual demo API58003. Five tests cover14 VAT routes, calculation/export, mobile read-only controls,16 IFRS routes,20 CT routes,16 audit routes and12 core/admin routes. They check rendering and selected actions; they are not exhaustive click coverage. Browser initial run had1 test-selector failure (Export JSON vs actual Export VAT JSON), corrected and rerun. Latest5 passed in30.3 seconds. Screenshots in screenshots/. No mocked browser financial responses.

`scripts/phase7.ps1 -Task` exposes backend/frontend/e2e/security/financial/ai/regression/benchmark/seed-demo/enrich-demo/demo-tax-cases/verify-demo/archive-demo. It propagates native failures. Seed commands require all demo guards and password; never point tests at the delivered demo. CI uses a non-superuser role, dedicated *_test database, migrations/drift, Ruff/mypy, coverage80% and core90%, plus frontend tests/lint/types/build.


## Ten persistent demonstration scenarios

1. Firm Admin: actual API-created10 clients/entities and30 engagements, CA memberships assigned through team API; seed-log.txt and manifest source IDs.
2. Internal Accountant: actual four-line upload/validate/commit and independent TB signed-balance assertion, isolated FY2027; accountant-demo-log.txt and manifest accountant_scenario. Distinct from restricted Client Accountant.
3. Auditor: actual analytics run, finding retrieval and original journal lineage investigation; audit-demo-log.txt and manifest audit_scenarios.
4. CA: actual working-paper preparation/submission and independent final review of a different preparer's paper after Audit Manager review; audit_scenarios stores both IDs. Own paper remains pending a different final partner.
5. Financial Reporting Manager: actual IFRS generation; independent PBT and ready checks; role-calculations-log.txt and manifest role_calculations.
6. Tax Manager: actual CT preparation from approved IFRS source; independent expected current tax; same evidence.
7. Tax Consultant with explicit Senior Tax Consultant role:10 reviewed QFZP alternative cases, actual calculation API and independent expected status/tax; qfzp-demo-log.txt and per-engagement manifest IDs.
8. VAT Analyst: actual approved-source reconciliation/net assertion and stored draft return; portal-invoice-scenarios.json vat_analyst.
9. Invoice Validator: actual deliberately defective invoice validation; structured exceptions in portal-invoice-scenarios.json. Draft is excluded from approved returns.
10. Client Document Contributor: real PDF upload to requested evidence; Auditor reviewed metadata and attempted submission;409 quarantine block observed. Final clean approval remains BLOCKED until an antivirus service scans it. No false CLEAN status was injected into the demo.

Unified financial runner itself executed80 numerical tests successfully (unified-financial-log.txt). This repeats a subset of the full suite and is not added to its294-case pass total. Latest targeted VAT case includes an actual32,768-UUID PostgreSQL array query to guard against asyncpg scalar bind limits, and confirms the synthetic status banner cannot disclose the demo manifest.

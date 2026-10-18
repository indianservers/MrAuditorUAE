# Phase 6 financial accuracy and verification

Expected values are independent fixed assertions, not snapshots produced from the implementation under test. The original238-test baseline passed before Phase 6 (two opt-in connector skips). All 33 Phase 6 tests pass using the actual import/IFRS/review stack and a disposable PostgreSQL database running as a non-superuser with forced RLS. Final regression counts are recorded in phase-6-report.md and regression-results.xml.

- Standard tax: negative/zero income,374,999/375,000/375,001 boundary and1M income →0/0/0.09/56,250 respectively.
- Mainland: PBT1.2M +400k approved partial deduction; tax110,250. An extra unapproved adjustment is ignored. Separate manager/partner reviews are exercised; stale-source export becomes draft.
- SBR: current/prior revenue ceiling, election, QFZP/MNE/separation exclusions and2029 amendment. A legal-as-of date before the new source knowledge fails rather than borrowing a future rule.
- QFZP: exact5% boundary, excess, missing facts, special denominator exclusions and profit reconciliation. The approved service fixture gives zero only after its profit segments match the financial bridge.
- Interest:20M net interest and50M statutory EBITDA →15M ceiling/5M disallowed; six-month 6M threshold, capitalization on amortization, FIFO and ten-period expiry. Loan workflow uses approved accounts/evidence and reconciled pre-GIDLR income.
- Losses:2M prior loss/1.6M income →1.2M use,400k taxable,2,250 tax. Three approved versions leave800k available. Transfer500k posts once and donor supersession leaves300k available; recipient use is separately capped.
- Group: two actual financial packages, PBT2.4M +800k adjustments →3.2M taxable and254,250 tax using one threshold.94.99% voting rights fail.
- Foreign credit: foreign tax12k/UAE attributed9k →9k credit, current tax101,250; an exemption on the same source line is rejected. Separate approved dividend schedule500k against1.2M PBT →700k taxable and29,250 tax.
- Relief/transitional/foundation: in-window clawback, explicit negative50k manual transitional result and application-pending foundation; none silently changes corporate tax.
- Returns: current release and complete evidenced checklist required; external filing without proof rejected.
- AI/security: all 24 tasks remain suggestions, preparers cannot accept their own output, accepted AI never posts a tax adjustment; invented articles/source IDs/periods fail. Unassigned/unprivileged sources and exports are denied; cross-tenant run access is empty and immutable SQL updates fail.

Six Playwright tests execute all 20 routes and the five requested scenarios (mainland, QFZP, interest loan, group and AI), PDF download and a390px mobile viewport. Evidence: playwright-results.json and screenshots/. Screenshot review led to clearer group approved-amount labels and an expanded structured AI presentation. Supporting schedules still use validated JSON editors for complex arrays; a bespoke spreadsheet editor for every legal fact is not claimed.

PDF/XLSX/JSON service export tests verify signatures and current/draft status. Bundled Python independently parses PDF pages, checks workbook structure/literal cells/no external links, parses JSON and renders all PDF pages for visual inspection. export-verification.json holds actual results. No verified DOCX visual result or live-provider semantic accuracy claim is made. benchmarks.json is local arithmetic, not production load evidence.

Reproduce from backend with INTEGRATION_TESTS=1 and disposable DATABASE_URL/REDIS_URL/JWT_SECRET/BOOTSTRAP_SECRET: `.venv/Scripts/python.exe -m pytest -q`. Never run integration fixtures against a production or preview database: they truncate tenant data. Frontend: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test:e2e:phase6` against seeded preview API58002/frontend3000. Preview scripts require DEMO_SEED=1 and do not reset existing data.

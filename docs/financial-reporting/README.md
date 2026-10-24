# Financial data and reporting workflow

Implemented on 24 October 2026 using the existing import, accounting, IFRS, approval, lineage and export services. Existing working-tree changes were preserved. No deployment, commit or push was performed.

## Available in the app

- Financial Data → Trial Balance: explicitly select an earlier committed period, see prior closing balances, amount movements and percentage movements, retain prior-only accounts, filter unmapped accounts, inspect monthly ledger movements and review independent source control status. The summary distinguishes current-source account counts from the comparison population. Monthly movement schedules exclude opening entries; TB-only imports do not claim monthly data.
- IFRS Reporting → Financial Statement Designer: preview and exports share precision, credit-section signs and zero suppression. Current profit and OCI appear within presented equity. Rounded section totals, readable cash-flow/equity schedules, note presentation signs and readable validation results are included in exports. Original amounts and source accounts remain available for traceability. New statement calculations identify methodology `auditos-ifrs/1.1`.
- Financial Statement Review: check statement totals, current/comparative equations, duplicate references, missing notes, note-to-statement links and amounts, rounding differences, existing financial validations and source freshness. Compare an earlier version within the same engagement/entity/currency/period to inspect line, note, total, cash-flow and presentation changes. Issues have stable identifiers, carry-forward status and resolved identifiers.
- New generated review errors feed the existing release gate. Submission/approval/locking and reviewed exports also recheck structured financials, including historical runs, without rewriting historical records. Downloaded files preserve the backend's draft/reviewed filename.

## Verification

- Combined accounting and reporting regression: **145 passed, 3 skipped**; see `backend-results.txt` and `backend-results.xml`. Live connector tests remain credential-gated. The Zoho fixture was updated to select an authorized organization after connection creation and use the account-transaction feed; it verifies manual detail evidence is not double-counted.
- Reporting regression after presentation/release refinements: **29 passed**; see `reporting-results.txt` and `reporting-results.xml`. Covers actual imported sources, financial generation, independent approval, JSON/PDF/XLSX/DOCX exports, stale input blocking, comparison-only accounts, zero prior balances, monthly opening exclusion, source controls and duplicate-note release blocking.
- Frontend unit tests: **29 passed**. Frontend type check, lint and production build passed during implementation. The final source-specific backend type check covers eleven files; full-project type checking is affected by concurrently added country-workflow modules outside this change.
- Browser: **1 end-to-end scenario passed** against real APIs and a dedicated disposable database, covering comparisons, monthly schedules, generated reviews, earlier draft comparison, distinct equity rows and draft PDF download. See `browser-results.json` and `screenshots/`.
- Application PDF output was rendered and visually inspected. The packaged DOCX renderer could not run because LibreOffice is absent; DOCX generation and ZIP structure are tested, but Word layout remains unverified.

## Reproduce locally

Use the existing backend virtual environment and initialized local QA configuration. `scripts/financial_reporting_run.py` always selects `auditos_financial_workflow_test`, Redis database 7 and a separate private object directory. It does not target the demo or live database. Create that disposable PostgreSQL database with the existing application role as owner, then run:

```powershell
backend/.venv/Scripts/python.exe scripts/financial_reporting_run.py .venv/Scripts/python.exe -m alembic upgrade head
backend/.venv/Scripts/python.exe scripts/financial_reporting_run.py .venv/Scripts/python.exe -m pytest tests/phase2 tests/phase5 tests/unit/test_financial_review.py -q
backend/.venv/Scripts/python.exe scripts/financial_reporting_run.py .venv/Scripts/python.exe ../scripts/financial_reporting_preview.py
backend/.venv/Scripts/python.exe scripts/financial_reporting_run.py .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 58011 --no-access-log
```

The preview script explicitly resets only this disposable test database. Run it after integration tests, which also reset synthetic fixtures. The private browser fixture contains IDs; no credentials or tokens are saved in documentation. In another terminal, start the frontend with `AUDITOS_API_ORIGIN=http://127.0.0.1:58011`, `AUDITOS_WEB_ORIGIN=http://127.0.0.1:3008`, `AUDITOS_NEXT_DIST_DIR=.next-financial`, then `npm run dev -- --port 3008`. Run `npx playwright test --config playwright.financial.config.ts` from `frontend`.

## Scope and remaining limits

These additions complete the bounded internal workflow, not comprehensive IFRS/AS/Ind AS compliance or Caseware product parity. Existing India statutory/report-builder work remains separate; this change does not claim it is fully qualified. Disclosure categories still require professional assessment and do not replace a licensed complete checklist. Presentation materiality is not automatic aggregation. Consolidation remains draft-only under the existing documented limits.

Review checks inspect structured application statements, not arbitrary imported PDF/Word financials, scanned text or narrative semantic accuracy. Rounding differences are visible warnings and do not silently change approved balances. Source control reconciliation does not independently prove completeness of the originating books. Comparisons require the same client/entity and a preceding period; the selector lists the latest 100 eligible snapshots. Current and historical source states are labeled explicitly. Global production release gates remain in force.

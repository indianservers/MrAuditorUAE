# Phase 2 QA results

Status: **PARTIAL — not a statutory production release.** Existing history is preserved; the new functional foundation is implemented, but the entire master-prompt scope is not yet qualified. No commit, push or deployment was performed.

Verified locally:

- Migration 0016 applied to disposable test and synthetic demonstration databases. Alembic schema check reported no drift. Before/after demonstration history digests are identical (`evidence/before-0016.json`, `after-0016.json`).
- Deterministic tests cover Decimal matching/tolerance, ambiguous candidates, counterparty/currency separation, bounded groups, real open-item ageing/fallback, extraction conflicts and strict typed jobs.
- Genuine PDFium text extraction and RapidOCR image extraction pass on generated local fixtures; original hashes/model hashes/boxes and separate ZIP-member fields are checked. This is not a statistical OCR quality benchmark.
- Database/API tests cover append-only event enforcement, correction history, independent approval, stale prior versions, actual ledger-derived lead/mapping/flow jobs, actor-scoped idempotency/conflict and cancellation without publication.
- A real browser run passes queued lead generation through Celery/Redis, retained result display, self-approval denial and truthful provider catalogue UI (`evidence/browser-results.json`, `lead-workbench.png`). Browser testing found and fixed the account-picker page-limit error and TB-source account lookup.
- Frontend unit suite: 25 passed. TypeScript, ESLint and backend mypy checks passed during implementation; final checks and full backend results are recorded below when complete.

Final verification receipts: full backend suite **511 passed, 2 skipped** in 582.56s (`evidence/backend-tests.txt`); latest focused extraction/matching/API/mapping revision checks **9 passed** (`evidence/focused-tests.txt`, overlapping the full suite); frontend production build passed (`evidence/frontend-build.txt`); browser **1 passed** with actual table visibility and HTTP 403 self-approval response verified. Final mypy checks covered 203 application files. The final focused run adds reviewed mapping publication and preserved proposal hash/staleness checks. Browser layout review also found and fixed flex shrinking that hid financial table content.

After the final source-graph, reconciliation-decision and export checks, the focused regression set passed **23 tests** in 61.60s (`evidence/final-focused-tests.txt`). This overlaps earlier tests; it is not added to the full-suite count. It includes actual original-source graph nodes/mapping receipts, explicit auditor match acceptance, unmatched-ledger findings and denial of approval while a supporting table is unreviewed.

Access note: existing accounting permissions are preserved. An independent reviewer of financial intelligence needs both engagement assignment/review permission and `accounting.read`; the default Audit Manager role does not automatically receive every accounting permission. The mapping test uses a distinct Firm Administrator as reviewer. Administrators can configure existing tenant role policies; this phase does not silently widen them.

Implementation inventory:

- Database: `backend/alembic/versions/0016_accounting_intelligence.py`; two RLS tables for jobs and immutable result events. Existing 0014/0015 Phase 1 foundation remains in the uncommitted workspace.
- Backend: `backend/app/modules/intelligence/` contains strict operation inputs, source/version checks, local OCR, deterministic matching/ageing, export and graph projection services. `backend/app/api/v1/intelligence.py` exposes bounded source choices, jobs, result histories, corrections, review decisions, reviewed mapping publication, working-paper generation, tick marks, raster preview and result export. `backend/app/workers/intelligence.py` executes/recover jobs on the intelligence queue.
- Existing integration center: `backend/app/modules/connectors/catalogue.py` and `/connectors/catalogue` explicitly distinguish all eleven provider families. Existing imports, financial ledger, analytics, sampling, evidence, AI and audit record services are reused.
- Browser: `/intelligence`, `/intelligence/{engagement}/{ocr|source-table|mapping|lead|ageing|reconciliation|vouching|flow}` in `frontend/src/features/accounting-intelligence.tsx`; same authenticated BFF and tenant scope, plus integration catalogue and navigation changes. Existing `/integrations`, `/audit/sampling`, working papers and lifecycle remain the connected entry points.
- Dependencies: locked RapidOCR, ONNX Runtime, PDFium and Pillow for local extraction; no external document transfer by this OCR provider. Existing TF.js infrastructure remains.
- Screenshots and measured receipts are under `docs/phase2/evidence/`. Workspace file inventory includes Phase 1 and Phase 2 changes; no files are committed by this campaign.

Measured local synthetic performance (`evidence/performance.json`): SQL ledger aggregates over 10k/100k/1m actual rows took 0.135/0.838/1.195 seconds. Unique exact transaction matching of 10k/20k per side took 0.186/0.401 seconds. SQL client RSS excludes PostgreSQL memory. These numbers do not measure end-to-end import, every scrutiny rule, worst-case ambiguous matching, all-document OCR throughput or production load.

Limits and remaining work: eight live ERP adapters are unimplemented; Zoho/Tally authenticated qualification pending; real malware-scanner environment unqualified and fail-closed; specialized India statutory reconciliation unavailable; 2,000-line vouching needs deliberate partitioning; OCR max 20 pages/25 MiB, matcher max 20k/side, exports PDF/DOCX first 500 rows. Several specialist UI controls and the full new-role/action/load matrix remain outstanding. Prior production blockers remain in effect.

# Test results

Verified on 18 October 2026 with Python 3.12, PostgreSQL and Redis, plus the installed Next.js/React toolchain. Databases and identities were explicitly synthetic/disposable.

- Backend: **218 passed, 2 skipped, 0 failures**. The two skips are opt-in live Zoho/Tally connector tests.
- Phase 4 contributes 46 additional tests: 28 unit/contract cases and 18 database-backed workflow/security cases (including both parameterized quality-review lifecycle cases).
- Frontend: **22 passed**, zero failures.
- Playwright: **3 passed**, zero unexpected failures. Screen coverage includes all new routes, invitation activation, responsive layout, real working-paper preparation/review and restricted client collaboration.
- Actual browser screenshots: **27**; every image is mapped in screenshot-inventory.json.
- Overall backend statement coverage: **90.03%**. Preserved Phase 2 calculation/validation core: **90.35%**, exceeding the existing 85% core gate.
- Ruff check and formatting: pass for 113 backend files. Mypy: pass for 90 application source files. Frontend TypeScript and ESLint: pass.
- Alembic: fresh upgrade to 0004 and no schema drift. Runtime PostgreSQL role has no superuser/RLS bypass.
- Production Next.js build: pass. Additional production-browser execution was not run because automatic review blocked starting that optional preview with `npm start`; the supplied reason was only “blocked by policy”.

The initial no-integration baseline had 138 backend passes/36 skips and 18 frontend passes. Early database runs exposed intentional client-permission and lifecycle behavior changes plus the unsafe migration-role readiness denial. baseline-integration.xml and regression.xml retain those intermediate failures; backend-tests.xml and playwright-results.json are the authoritative final successful results.

The full audit scenario runs acceptance through archive with separate human test identities, sampled item results, reviewed source evidence, returned/revised papers, cleared notes and completion, with and without independent quality review. A declared clean-scanner test double is used only for the clean evidence path. The real default upload path remains quarantined without configured ClamAV. Separate tests cover hallucinated citations, human AI-procedure acceptance, findings responses/closure, tenant isolation, role differences/expiry/revocation, disabled users and concurrent edits.

Live AI, ClamAV and production S3/KMS were not verified. The methodology starter still requires independent professional validation. These tests do not certify audit quality, universal accessibility, large-portfolio scalability or commercial production readiness.

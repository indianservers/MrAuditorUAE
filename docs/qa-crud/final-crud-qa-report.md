# Final CRUD QA report

**Campaign status: PARTIAL. Readiness: NO-GO.**

Backend evidence: 487 unique current-source test cases passed; 2 skipped; 0 failed. Full run and focused reruns are combined by test identity; the superseded unparameterized test name is excluded. Focused new cases: 14. Frontend unit tests: 25 passed; browser results: {'startTime': '2026-10-18T08:20:13.174Z', 'duration': 77678.48, 'expected': 4, 'skipped': 0, 'unexpected': 0, 'flaky': 0}. Role login/API probe sets: 13. Discovery covers all 38 requested families, with 109 typed audit kinds, mapped tables and exact OpenAPI routes in the inventory.

Verified fixes address source staleness, ML double counting, guarded lifecycle/history, scoped record detail, search and multi-tab refresh. The actual source-change test includes AED 1m → 1.1m revenue and AED 100k profit movement. No approved historical result is silently rewritten.

Per-family coverage and policies:

- **Clients — PARTIAL**. Reasoned archive/restore with version conflict protection. Related passing tests: 14; full per-role browser CRUD: two representative workflows only.
- **Legal entities — PARTIAL**. Archive/restore after dependent engagement closure; active parent required. Related passing tests: 116; full per-role browser CRUD: not completed.
- **Ownership relationships — PARTIAL**. Effective-period reviewed relationship versions; do not hard-delete history. Related passing tests: 2; full per-role browser CRUD: not completed.
- **Financial periods — PARTIAL**. Scoped create/read; immutable source period linkage. Related passing tests: 116; full per-role browser CRUD: not completed.
- **Accounting connections — PARTIAL**. Guarded synchronization; no blanket delete. Related passing tests: 15; full per-role browser CRUD: not completed.
- **Imports — PARTIAL**. Validate/commit/supersede; immutable source receipts. Related passing tests: 19; full per-role browser CRUD: not completed.
- **Journal records — PARTIAL**. Immutable imported lines; replace source batch. Related passing tests: 19; full per-role browser CRUD: not completed.
- **Account mappings — PARTIAL**. Append mapping versions; existing feature receipts become stale. Related passing tests: 5; full per-role browser CRUD: not completed.
- **Trial balances — PARTIAL**. Regenerate from explicit snapshot; preserve prior results. Related passing tests: 116; full per-role browser CRUD: not completed.
- **Reconciliations — PARTIAL**. Immutable runs and exceptions; controlled regeneration. Related passing tests: 116; full per-role browser CRUD: not completed.
- **Audit engagements — PARTIAL**. Controlled transitions; direct status PATCH rejected. Related passing tests: 46; full per-role browser CRUD: not completed.
- **Materiality — PARTIAL**. Versioned draft, independent review, reopen/lock. Related passing tests: 46; full per-role browser CRUD: not completed.
- **Risk assessments — PARTIAL**. Versioned review; unused draft archive/restore. Related passing tests: 46; full per-role browser CRUD: not completed.
- **Audit programs — PARTIAL**. Versioned program/procedure review; unused draft archive/restore. Related passing tests: 46; full per-role browser CRUD: not completed.
- **Working papers — PARTIAL**. Unused draft archive/restore; approved history protected. Related passing tests: 9; full per-role browser CRUD: two representative workflows only.
- **Evidence — PARTIAL**. Immutable object versions, hashes, retention; no hard delete. Related passing tests: 46; full per-role browser CRUD: not completed.
- **Review notes — PARTIAL**. Resolve/clear through review workflow. Related passing tests: 46; full per-role browser CRUD: not completed.
- **IFRS adjustments — PARTIAL**. Draft/review/reopen; approved adjustment supersession changes dependencies. Related passing tests: 7; full per-role browser CRUD: not completed.
- **Lease schedules — PARTIAL**. Versioned assumptions and immutable calculations. Related passing tests: 20; full per-role browser CRUD: not completed.
- **ECL schedules — PARTIAL**. Versioned assumptions and immutable calculations. Related passing tests: 20; full per-role browser CRUD: not completed.
- **Financial statements — PARTIAL**. New approved source profile and mapping required after supersession. Related passing tests: 7; full per-role browser CRUD: not completed.
- **Consolidation — PARTIAL**. Controlled member/elimination runs, immutable prior outputs. Related passing tests: 7; full per-role browser CRUD: not completed.
- **Corporate Tax — PARTIAL**. Controlled regeneration/release; current financial source required. Related passing tests: 33; full per-role browser CRUD: not completed.
- **QFZP — PARTIAL**. Reviewed classification inputs and assessment; not automatic certification. Related passing tests: 33; full per-role browser CRUD: not completed.
- **VAT — PARTIAL**. Draft invoice archive/restore; reviewed return source dependency checks. Related passing tests: 23; full per-role browser CRUD: not completed.
- **Transfer Pricing — PARTIAL**. Reviewed source relationships and controlled immutable runs. Related passing tests: 44; full per-role browser CRUD: not completed.
- **Intercompany loans — PARTIAL**. Reviewed economic assumptions; rerun dependent calculations. Related passing tests: 44; full per-role browser CRUD: not completed.
- **Benchmarking — PARTIAL**. Versioned observations; manual assumptions remain disclosed. Related passing tests: 44; full per-role browser CRUD: not completed.
- **DMTT — PARTIAL**. Reviewed jurisdiction/financial sources and immutable calculation history. Related passing tests: 15; full per-role browser CRUD: not completed.
- **GRC risks — PARTIAL**. Specialist governed review; generic archive is blocked. Related passing tests: 12; full per-role browser CRUD: not completed.
- **Internal controls — PARTIAL**. Specialist governed review and source linkage. Related passing tests: 12; full per-role browser CRUD: not completed.
- **Monitoring alerts — PARTIAL**. Controlled alert disposition and retained evidence. Related passing tests: 12; full per-role browser CRUD: not completed.
- **Remediation actions — PARTIAL**. Owner-scoped controlled transitions. Related passing tests: 12; full per-role browser CRUD: not completed.
- **AI investigations — PARTIAL**. Grounded sources, proposal review, bounded execution. Related passing tests: 15; full per-role browser CRUD: not completed.
- **AI workflows — PARTIAL**. Cancel/review/execute with exact-payload and target-version checks. Related passing tests: 15; full per-role browser CRUD: not completed.
- **TensorFlow.js predictions — PARTIAL**. Append-only artifacts; stale lineage blocks further consequential use. Related passing tests: 15; full per-role browser CRUD: not completed.
- **Users and permissions — PARTIAL**. Versioned admission and access checks; no destructive user-history removal. Related passing tests: 93; full per-role browser CRUD: not completed.
- **Subscriptions and entitlements — PARTIAL**. Separately authorized platform changes; isolated from client-data permissions. Related passing tests: 93; full per-role browser CRUD: not completed.

Actual test identities and receipts are in campaign-results.json. Test categories overlap; test-counts.json avoids false sums. Independent database receipts and browser screenshots are retained. Complete specialist browser CRUD across every role remains open; see remaining-blockers.md. No git commit or push was performed for this campaign.

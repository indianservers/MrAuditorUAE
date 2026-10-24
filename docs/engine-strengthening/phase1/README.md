# Engine strengthening — Phase 1 delivery

Scope: E01, E02, E03 and E20. This is a verified foundation path with remaining programme requirements recorded explicitly in `gap-matrix.json`. It is not an assertion that all requested controls or production prerequisites are complete. Existing uncommitted connector, country-workflow, reporting, UI and ML work was retained. No Phase 2–5 tax/reporting/audit engines were implemented by this change.

## Implemented path

The existing accounting-intelligence workspace now offers **Foundation validation** at `/intelligence/{engagement_id}/foundation-validation`. It uses the existing FastAPI service, tenant RLS, immutable intelligence ledger, Celery job outbox and backend review permissions. It does not introduce a parallel engine or require external AI credentials. TensorFlow.js and the OpenAI-compatible gateway remain separate and unchanged in architecture.

Select an active journal snapshot, reviewed document extractions and rule assessments. Link selected extraction fields to actual journal lines. The result retains extraction hashes, source record IDs, import snapshot hashes, mapping receipts, reporting context and rule assessment dependencies. These are explicit supporting relationships selected by the preparer; they do **not** assert automatic invoice-to-journal amount reconciliation or proof of an accounting conclusion.

The validation requires source completeness, independently supplied import counts/debit/credit totals, journal balance, mapped journal accounts, reviewed reporting context, reviewed extractions and resolved reviewed rule applicability. “Complete” means complete **for these selected technical foundation controls**, not complete evidence coverage for the engagement or every ledger line. Missing essential evidence/rules produces a successfully executed result with partial completeness and blocking issues. A preparer can submit it, but the backend refuses approval until regenerated without blockers. Independent review and current versions are checked again at action execution.

After approval, existing working-paper generation creates a draft in the normal audit workflow. Human-authored procedures and conclusions remain the reviewer's responsibility. Changes to an extraction, source snapshot, mapping or applicable rule make dependent results stale at read/release time. Historical approvals and hashes remain unchanged. Regenerate, submit and independently approve a replacement; release of stale work is blocked.

## Per-engine status

### E01 — jurisdiction and rules

- Runtime: existing versioned regulatory registry and date resolver exercised against the disposable database.
- Data/control readiness: published selections now recheck source-validation blockers and explain the same-key highest-published-version amendment policy and date basis. Optional category/publication/topic/implementation metadata added; legacy absent metadata remains unknown.
- Rule verification: no substantive UAE legal parameters, rates or thresholds were introduced or changed. No real UAE legal source was newly certified by this delivery. Test source attestations and document hashes are explicitly synthetic. Existing published content remains dependent on actual primary-source retention and qualified independent review.
- Verification: rule arithmetic/date-boundary units and existing publication, independence, context binding and historical stale-propagation integration tests.
- Limitations: cross-key conflicts, factual elections and transitional-law semantics still require explicit professionally reviewed configuration. Domain allowlisting and source-hash attestation do not establish legal content correctness. Firm policy/reviewer judgments are distinguished in metadata but their full alternative activation policy is not implemented.

### E02 — documents

- Runtime: local digital-PDF extraction, storage, corrections and independent review exercised. Original evidence remains preserved. Repeated identical current uploads with unchanged scan state reuse the current version and record a duplicate event; reverting older content creates a new version.
- Data/control readiness: Arabic/English label patterns, Arabic/Persian numeral and separator normalization, original matched text, page/block/bounding-box information where available, method and explicit unavailable field confidence. Configurable bounded page/byte limits apply to extraction and preview.
- Rule verification: not applicable to text recognition; extracted tax identifiers are not registration attestations.
- Verification: real synthetic PDF through storage/extraction/jobs; labeled Arabic/English unit fixtures, ambiguity and malformed-value tests; correction/stale lineage and duplicate-upload integration checks.
- Limitations: no claim of evaluated scanned Arabic OCR, general invoice layout recognition, multipage table reconstruction, currency-symbol disambiguation or full document classification review. ClamAV integration exists but the workflow uses an explicit scanner test double. Real evidence remains quarantined until an operational scanner clears it. Hashes alone are not malware scanning.

### E03 — financial data

- Runtime: existing staged Decimal imports, normalization, control totals, idempotency, immutable activation and mappings exercised.
- Data/control readiness: partial-extract imbalance wording no longer implies a proven ledger error. Invalid supporting-table ISO codes are rejected. Period lock/version added; locked periods block new activation and entity-wide approved mapping changes. Authorized reopen requires current lock version and a recorded reason.
- Rule verification: no accounting or tax classification is inferred from account codes, account names or model predictions. Mapping suggestions retain their existing `rules_baseline` label.
- Verification: import regression suite, Decimal unit coverage, partial-extract control test, unauthorized/stale period actions, locked activation/mapping rejection, reopening and mapping invalidation.
- Limitations: the existing general mapping API allows an authorized mapping administrator to approve a profile; no new independent mapping approval or effective-dated taxonomy lifecycle is claimed. No complete posted-adjustment/reversal/restatement engine was added. Opening/closing and subledger controls still need independent reconciliation sources; foundation completeness is not a replacement for those controls.

### E20 — engagements, approvals and evidence

- Runtime: existing engagement roles, independent approvals, immutable revisions, lineage graph and job recovery reused; foundation submit and blocker guards added.
- Data/control readiness: foreign-tenant/engagement event dependencies and unknown dependency schemas fail freshness. Known cross-engagement working-paper record/intelligence references are rejected. Foundation results expose separate execution/completeness/severity/review dimensions. Period actions log entity, engagement, before/after state, version and reason using existing append-only audit storage.
- Rule verification: foundation review does not certify law or constitute an audit opinion.
- Verification: end-to-end synthetic workflow, two-stage audit working-paper approval, stale release prevention, replacement paper approval, self/unsubmitted/stale approval rejection, tenant/engagement boundaries, failed-job retry/idempotency and existing immutable-event checks.
- Limitations: invalidation is checked at read/action time; this delivery does not automatically create generic review tasks or recalculate every eligible draft. Existing engagement scope/team/policies remain in force, but no new universal entity-fact/approval-policy schema or historical lineage backfill is claimed. Legacy results must be reassessed rather than assigned invented provenance. Database mutation guards are not cryptographic immutability.

## Migration and compatibility

1. Back up and migrate the target deployment through Alembic revision `0020` before restarting updated API/workers. Only the dedicated disposable `auditos_foundations_test` database was migrated for verification; normal working databases were not migrated by this task.
2. Revision `0020` adds `financial_periods.lock_state` (`OPEN` by default) and `lock_version` (`1` by default), with allowed-value checks. Existing periods retain open behavior until explicitly locked. No historical accounting amounts or approvals are rewritten. RLS is inherited from the existing table. The migration refuses destructive downgrade; use a reviewed forward migration.
3. Rule metadata is optional and requires no database migration because existing rule bodies are versioned JSON. Missing legacy category/publication metadata is unknown. No new defaults are persisted into historical content hashes.
4. `foundation-validation` is additive to existing job operation schemas. Deploy API and workers together. Existing result kinds retain their current shapes; the shared `foundation/1` contract applies to the new foundation path, not a forced rewrite of every old engine.
5. Unknown dependency types now fail closed. An older worker/API encountering a future receipt schema must be upgraded; do not interpret it as fresh. Current existing receipts remain supported.
6. Current entity-wide account mappings cannot be changed while any entity period is locked. Effective-dated mappings are a remaining prerequisite for more granular behavior. Identical evidence reuploads may now return the current version with `duplicate_detected: true` instead of creating unnecessary revisions.
7. Mapping freshness receipts now include statement group, parent account and mapping-profile ID as well as version/classification. A different profile with the same local version number can therefore invalidate a result. Old persisted mapping receipts missing these fields fail comparison and require regeneration/review; their historical content is preserved.

Configuration examples are in `configuration.env.example`. `DOCUMENT_MAX_PAGES` defaults to 20 (allowed 1–100); `DOCUMENT_MAX_BYTES` defaults to 25 MiB (allowed 1 KiB–100 MiB). Separate existing evidence/archive/pixel/timeout bounds still apply and may impose stricter limits. The language-model API key is unnecessary for this path.

## Shared contracts and next-phase interfaces

`backend/app/core/engine_contracts.py` defines strict `EngineResult` and `EngineIssue` types. An execution has tenant/entity/engagement/period, jurisdiction/framework, execution ID, schema/calculation version, execution mode, execution status, completeness, professional review status, assumptions, unresolved questions, evidence/version receipts and structured issues. Finding severity, blocking behavior and disposition belong to issues and do not overwrite execution or review state.

Error categories are `invalid_input`, `missing_evidence`, `unverified_rule`, `permission_denied`, `unsupported_jurisdiction`, `stale_source_data`, `dependency_unavailable` and `incompatible_schema`. Existing endpoint HTTP errors are not globally rewritten by this delivery. Incompatible or unavailable dependencies must fail rather than produce an empty success. New downstream engines should consume immutable receipts and run currentness and authorization checks at approval/release, preserving prior approved versions.

## Reproduce verification

Use the dedicated test runner only after the existing local QA environment is provisioned. It reads private QA configuration without printing secrets and pins a new disposable `*_test` database and separate object directory. Its integration fixtures intentionally truncate that disposable database. Never redirect these fixtures to a working database.

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe scripts/foundations_run.py prepare
.\backend\.venv\Scripts\python.exe scripts/foundations_run.py .venv/Scripts/python.exe -m pytest tests/qa_crud/test_foundations.py tests/qa_crud/test_accounting_intelligence.py tests/qa_crud/test_regulatory_workflows.py tests/phase2/test_pipeline.py -q
```

From `backend`, run the unit suite with `.\.venv\Scripts\python.exe -m pytest tests/unit -q`. From `frontend`, run `npx vitest run tests/foundation-validation.test.tsx`, `npx tsc --noEmit` and targeted ESLint. Actual machine-readable results are retained in this directory, including `workflow-evidence.json` from the successful full workflow. Scanner/broker dispatch are explicit doubles; job processing, database, private object storage, PDF extraction and HTTP permission paths are real local implementations. No external communication or filing is performed.

The UI interaction test validates the actual job operation payload, status separation and warning navigation. TypeScript/ESLint check the changed UI. This delivery does not claim a new full-browser visual regression run or production deployment.

### Observed broader-suite blocker

The broad 27-test integration run produced **26 passed, 1 failed**: `test_zoho_native_journal_and_chart_staging` returned a sync result without `derived_import_batch_id`. The existing synthetic organization stub lacks the base-currency identity now required by the in-progress connector implementation. A diagnostic rerun with that fixture currency supplied stalled in the synchronous checkpoint/storage path and was interrupted; the diagnostic fixture edit was then reverted. Code inspection identifies a lock-order problem: request entitlement admission holds the tenant storage advisory lock (namespace 12), while `ConnectorRuntime.persist_object` opens a second transaction and `put_private` attempts that same lock. The original broad failure is retained in `integration-broad-results.xml`; the foundation/regulatory/import set excluding that named connector test is recorded separately. No connector-control bypass or production change was introduced to hide this failure. Resolve the connector transaction ownership before relying on synchronous Zoho source acquisition in Phase 2. File imports and the demonstrated foundation workflow do not need this live connector.

## Precise Phase 2 prerequisites

- Resolve the open/partial items in `gap-matrix.json` that affect the intended tax use case; this programme is not production-complete merely because the synthetic foundation path passes.
- Retain the actual applicable UAE primary legal documents and provisions, publication/effective periods, elections and factual conditions. Independently verify and approve each executable parameter. Resolve cross-key conflicts and transition questions before a final tax conclusion.
- Configure and verify operational malware scanning, storage access/retention and real queue delivery/recovery. Evaluate Arabic OCR on representative licensed/nonconfidential fixtures before depending on it.
- Require independent, source-reconciled opening/closing and subledger controls appropriate to the tax computation; do not treat selected foundation controls as population-wide audit assurance.
- Decide and implement independent mapping approval, effective-dated taxonomies and explicit legal classifications separate from financial presentation mappings. Implement the adjustment/reversal/restatement paths needed by the next tax workflow.
- Connect generic invalidation follow-up tasks and eligible draft recalculation to the existing outbox with idempotent deduplication. Preserve historical approved versions and block release until rereviewed.
- Migrate/deploy revision `0020`, establish role assignments and professional review policies, then rerun integration tests and a production-like browser workflow. No external filing or communication should occur as part of verification.

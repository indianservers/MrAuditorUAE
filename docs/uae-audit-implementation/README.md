# TheAuditor — use cases 01–50 implementation

Status: **partial implementation; not all 50 use cases or release gates are complete**.

This delivery extends the current modular application. Existing uncommitted work, original evidence, approved history and concurrent foundation/connector/reporting additions are preserved. No deployment or production model promotion was performed. The scope excludes use cases 51–100.

## Added procedures

Twenty-three bounded procedures are integrated with the existing intelligence job API and country-workflow UI:

- Shared audit: subledger-to-GL controls, subsequent receipts/payments, external confirmation evidence and expense cutoff/unrecorded liabilities.
- Accounting: source-controlled provision-matrix ECL through the existing IFRS engine, asset-register/depreciation/GL checks through the fixed-assets engine, inventory count-date movement bridges and cash forecast/funding-gap checks.
- Procurement/payroll: order/receipt/invoice/payment matching, vendor/employee shared bank hashes, expense policy/receipt reuse and benefit comparisons using supplied effective-dated regime rules.
- Sector/tax: customs documents/duty inputs, excise stock conservation/tax-return comparison, sourced trade-price/document checks, gold gross/fine weights, escrow authorisations/cumulative limits, hospitality/healthcare billing bridges and single-obligation construction revenue through IFRS 15.
- Diligence: KYC/EDD evidence readiness, economic ownership path calculations and an explicitly labelled uploaded-list sanctions-name baseline. These do not provide identity authentication, legal UBO determinations, sanctions clearance or regulatory filing.

Canonical source contracts, date windows, row/currency controls, missing evidence, ambiguous allocations and unsupported scenarios are validated. Calculation results default to `UNVERIFIED`, retain source receipts and require the existing independent review. Blocking control/evidence failures cannot be waived by acknowledging an exception. No journal, tax classification or filing is posted by these procedures.

The workflow UI is `/intelligence/<engagement-id>/country-workflow`; source preparation is `/intelligence/<engagement-id>/workflow-source`. CSV field contracts are available there. Period-end GL balance controls can be generated directly from an authorised committed account, with an explicit receivable/payable sign convention. Source populations remain bounded; an uploaded-file control does not prove completeness of the originating system.

Diligence source preparation and reads additionally require the existing `audit.evidence.review` professional permission. Ordinary accounting access does not expose those source bodies. This is a scoped evidence boundary; a dedicated restricted AML case-management subsystem remains unfinished.

## AI and ML separation

- Financial calculations, tax arithmetic, reconciliations and schedules remain deterministic.
- TensorFlow.js runs in Node on the supported portable CPU backend. Training remains in workers. Inference checks feature/preprocessing dimensions, metadata, artifact hashes and topology; model instances are cached with a two-model bound within a worker process. Separate server-created child processes remain isolated; this is not a cross-process model daemon.
- Child admission is bounded to two per Python process. Node inference serialises model use and bounds its queue. Models, optimizer state and temporary tensors are disposed; repeated inference, queue saturation, corrupt/missing artifacts and schema mismatch have executable checks.
- Explicit `rules_baseline`, `statistical_baseline` and `diagnostic_mock` requests are available at `POST /api/v1/ml/inference/baselines`. They do not require a deployment or language-model credentials. Diagnostics return no model score; no trained inference silently falls back to them.
- Trained inference still requires the existing approved deployment, compatible private artifacts and scoped dataset. Persisted results include mode, model/feature/preprocessing versions, entity/period, source receipts, score meaning, limitations and unreviewed dispositions. Feedback/approval and source staleness remain separate controls.
- The existing `journal-classifier` is a binary exception-review classifier, not a journal-type classifier. Account-name mapping proposals currently use a labelled rules baseline. Neither proposed mappings nor model scores determine VAT treatment, deductibility or audit conclusions.
- The OpenAI-compatible gateway is separate. Its API identifies `diagnostic_mock`, actual `language_model` execution, or `unavailable`. Missing credentials/configuration do not disable deterministic workflows/local ML. Optional language output explains retained engine evidence; it does not replace calculations, invent market benchmarks or approve legal positions.

`GET /api/v1/ml/engagements/<id>/capabilities` reports configuration separately from runtime verification. Installed code or a deployment record is not proof of operational inference. Synthetic tests demonstrate execution and controls, not real-client accuracy. The previously failed experimental classifier evaluation is not superseded by this pipeline test and remains unqualified for production.

The command centre's approved `audit.get_shared_workflows` tool reads current retained engine results and validates their receipts. It does not fabricate a calculation. ML tools omit stale results and preserve their actual execution mode. Uploaded text cannot change the authorised tool registry or approval gates.

## Verification

Actual receipts are in `evidence/`; `verification-summary.json` is generated from them. Counts from broad and focused runs overlap and must not be added. The latest frontend production build used a separate `.next-audit-gap-build` directory. No new browser end-to-end scenario is claimed; component/type/build checks and real backend HTTP/job/review/export/tool tests were executed.

Integration fixtures use a separately owned `auditos_audit_gap_test` database, separate Redis DB and object directory. They execute real database/HTTP/object/job processors. Scanner verdicts and broker dispatch are explicit test doubles; the actual processor functions are invoked. TensorFlow.js fitting/inference uses the real CPU runtime with language-model credentials absent.

Reproduce from the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/audit_gap_test_run.py prepare
backend/.venv/Scripts/python.exe scripts/audit_gap_test_run.py .venv/Scripts/python.exe -m pytest tests/qa_crud/test_shared_audit_workflows.py tests/qa_crud/test_ml_execution_modes.py tests/phase9/test_workflows.py -q
```

The wrapper deliberately targets only its named disposable test database. The integration fixtures reset that database, not the demo or a customer database. Existing local QA configuration is required and is never copied into documentation.

## Remaining work

`capability-manifest.json`, `capability-matrix.csv` and `capability-matrix.html` retain all 50 original use cases, deterministic engines, ML mode where relevant, language-model dependency, evidence/review status, verification scope and blockers. “Scoped core” describes a bounded implementation, not full compliance or production readiness.

Substantial engineering remains: final group reporting/intercompany workflows, complex contract/disclosure coverage, full payroll recomputation/alternative schemes, property VAT, tax-specific retention/holds, unified FTA request packaging, restricted AML cases and notification delivery. Live identity/screening/market/ERP/authority connections, professional rule adoption, real-client model labels/evaluation and production scanner/recovery/load acceptance are separate unfinished dependencies. Sector procedures require broader pilot and source-system qualification. These are not marked complete by the added calculators.

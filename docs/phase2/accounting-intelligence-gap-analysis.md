# Accounting intelligence gap analysis

Baseline: Phase 1 local foundation and migration 0015. Production remains PARTIAL / NO-GO; see `docs/qa/mr-auditor-phase1-report.md` and the original QA blockers. This phase retains one app/database/codebase.

| Feature | Baseline status | Reuse / gap |
|---|---|---|
| CSV/XLSX/Tally import | Working | Existing streaming parser, validation, commit, duplicate controls and immutable source receipts. |
| Zoho/Tally live connectivity | Blocked by credentials/environment | Real existing adapters; no live qualification claim. |
| Other requested ERP providers | Missing live qualification | Typed provider contracts and truthful upload paths required. |
| GL, journals, accounts, currencies | Working | Existing NUMERIC amounts, batch/source/snapshot linkage. |
| Trial balance | Working | Existing SQL balances and immutable runs. |
| Ledger mapping | Partially implemented | Versioned profiles exist; assisted proposals and reviewed multi-dimensional mappings need integration. |
| Population scrutiny | Working, qualification partial | Reuse 25 versioned DuckDB tests, applicability and source-linked findings. |
| Sampling | Working | Reuse documented random/MUS/systematic/risk/judgmental/full selection and selected line IDs. |
| Evidence storage/review | Working; scanner deployment unverified | Reuse private file versions, hashing and fail-closed quarantine. |
| Digital PDF extraction | Partially implemented | VAT text-layer parser only; no genuine image OCR. |
| Scanned PDF/image OCR | Missing | Add bounded local provider, original bytes retained, separate extraction versions. |
| Extraction correction/review | Missing shared workflow | Immutable corrections, source locations and independent review. |
| Vouching | Missing connected engine | Bind actual sampling items to extracted evidence and deterministic comparisons. |
| Reconciliation | Partially implemented | Reuse balance comparison; add bounded transaction/group matching and immutable decisions. |
| Lead schedules/ageing | Partially implemented/missing shared engine | Reuse balances; age real open items rather than assuming GL entries remain unpaid. |
| Working papers | Working review workflow | Reuse structured papers/history, add reproducible generation and exports. |
| Lineage/source impact | Working, bounded | Extend current source/context receipts; preserve approved results. |
| TensorFlow.js | Existing; production quality unverified | Preserve accounting ML. OCR is a separate local document provider. |
| External AI/OCR | Blocked if unconfigured | No unauthorized external transfer or invented output. |
| Production qualification | Unverified / NO-GO | Live providers/AV, full specialist browser matrix and ML calibration remain gates. |

These statuses describe inspected baseline capabilities. Implementation receipts and actual results will be recorded in `qa-results.md`; a generic upload is never presented as an authenticated ERP connection.

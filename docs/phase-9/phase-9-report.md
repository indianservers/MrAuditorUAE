# Phase 9 delivery report

Phase 9 adds genuine TensorFlow.js training/inference and a bounded UAE DMTT technical workbench. Previous modules and uncommitted work are preserved. No Phase 10 work, commit or push was performed.

## Actual ML results

TensorFlow.js 4.22.0 runs on the JavaScript CPU backend under Node 24.15.0 in a dedicated resource-bounded process behind Redis/Celery. Migration `0009_ml_dmtt.py` adds an immutable tenant-scoped registry ledger; private ObjectStore objects hold model JSON, binary weights and preprocessing/calibration metadata.

The dataset contains 250,024 original synthetic journal lines marked unknown and 13,200 separately controlled fixture lines: 263,224 total. Original unknown records are excluded from supervised fitting. Normal accounting facts are unchanged. Fixture journals/clients separate training, validation, test and OOD cohorts. These results demonstrate software feasibility, not real-client audit effectiveness.

All four primary runs completed 12 epochs. The autoencoder trained on 6,170 normal lines; held-out precision is 0.809412, recall 1.0, F1 0.894668 and false-positive rate 0.039397. The binary exception classifier and separately versioned risk-ranking model each trained on 7,200 labelled lines and achieved synthetic held-out precision/recall/F1 of 1.0. They currently share architecture/objective, so identical results do not establish a distinct ranking advantage. Account classification achieved 1.0 accuracy; deterministic keywords and train-only nearest centroids also achieved 1.0, so no superiority is claimed. Each run has 2,400 held-out and 1,200 OOD lines. See model-summary.json and training-results.json for exact architectures, losses, confusion matrices, threshold sweeps, review-budget metrics and OOD results.

The actual Phase 2 default rule engine was also evaluated on the same fixture test cohort: any-rule flagging produces F1 0.264819. This broad review-signal comparison against narrow synthetic labels does not establish that audit rules are defective or that ML improves real audit quality. Simpler rule/statistical baselines and expected random prevalence are recorded separately. All four fresh artifact loads reproduced predictions with observed maximum difference zero, within the 1e-6 tolerance.

Independent approval precedes experimental deployment. Per-family deployment history supports rollback. Four 1,000-record inference batches and drift outputs were verified. Evidence-backed feedback needs a separate authorized curator, preserves evaluation splits and never triggers automatic retraining. Predictions do not overwrite deterministic findings or approved account mappings. Generative commentary retains the validated prediction separately and needs professional semantic review.

## DMTT coverage

The active rule version is `UAE-CD142-MD96/v2`. Current-law research found that MD96/2026 repealed MD88/2025 and adopted the listed newer OECD material, with fiscal applicability from 1 January 2025. MD133/2026 is included for information-return obligations. Official source metadata and coverage limits are in regulatory-coverage.json.

Ordinary-case scope, approved IFRS-based income adjustments, reviewed covered/deferred tax schedules, jurisdictional ETR, period-aware SBIE, top-up and exact allocation use Decimal calculations. Statutory accounting basis/currency is explicit. Reviewed transitional CbCR/de minimis elections are supported. Loss/negative-tax, due recapture and unsupported special blending cases require technical schedules instead of an unsupported final tax. Eight synthetic groups cover threshold, foreign-parent, loss, transition, substance and safe-harbour cases. Independent fixtures verify 585,120 for the 2025 golden case and 70,548 for an actual IFRS-backed 2026 API case.

Fifteen DMTT AI tasks use approved providers, authorized source/reference allowlists and independent technical acceptance. They cannot calculate or change final tax. The minimized source context supports diagnostic assistance; substantive conclusions require additional authorized material and production evaluation.

## Validation and performance

Baseline: 338 backend passes, two configured skips and 22 frontend passes. Phase 9 targeted checks pass 15 tests, covering genuine training/reload/inference, RLS/immutability, review/curation, all 15 DMTT AI tasks, cancellation and numerical fixtures. A regression holds the engagement lock while confirming progress/cancellation still respond. Fresh migrations 0001-0009 and Alembic drift check pass. The final full suite passed 353 tests with two configured skips in 278.43 seconds. All four browser scenarios passed in 34.5 seconds; 22 frontend unit and three Node feature/metric tests passed. Browser results are in browser-log.txt. TypeScript, ESLint, Ruff, Mypy, Node tests, frontend unit tests and production build were executed.

Measured sequential local CPU performance for 250,000 rows: feature extraction 0.8671 seconds, preprocessing 0.0356 seconds, dense inference 0.5150 seconds, and model loading 0.00748 seconds. Whole-process RSS at that checkpoint was 652,738,560 bytes. Primary model fitting took approximately 1.5-2.1 seconds, excluding extraction/preprocessing/orchestration. Hardware and 10k/100k figures are in performance.json. Network, production concurrency, GPU and one-million-record throughput are not claimed.

## Remaining limits and Phase 10 readiness

All models remain experimental and synthetic-validated. Scores are not calibrated fraud/misstatement probabilities. Full longitudinal monitoring, SHAP/causal explanations, detailed recapture/transition/loss-DTA utilization, special group structures, automatic covered-tax reconciliation, foreign QDMTT effects and electronic filing remain partial or unimplemented. Complex schedules use shared structured forms. Three moderate npm transitive advisories remain documented; no vulnerable formatting CLI is exposed through application inputs. No production penetration test is claimed.

Phase 10 readiness is conditional on representative authorized audited datasets, production AI/economic evaluation, relevant tax coverage closure and operational security review. See coverage.json for explicit classifications.

## Delivery evidence index

1. Runtime: architecture.md and tensorflowjs-runtime.md.
2. Dataset counts/labels: demo-dataset.json and training-datasets.md.
3. Architecture, epochs/losses and held-out metrics: training-results.json and model-summary.json.
4. Baselines: existing-rule-comparison.json and per-model evaluation fields.
5. Private artifacts: immutable model event body.artifacts records ObjectStore key/version/SHA256; no public weight URL exists.
6. Inference/approval/rollback: inference-verification.json.
7. ML pages: `/ai-lab/{overview,datasets,features,architecture,training,evaluation,confusion,investigator,registry,deployment,drift,feedback}`.
8. DMTT pages: `/pillar-two/{overview,scope,entities,income,taxes,deferred,etr,sbie,topup,elections,reporting,ai}`.
9. Regulatory matrix: regulatory-coverage.json and dmtt-rule-registry.md.
10. Accuracy: accuracy-tests.md and dmtt-demo-results.json.
11. Security: ml-security.md and backend/tests/phase9.
12. Regression: targeted-tests.txt, full-regression.txt and browser-log.txt.
13. Defects: bugs-found-and-fixed.md.
14. Performance: performance.json; screenshots: screenshots/.
15. Limitations/readiness: coverage.json and the preceding section.

The additional DMTT arithmetic benchmark ran 100 calculations of 500 typed synthetic entities in 0.1783 seconds, excluding source validation/database overhead; allocations reconciled. See performance.json.

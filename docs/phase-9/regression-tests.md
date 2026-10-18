# Regression Tests

Baseline: 338 backend passes and two configured skips; frontend 22 passes. The targeted Phase 9 suite includes 15 tests with real TensorFlow training/reload/inference, all 15 DMTT AI tasks, independent approval/curation, tenant RLS, child cancellation and independent numerical fixtures. Final full-suite evidence: full-regression.txt. Browser evidence: browser-log.txt. Node feature/metric tests: npm test in ml-engine. Historical intermediate failures remain recorded rather than relabelled passes.

Final serial full suite on the freshly migrated Phase 9 database: 353 passed, two configured skips, 278.43 seconds. Original Phase 2 evidence files overwritten by legacy tests were restored byte-for-byte from HEAD afterward. No failing tests were disabled.

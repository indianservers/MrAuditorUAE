# Release test matrix

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Authoritative machine-readable files: [CSV](release-test-matrix.csv) and [JSON](release-test-matrix.json). Each row records requirement, test, type, expected/actual, status, severity, defect reference, evidence, reviewer and gate.

Backend totals: {'PASSED': 466, 'FAILED': 0, 'SKIPPED': 2}. Coverage is read from coverage-final.json when available; core-coverage-final.txt checks the existing 85% core gate. Eight independent arithmetic receipts are separate from backend test totals. Browser stats: {"startTime": "2026-10-18T04:58:41.571Z", "duration": 177110.082, "expected": 27, "skipped": 0, "unexpected": 0, "flaky": 0}. Three Node ML unit tests and 25 frontend component tests are recorded in their own logs, never merged into backend counts. Skips are not passes. Independent professional and security reviewer sign-off remains pending. The full coverage run passed 462 tests with two skips; four additional startup checks passed afterward and are included once in the deduplicated backend total. The isolated CI browser smoke passed separately.

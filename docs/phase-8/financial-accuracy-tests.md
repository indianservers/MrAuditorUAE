# Financial Accuracy Tests

The full backend regression completed with 338 passes and two configured skips, including Phase 8 numerical and PostgreSQL workflows. The frontend unit suite completed 22 passes. Fresh migrations 0001–0008 succeeded and Alembic detected no schema drift. Backend Ruff/Mypy and frontend typecheck/lint/build passed at the recorded checkpoints.

Phase 8 tests distinguish OP/OC from operating margin, test missing/zero denominators, inclusive/exclusive percentiles, negative values, weighted/unweighted pooling, FX, allocations, threshold boundaries, principal events, floating resets, compounding and period history. Real-API tests use actual accounting imports, approved IFRS source, multiple reviewers and immutable source runs. They exercise controlled sales, loans, services, compensation/CT bridge and Local File publication/client access.

Exact commands, counts and times are in full-regression-log.txt (final serial full run). XML and targeted logs are retained historical checkpoints, including the explicitly failed overlapping runs. Subsequent targeted checks are separate evidence, not silently added to the full-suite count. Two baseline failures from invocation at repository root were path-resolution issues; rerunning those tests from backend passed. No tests were deleted to obtain a pass.

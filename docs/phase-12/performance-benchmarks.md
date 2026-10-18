# Performance benchmarks

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Actual measurements in performance.json. Each API wave uses 10/50/100 **distinct** synthetic identities against the existing 250,024-row demo population; 320 total read requests. Signed development fixture sessions bypass login only in development, so this is not an authentication-load test. Load identities are disabled afterward.

- 10 distinct users, `/api/v1/clients?limit=25`: p50 0.091s, p95 0.099s, p99 0.099s, 48.33 requests/s, 0 errors.
- 10 distinct users, `/api/v1/accounting/ledger?limit=50`: p50 0.779s, p95 0.896s, p99 0.896s, 11.03 requests/s, 0 errors.
- 50 distinct users, `/api/v1/clients?limit=25`: p50 0.207s, p95 0.358s, p99 0.372s, 122.12 requests/s, 0 errors.
- 50 distinct users, `/api/v1/accounting/ledger?limit=50`: p50 2.199s, p95 3.316s, p99 3.327s, 14.67 requests/s, 0 errors.
- 100 distinct users, `/api/v1/clients?limit=25`: p50 0.462s, p95 0.805s, p99 0.874s, 110.26 requests/s, 0 errors.
- 100 distinct users, `/api/v1/accounting/ledger?limit=50`: p50 3.448s, p95 5.729s, p99 5.865s, 16.71 requests/s, 0 errors.

- 10,000 generated rows: TB 0.022s, analytics 0.289s; TB sum 0.00.
- 100,000 generated rows: TB 0.228s, analytics 1.864s; TB sum 0.00.
- 250,000 generated rows: TB 0.528s, analytics 4.265s; TB sum 0.00.
- 1,000,000 generated rows: TB 2.639s, analytics 23.180s; TB sum 0.00.

The million-row workload is generated in process and does not replace or expand the demo ledger. DuckDB stays bounded at 1 GiB/two threads with signature partitioning. Missing prerequisite rules return not-testable rather than invented results. Driver RSS is a point observation, not peak API/worker/DB memory. Production CPU, queue saturation, write mixes, all specialist/report/AI loads and cloud cost per file were not measured. The existing auth limiter allows 20 authentication POST requests per minute per backend-observed address; shared BFF addresses need explicit multi-user policy qualification. Forwarded headers are not implicitly trusted, and no sign-in capacity guarantee is made. Provisional target discussions must use this baseline; no production SLO or 100-user capacity guarantee is declared.

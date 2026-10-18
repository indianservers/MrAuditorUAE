# Measured performance

These are local synthetic measurements, not production SLAs. Five in-process ASGI samples were taken for each read endpoint; no network latency or peak RSS claim is made.

- dashboard: median 101.95 ms; max 646.57 ms.
- rcm_300: median 80.41 ms; max 99.33 ms.
- risk_100: median 19.98 ms; max 25.55 ms.
- controls_200_page: median 25.23 ms; max 88.24 ms.
- alert_page_50: median 22.02 ms; max 25.92 ms.
- board_package: median 11.26 ms; max 14.64 ms.

500 alerts were read in ten bounded pages in 0.248 seconds. The retained population benchmark covered 250,024 actual original synthetic lines: extraction 11.205 seconds, DuckDB load/signatures 4.56 seconds and 25 rules 1.0 seconds. The engine retained a 1 GB limit and two threads. Cross-period journal identifiers were qualified to prevent collisions; this benchmark is not an engagement conclusion.

Monitoring timings and explicit unavailable-source statuses are in performance.json. Actual model scoring is bounded to 10,000 rows per call; the demonstration uses 1,000-row and 100-row slices with frozen source snapshots. Production concurrency, long-running Beat uptime and peak process memory need separate operational qualification.

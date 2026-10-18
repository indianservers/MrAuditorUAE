# Measured performance

Progressive import/upload/validation/commit/TB timings are in dataset.json; checkpoint time on a resumed stage can reflect verification only, so use summed batch timings for generation performance.

load-results.json records 10/25/50/100 distinct-user bounded HTTP read loads when executed, response-shape checks, p 50/p 95, wall time and host CPU/memory deltas. Host metrics include other local campaign work. No production throughput capacity is inferred.

Three jobs traversed the actual HTTP API, Redis broker and separate Celery worker, then completed in PostgreSQL and were retrieved through HTTP. Measured elapsed time was 12.81 seconds (0.234 jobs/second) for this small solo-worker analytics sample; worker-results.json contains timestamps and outputs.

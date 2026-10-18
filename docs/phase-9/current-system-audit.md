# Current system audit

Inspected existing FastAPI/SQLAlchemy PostgreSQL modules, Next.js Precision workbench, financial analytics, approved IFRS source checks, TP model/workpaper patterns, AI gateway, permissions, private ObjectStore and Celery accounting jobs. Phase 8 remains uncommitted together with earlier phases; all existing changes are preserved. Baseline completed serially on the isolated Phase 8 test database: 338 passed, two configured skips in 263.79 seconds. Final regression uses a newly migrated Phase 9 test database; the demo database is separate. Frontend baseline has 22 passing tests.

Node 24.15.0 supports the verified TensorFlow.js 4.22.0 JavaScript CPU package. Native TensorFlow bindings are not assumed compatible with this Windows runtime. Training runs in a resource-bounded child Node process behind Redis orchestration. There is no existing trainable ML registry. Generative suggestions and deterministic audit rules remain separate signals.

The existing demo has 250,024 immutable journal lines and existing normalized financial sources. The Phase 9 builder will export authorized facts without modifying journals, use unknown labels for original records and separate reproducible controlled synthetic labels for training. No confidential cross-tenant pool is authorized.

DMTT must reuse approved IFRS sources and technical workpapers. Official CD142/2024, MD88/2025 and current MoF legislation links are being checked. Unsupported special tax cases must block final computations rather than silently blend into the ordinary UAE group.

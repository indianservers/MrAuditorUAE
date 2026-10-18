# Architecture

FastAPI authorizes tenant and engagement access. Redis/Celery dispatches a dedicated Node child with a 1,536 MiB V8 heap cap and 900 second wall timeout. PostgreSQL stores append-only model/dataset/review/deployment/prediction/feedback records in ml_registry_events; private versioned ObjectStore stores compressed datasets and genuine TensorFlow.js weights. This deliberately reuses the existing job, audit review and storage infrastructure. DMTT source workpapers reuse AuditRecord; calculation snapshots share the append-only ledger but are excluded from ML APIs.

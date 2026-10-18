# Evaluation methodology

The built-in reproducible evaluator uses six independently authored explicit-label text fixtures: invoice, loan, lease, bank statement, financial statement and contract. It measures exact field precision/recall, invented fields and page references. It also checks unsupported intent rejection and deterministic amount/currency mismatch. Expected values are authored independently of extractor output; no model grades its own work.

The synthetic document oracle independently specifies amount and page for fifty generated evidence records: {'correct': 50, 'total': 50}. The fixture evaluator results are in demo-verification.json under evaluation. Strong results here apply only to these simple labeled layouts. PDF visual layout/OCR/table semantic accuracy, real model hallucination and subjective synthesis quality are NOT_EVALUATED. The external provider was not used.

Approval, authorization, source freshness, immutable history, exact payload, retry, cancellation and graph controls are tested with actual PostgreSQL/FastAPI services. Browser results measure real UI actions and worker execution. Do not infer general AI completion accuracy from transport tests or page rendering.

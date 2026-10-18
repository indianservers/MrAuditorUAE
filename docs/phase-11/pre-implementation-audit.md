# Phase 11 pre-implementation audit

Repository inspected on 18 October 2026. Branch `main`; origin is the requested MrAuditorUAE repository. Phases 4–10 contain substantial uncommitted work and are being preserved. No push is part of this phase.

## Dependency classification

- **Available; regression verification in progress:** FastAPI, PostgreSQL/Alembic revisions 0001–0010, Redis/Celery, Next.js, identity, tenant RLS, engagement grants, immutable audit revisions and review separation. Baseline output is retained beside this document.
- **Available with limited scope:** accounting imports, GL/TB, DuckDB analytics, reconciliation and sampling; no live Zoho/Tally credentials. Tools must bind entity and period to an authorized engagement and bound every result.
- **Available with limited scope:** external audit workpapers and evidence; IFRS calculations and reporting snapshots; CT/QFZP; VAT/e-invoicing; TP; DMTT; GRC/monitoring. These engines have their own approved-source and licensing checks. Retrieval is not a replacement calculation or professional conclusion. Unsupported specialist operations must remain explicit.
- **Available with limited scope:** Phase 9 TensorFlow.js CPU runtime and immutable model/inference/evaluation ledger. Synthetic validation is experimental. Existing governed training/deployment remains separate from investigation requests.
- **Available with limited scope:** one existing AI provider gateway, approved model/template configuration, schema parsing and usage records. Mock diagnostic provider is available; semantic quality of an external model requires configured credentials and approved disclosure. No second provider infrastructure will be introduced.
- **Available with limited scope:** private versioned local/S3 object storage, hashes, evidence versions, bounded file validation. Evidence without a configured available ClamAV scanner remains quarantined. Indexing must not bypass that restriction.
- **Missing before this phase:** durable cross-module agent planner, unified tool registry, investigation state machine, permission-aware chunk retrieval, document extraction corrections/matching, exact-payload AI approval gateway and unified command center.
- **Blocked by external provider/license:** live LLM evaluation, licensed IFRS/ISA full text and commercial comparable datasets. Official source metadata is not a licensed technical corpus.
- **Missing/optional infrastructure:** pgvector and OCR availability must be detected. A lexical fallback must identify itself accurately; it must not be presented as semantic embedding retrieval.

## Inspected implementation boundaries

`app/modules/ai_engine/service.py`, provider adapters, accounting APIs/models, audit execution service/access/evidence, IFRS/tax/VAT/TP/DMTT services, ML events/runtime, GRC services and workers, role permissions, tenant session setup, guarded demo utilities and frontend API/BFF/workbench conventions were inspected.

Authorization rechecks active identity, membership, tenant role policies and engagement grants. GRC owner scope is narrower than professional scope. Platform or AI administration must not imply client-data access. Existing ordinary reads sometimes take engagement row locks; long workflow computation should avoid holding these locks across provider calls.

## Planned security boundary

Typed allowlisted tasks and tools; no SQL, code, shell, network or training tools exposed to model output. Retrieved text is untrusted. Each read rechecks source access, current version and scope. Proposals preserve payload hashes and dependencies, require independent authorized humans, and cannot bypass domain review chains. Unsupported consequential executors remain disabled.

Security references consulted: [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/), [OWASP LLM guidance](https://genai.owasp.org/llm-top-10/), [NIST GenAI profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence). This is a control design, not certification.

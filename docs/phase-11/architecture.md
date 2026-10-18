# Unified AI architecture

FastAPI owns authorization and orchestration. PostgreSQL owns durable state, immutable events and source lineage. Redis/Celery dispatch bounded work; a pending state remains recoverable if dispatch fails. Next.js uses the existing authenticated BFF. Phase 9 owns model inference/training/deployment and private evidence storage remains the only binary store.

The planner selects reviewed task recipes, rather than letting model output invent tools. Each recipe delegates to typed specialist tools. A final quality pass records missing/failed sources; narrative may be requested through the existing provider gateway with a bounded source context. Neither narrative nor model scores can establish professional conclusions.

Workflows save each step transactionally. Resume reauthorizes the initiating identity and validates completed-step source versions. A stale dependency requires a new investigation rather than silently combining versions. Per-run serialization and step identities prevent duplicate receipts. Cancellation is checked at step boundaries. Workflow results are reauthorized when served, including citations and exports.

Proposals are separate from domain approvals. Exact payload and dependencies are hashed; an independent reviewer decides. The first supported executor creates a draft evidence review workpaper only. Existing professional review remains mandatory. Financial postings, report publication, external communication, ML deployment and rule interpretation changes have no automatic executor.

Document extraction reads a current approved clean evidence version, verifies its private object hash and stores bounded page/section chunks with extraction lineage. Scanned pages without available OCR are reported as needing OCR, not treated as empty evidence. Corrections create new extraction versions. Retrieval applies source authorization and current-version checks before selecting and returning excerpts.

This document describes the intended architecture. Verification status and scope belong in the final phase report and must not be inferred from this design.

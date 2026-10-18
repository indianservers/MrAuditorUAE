# Source-linked retrieval

The implemented backend is PostgreSQL keyword search over bounded chunks, with source authorization and current-version checks both before content is returned and on subsequent citation reads. Tenant, client, entity, period, engagement, document version, extraction identity, page/section, confidentiality, source reference and hash are preserved. Current implementation permits confidential/restricted labels but does not define a second classification-based clearance hierarchy beyond existing resource access.

Reopening evidence, changing versions or correcting an extraction invalidates earlier chunks. Reindex current approved sources. Prompt instructions are never the authorization boundary. The explicit narrative endpoint uses only validated supplied citations through the existing AI gateway, with a 11000-character context cap, 30 requests per user/hour and approved external disclosure required for non-mock providers.

Semantic embeddings, pgvector indexing, hybrid reranking, legal effective-date filtering and shared prior-engagement retrieval are not implemented. Metadata effective_date is currently null for extraction chunks. Do not call keyword retrieval hybrid semantic RAG. A generated citation being valid proves source identity/access, not that the model's interpretation is supported; live semantic grounding evaluation remains required.

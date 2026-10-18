# API inventory

Canonical GRC routes are under /api/v1/grc/engagements/{eid}. Typed schema metadata is available from /workspace; /api/v1/grc/frameworks supplies public standards metadata, rule source requirements and task names. The same engagement/team infrastructure is retained.

- GET /workspace, /dashboard, /records/{kind}, /records/{id}/history.
- POST /records/{kind}; PATCH /records/{id}; POST /records/{id}/actions.
- POST /records/{id}/calculate; POST /internal-audits/{id}/transitions.
- GET /rcm, /runs, /alerts, /alerts/{id}/source.
- POST /monitoring/{id}/execute; POST/GET /schedules; PATCH /schedules/{id}.
- POST /samples; POST /sod/import (bounded evidence-matched multipart CSV).
- POST /policies/{id}/acknowledgments; GET /notifications.
- POST /ai; POST /board/{id}/publish.
- GET /board/packages, /board/packages/{id}, /board/packages/{id}/export/{pdf|docx}.
- Existing /api/v1/ml/predictions/{id}/feedback and /datasets/{id}/curation consume registered monitoring inference.

Frontend routes are /grc/{engagementId}/{area} for all 24 grcAreas in grc-studio.tsx and /board for restricted recipients. /grc is the engagement chooser. Access uses the existing cookie-protected BFF and tenant header; bearer tokens are not exposed to browser storage.

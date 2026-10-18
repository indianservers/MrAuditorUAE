# Phase 6 API inventory

- `GET /api/v1/tax/legislation` — Legislation
- `GET /api/v1/tax/engagements/{eid}/workspace` — Workspace
- `GET /api/v1/tax/engagements/{eid}/records/{kind}` — Records
- `POST /api/v1/tax/engagements/{eid}/records/{kind}` — Create
- `POST /api/v1/tax/engagements/{eid}/computations/{profile_id}` — Compute
- `POST /api/v1/tax/engagements/{eid}/calculate/{rid}` — Calculate
- `GET /api/v1/tax/engagements/{eid}/runs` — Runs
- `POST /api/v1/tax/engagements/{eid}/loss-transfers/{rid}/post` — Post Transfer
- `GET /api/v1/tax/engagements/{eid}/runs/{rid}` — Result
- `GET /api/v1/tax/engagements/{eid}/loss-ledger/{profile_id}` — Losses
- `GET /api/v1/tax/engagements/{eid}/runs/{rid}/export/{format}` — Export
- `POST /api/v1/tax/engagements/{eid}/ai` — Suggest
- `POST /api/v1/tax/engagements/{eid}/ai/{rid}/decision` — Decide

Tax records also use the existing engagement audit PATCH and actions endpoints for optimistic versioning, independent approval and immutable history. Tax schemas are returned by the engagement workspace endpoint. Lists accept bounded pagination. Exports require tax.return.export and engagement access. Full request/response schema: openapi.json.

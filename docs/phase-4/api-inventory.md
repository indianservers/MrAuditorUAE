# Phase 4 API inventory

Generated from the implemented FastAPI OpenAPI schema. All paths below use authenticated tenant and service authorization except invitation redemption. List endpoints are bounded; audit record bodies use strict kind-specific validation in the service.

- `GET /api/v1/admin/users`
- `GET /api/v1/admin/roles`
- `GET /api/v1/admin/permissions`
- `POST /api/v1/admin/roles/{rid}/permissions`
- `POST /api/v1/admin/invitations`
- `POST /api/v1/admin/invitations/redeem`
- `PATCH /api/v1/admin/users/{mid}`
- `POST /api/v1/admin/client-access`
- `GET /api/v1/admin/activity`
- `POST /api/v1/engagements/{eid}/audit/evidence-files/{rid}`
- `GET /api/v1/engagements/{eid}/audit/evidence-files/{rid}`
- `GET /api/v1/engagements/{eid}/audit/evidence-files/{rid}/{vid}/download`
- `GET /api/v1/client-portal/requests`
- `POST /api/v1/client-portal/requests/{rid}/view`
- `POST /api/v1/client-portal/requests/{rid}/responses`
- `POST /api/v1/client-portal/requests/{rid}/upload`
- `POST /api/v1/engagements/{eid}/audit/ai-actions`
- `POST /api/v1/engagements/{eid}/audit/ai-actions/{rid}/accept-procedure`
- `GET /api/v1/admin/methodology/starter`
- `GET /api/v1/admin/methodology`
- `POST /api/v1/admin/methodology`
- `POST /api/v1/admin/methodology/{mid}/approve`
- `POST /api/v1/engagements/{eid}/audit/methodology/{mid}/instantiate`
- `GET /api/v1/engagements/{eid}/audit/workspace`
- `GET /api/v1/engagements/{eid}/audit/team`
- `POST /api/v1/engagements/{eid}/audit/team`
- `GET /api/v1/engagements/{eid}/audit/linkable-sources`
- `GET /api/v1/engagements/{eid}/audit/team-candidates`
- `POST /api/v1/engagements/{eid}/audit/policy`
- `POST /api/v1/engagements/{eid}/audit/quality-review`
- `POST /api/v1/engagements/{eid}/audit/transition`
- `GET /api/v1/engagements/{eid}/audit/completion-checks`
- `POST /api/v1/engagements/{eid}/audit/select-sample`
- `GET /api/v1/engagements/{eid}/audit/review-queue`
- `GET /api/v1/engagements/{eid}/audit/records/{rid}/history`
- `PATCH /api/v1/engagements/{eid}/audit/records/{rid}`
- `POST /api/v1/engagements/{eid}/audit/records/{rid}/actions`
- `GET /api/v1/engagements/{eid}/audit/{kind}`
- `POST /api/v1/engagements/{eid}/audit/{kind}`
- `POST /api/v1/ai/audit-procedures`

The existing engagement POST/PATCH APIs remain; arbitrary status changes are denied. The existing workspace access response now supports portal-only identities. Evidence download is authenticated, scoped and attachment-only.

Total application paths: 106. New Phase 4 APIs share the existing `/api/v1` application.

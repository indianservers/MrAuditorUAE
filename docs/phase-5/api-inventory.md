# API and frontend inventory

Prefix: `/api/v1`. IFRS routes:

- GET `/ifrs/standards`.
- GET `/ifrs/engagements/{eid}/workspace`.
- GET/POST `/ifrs/engagements/{eid}/records/{kind}`.
- POST `/ifrs/engagements/{eid}/calculate/{record_id}`.
- GET `/ifrs/engagements/{eid}/runs` and `/runs/{run_id}`.
- POST `/ifrs/engagements/{eid}/financial-statements/{profile_id}`.
- GET `/ifrs/engagements/{eid}/adjusted-trial-balance/{profile_id}`.
- POST `/ifrs/engagements/{eid}/consolidation/{record_id}`.
- GET `/ifrs/engagements/{eid}/runs/{run_id}/validate`.
- GET `/ifrs/engagements/{eid}/runs/{run_id}/export/{pdf|xlsx|docx|json}`.
- POST `/ifrs/engagements/{eid}/runs/{run_id}/propose-journal`.
- POST `/ifrs/engagements/{eid}/ai-actions`.

Versioned mutations reuse PATCH `/engagements/{eid}/audit/records/{rid}`, POST `.../{rid}/actions`, GET `.../{rid}/history`. Creation through `/engagements/{eid}/audit/ifrs-{kind}` uses identical strict schemas and hooks. The BFF allowlist forwards tenant/auth headers without exposing tokens to JavaScript. See openapi.json.

Frontend landing `/ifrs`; sixteen routes `/ifrs/{eid}/{area}`: dashboard, designer, trial-balance, adjustments, cash-flow, notes, ecl, revenue, leases, deferred-tax, fixed-assets, impairment, consolidation, intercompany, disclosures, ai. Impairment offers provision inputs; ECL offers EIR instruments; Designer offers package approval records.

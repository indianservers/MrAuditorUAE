# Vat Engine

Implemented in `backend/app/modules/vat` and `backend/app/api/v1/vat*.py`; migration0007. Strict typed VAT profiles/rules/invoices/adjustments/recovery/returns/readiness are versioned AuditRecords with revision and independent review history. Immutable `vat_computation_runs` store inputs, source versions, methodology, official rule URLs, hashes and exact decimal results. `synthetic_datasets` records guarded demo versions. Both tables force tenant RLS; run mutation is rejected by a PostgreSQL trigger.

Workflow: independently approve rules and taxpayer profile; prepare and validate source invoice facts; approve evidence and invoices; reconcile actual active journal lines and full VAT control balances; resolve exceptions; prepare a return workpaper; Tax Manager and independent Tax Partner/CA review; export current source-linked JSON. No tax filing endpoint or tax registration automation is represented.

GET legislation/workspace/records/runs are scope checked. Record and run lists paginate; invoice direction and reference/supplier search use backend filtering. Reconciliation rows are served50 at a time. A run's dependency check includes newly approved invoices/adjustments, source status/version and inactive journal batches. Maximum approved invoice population is20,000 per run; larger periods must be partitioned or require a future execution design. Computation remains synchronous. Cash-basis profiles fail closed pending specialist methodology.

VAT source classifications are human-reviewed legal facts. This is a preparation engine within the stated scope, not universal UAE VAT certification. Historical rule adoption requires independent technical review; a catalogue URL alone does not approve an interpretation.

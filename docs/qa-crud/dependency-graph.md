# Dependency graph

```mermaid
flowchart TD
Client --> Entity --> Period --> Import --> Snapshot
Snapshot --> GL --> TB --> IFRS --> Tax
IFRS --> Consolidation
GL --> Analytics --> Sampling
GL --> VAT
GL --> TP
GL --> Features --> Model --> Prediction --> AI
Mapping --> TB
Mapping --> Analytics
Mapping --> Features
ReviewedRecords --> IFRS
ReviewedRecords --> VAT
ReviewedRecords --> TP
ReviewedRecords --> GRC
ReviewedRecords --> AI
```

The graph represents dependency families, not evidence that every edge has a complete browser regression. Immutable calculation dependencies capture record id/version/status. ML datasets now capture active source snapshot hashes and chart mapping versions. The permission-filtered `GET /engagements/{eid}/audit/dependencies` registry verifies current receipts synchronously on every read with per-module paging. Source supersession and mapping changes never rewrite approved historical outputs.

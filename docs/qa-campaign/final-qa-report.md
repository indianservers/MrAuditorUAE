# AuditOS UAE QA campaign status

Status: **CONDITIONAL INTERNAL QA ONLY; FULL CAMPAIGN ACCEPTANCE NOT YET SATISFIED**.

Actual clients: 25; journal lines: 1000590 (1000000 scale records); engagements: 119; users: 163; VAT invoices: 5. Full record counts are in module-record-counts.json.

Latest unique backend results: 473 passed, 0 failed, 2 skipped. Financial fixtures: 22 passed. QA workflow scenarios: 15 passed, 0 failed. Roles: 61; backend role checks: 305; permission failures: 0.

Frontend: 196 routes visited. API: 276 operations discovered; 414 contract probes. This does not establish complete control or business-case coverage.

Fixed client code search with backend/browser reproduction and retest. Corrected populated-database test fixture source scope. Actual TensorFlow fitting/inference executed. See numerical/model-results.json for actual measured values.

The experimental classifier's held-out precision, recall and F1 were all zero (40 records); OOD scores were also zero (20 records). It remains experimental and is not production validated. Deterministic baseline F1 was 1 on those small fixtures. External model factual accuracy was not measured.

At 100 concurrent synthetic users, the completed post-index read benchmark had zero failed responses and p 95 9.84 seconds, compared with 22.24 seconds before optimization. One intermediate transport-disconnect attempt is retained; this is not production capacity certification.

All data is isolated synthetic QA. Existing demo backed up and preserved. No production deployment, no real client data sent externally. Source changes are uncommitted for review.

All 100 scale snapshots now have source-CSV-derived TB comparisons, persisted reconciliations and deterministic sampling runs. The accounting-workflow-results.json file records each result. Three real broker jobs completed successfully; worker-results.json contains measured throughput.

Remaining work and severity: unresolved-blockers.md. Detailed counts/performance/model metrics: summary.json. Raw commands/evidence: commands.md, XML/log/JSON files.

# Defects and retests

QA-001 MEDIUM — client directory advertised code search but backend searched only names. Reproduced by Playwright and search-before.xml. Fixed with escaped ORquery in ResourceService for Clientonly. search-after.xml and browser-controls-final.txt pass.

QA-002 TEST HARNESS — TP fixtures used all tenant journal lines when financial result lacked period_id. In populated databases this selected foreign engagement sources; production correctly rejected 422. Fixture now constrains entity+period; original failures and TP reruns retained.

QA-003 TEST HARNESS — same entity/year scale replacement correctly blocked 409. Generator now uses separate historical periods. QA-004 HARNESS — overall tablecount included concurrently executed workflow lines; checkpoint now counts only source-manifest batch IDs.

QA-005 QUALITY LIMITATION — defaults flagged all 200 normal fixture lines. An explicit source configuration (exact near-duplicates, daily velocity 500) flagged zero normal lines and retained all eight directly testable labels. Both runs are retained. This small synthetic calibration is not a production accuracy study.

QA-006 MEDIUM, FIXED — default ledger pagination sorted a million-row tenant population. Migration 0013 adds (tenant_id, created_at, id). With refreshed statistics, measured page query fell from 314.505 ms to 0.332 ms. Completed 100-user workload p 95 fell from 22.24 to 9.84 seconds. One intervening transport-disconnect run remains recorded.

QA-007 HIGH, OPEN — the actual three-epoch classifier achieved held-out and OOD precision/recall/F1 of zero. The deterministic baseline scored 1 on this tiny fixture. The model remains experimental, production_validated=false, with no production promotion. Workflow PASS means artifact and authorization assertions passed, not model accuracy acceptance.

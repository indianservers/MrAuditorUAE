# Deployment preparation runbook

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

**NO-GO for production; no deployment performed or authorized.**

1. Select explicit pilot modules, controller jurisdiction/residency and independent professional/security reviewers; resolve release-gates.json blockers.
2. Provision authorized isolated staging, private DB/Redis/S3/KMS/IAM and approved secret delivery; validate regional health/capacity and cost quote.
3. Build immutable frontend/backend images, generate SBOMs, scan complete images/IaC and archive digests. Existing CI gates remain enabled; run hosted CI rather than assuming templates pass.
4. Create verified encrypted backup/object manifest; rehearse clean/upgrade migration, previous-release compatibility, application rollback and restore.
5. Run migration job, API/worker and one Beat; explicitly subscribe celery, grc, enterprise-ai, intelligence. Verify scanner signatures and fail-closed behavior, TLS/domain, session MFA, operators and tenant entitlements.
6. Run authorized synthetic staging smoke/E2E/security/accessibility/load and paging drills. Do not seed the demo into production.
7. Obtain manual environment/professional/security/customer approval with exact release evidence; only then authorize a separate deploy workflow. release-gate.yml intentionally contains no deployment step.
8. Start restricted invited pilot, monitor evidence-backed thresholds, preserve rollback point and pause on any release blocker.

Run scripts/release_gate.py against release-gates.json; it must exit nonzero while gates are unverified. No empty success placeholder permits deployment.


## Queue readiness correction — 25 October 2026

The staging worker previously omitted `intelligence` although the application routes country/source intelligence jobs there. The template now subscribes to all four configured queues. Its health command runs `python -m app.workers.queue_health --timeout 3`, verifies the exact worker's active subscriptions against the application's default queue and routes, and fails closed on missing consumers or unverifiable replies. New configured routes therefore require an explicit consumer update. Dynamic routers require a separate assessment.

`worker-queues-before-results.xml` preserves the regression reproduction (two failures from the missing queue). `worker-queue-consumption-initial.json` preserves the first probe's CLI argument failure; the harness was corrected before the successful run. `worker-queue-consumption.json` records the final local execution: healthy with all consumers, unhealthy after removing `intelligence`, healthy after restoring it, and one completed marker task on each of the four queues. The probe verifies ownership of its private empty Redis process before use/shutdown and confirms its worker and broker stopped. It performs no application database operations.

Repeat from the repository root with the existing private local test configuration:

```powershell
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py .venv/Scripts/python.exe ../scripts/worker_queue_contract.py ../deploy/compose.staging.yml
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py .venv/Scripts/python.exe ../scripts/verify_worker_queue_consumption.py
backend/.venv/Scripts/python.exe scripts/country_workflows_run.py .venv/Scripts/python.exe -m pytest tests/unit tests/phase12/test_release_gate.py tests/phase12/test_deployment_queues.py -q --junitxml=../docs/phase-12/worker-queues-regression-results.xml
```

The final regression receipt records **1,606 passed and 4 skipped** across backend unit, release-gate and deployment-queue tests; scoped Ruff checks also pass.

This is a Windows solo-worker synthetic proof using Redis 5.0.14.1, not qualification of the container, hosted Redis, production worker pool, migration, recovery or application rollback. Those release gates remain open. Real redacted pilot inputs and independently checked expected results are still required in the country pilot folders; synthetic fixtures do not establish client qualification.

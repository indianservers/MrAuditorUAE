# Deployment preparation runbook

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

**NO-GO for production; no deployment performed or authorized.**

1. Select explicit pilot modules, controller jurisdiction/residency and independent professional/security reviewers; resolve release-gates.json blockers.
2. Provision authorized isolated staging, private DB/Redis/S3/KMS/IAM and approved secret delivery; validate regional health/capacity and cost quote.
3. Build immutable frontend/backend images, generate SBOMs, scan complete images/IaC and archive digests. Existing CI gates remain enabled; run hosted CI rather than assuming templates pass.
4. Create verified encrypted backup/object manifest; rehearse clean/upgrade migration, previous-release compatibility, application rollback and restore.
5. Run migration job, API/worker and one Beat; explicitly subscribe celery, grc, enterprise-ai. Verify scanner signatures and fail-closed behavior, TLS/domain, session MFA, operators and tenant entitlements.
6. Run authorized synthetic staging smoke/E2E/security/accessibility/load and paging drills. Do not seed the demo into production.
7. Obtain manual environment/professional/security/customer approval with exact release evidence; only then authorize a separate deploy workflow. release-gate.yml intentionally contains no deployment step.
8. Start restricted invited pilot, monitor evidence-backed thresholds, preserve rollback point and pause on any release blocker.

Run scripts/release_gate.py against release-gates.json; it must exit nonzero while gates are unverified. No empty success placeholder permits deployment.

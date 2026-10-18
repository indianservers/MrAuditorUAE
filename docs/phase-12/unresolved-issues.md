# Unresolved issues

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

## P12-B01 — BLOCKER: Production deployment rollback is unverified

Status: OPEN. No authorized production/staging account, prior immutable release images or tested application rollback

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B02 — HIGH: Hosted infrastructure and container security unqualified

Status: OPEN. Local Trivy IaC/Dockerfile configuration scan completed with two low findings; Docker image build/scan and Terraform provider/account validation remain unavailable; templates are not deployment evidence

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B03 — HIGH: Real malware scanner and parser isolation need qualification

Status: OPEN. Fail-closed quarantine exists; synthetic scanner doubles are not ClamAV assurance; staging scanner not run

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B04 — HIGH: AI and ML lack representative professional validation

Status: OPEN. No authorized real customer datasets, licensed full-text standards/corpora, live model evaluation or calibrated deployment evidence

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B05 — HIGH: Independent security and privacy approval outstanding

Status: OPEN. ASVS 5.0.0 partial assessment, no independent penetration test, DSR execution/retention/legal and subprocessor sign-offs incomplete

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B06 — HIGH: Production monitoring and remote recovery remain unverified

Status: OPEN. Local restore passed; production PITR, alert delivery, regional failure recovery and RTO/RPO acceptance not tested

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B07 — MEDIUM: TFJS transitive dependency advisories

Status: OPEN. Three moderate npm findings through argparse/sprintf-js; no compatible current patch reported, not exposed as a customer formatting API

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B08 — MEDIUM: Billing provider and invoices not connected

Status: OPEN. No provider credentials/selection or live webhook/payment testing; no cards or charges simulated

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B09 — MEDIUM: Full primary-action/browser/accessibility matrix incomplete

Status: OPEN. 27 regression scenarios do not equal every requested end-to-end workflow; axe sample and keyboard checks do not establish WCAG conformance

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-B10 — MEDIUM: Demo reset is intentionally not a destructive truncate

Status: OPEN. Valid demo reused. Immutable professional history requires reviewed archival/reset procedure; no tenant-wide destructive reset was introduced

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-L01 — LOW: S3 access-log target not configured in infrastructure template

Status: OPEN. Trivy AWS-0089 remains; select an approved private log target, retention and residency before deployment

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

## P12-L02 — LOW: RDS performance telemetry not configured in infrastructure template

Status: OPEN. Trivy AWS-0133 remains; qualify the current provider telemetry option, retention, cost and alert delivery

Next action: Complete the linked operational runbook and obtain required environment/data/reviewer access.

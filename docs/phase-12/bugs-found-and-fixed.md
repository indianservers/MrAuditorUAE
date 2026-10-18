# Defects found and fixed

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

## P12-001 — Access tokens survived logout

Severity: HIGH. Status: FIXED_VERIFIED.

Reproduction: Login, call /auth/me, logout, call /auth/me with the same token.

Root cause: Refresh revocation was not checked by access-token authorization.

Fix: Bind issued access JWTs to RefreshSession IDs and check revocation/expiry; production rejects unbound tokens.

Regression: test_logout_immediately_revokes_access.

## P12-002 — Production admitted demo configuration

Severity: HIGH. Status: FIXED_VERIFIED.

Reproduction: Set production plus a demo flag/database identity.

Root cause: Production settings only checked bootstrap and signing length.

Fix: Reject demo/test database names and demo flags; API, worker and Beat production startup checks schema, role safety and synthetic tenant markers/known demo identity.

Regression: test_production_demo_configuration_forbidden.

## P12-003 — Invalid document amount corrections crashed matching

Severity: MEDIUM. Status: FIXED_VERIFIED.

Reproduction: Correct amount to non-numeric, NaN or Infinity and request matches.

Root cause: Bounded strings lacked typed validation.

Fix: Validate Decimal finiteness/scale/bounds, ISO date/currency; tolerate invalid legacy amounts.

Regression: test_invalid_correction_rejected; test_legacy_invalid_amount_does_not_crash_matching.

## P12-004 — Revoked AI initiator left endlessly dispatchable work

Severity: MEDIUM. Status: FIXED_VERIFIED.

Reproduction: Queue an investigation then disable initiating membership.

Root cause: Worker authorization errors rolled back without terminal receipt.

Fix: Stop denied/stale workflows in a separate transaction with immutable event; idempotent on redelivery.

Regression: test_revoked_ai_worker_stops_durably_instead_of_retrying_forever.

## P12-005 — ML cancellation delayed by read locks

Severity: HIGH. Status: FIXED_VERIFIED.

Reproduction: Train, immediately start longer training and cancel while metadata refreshes.

Root cause: Immutable ML source and list reads acquired engagement FOR UPDATE, delaying UI mutation settlement.

Fix: Use non-locking authorized ML reads; retain final write locks and reauthorize/recheck deployment after inference.

Regression: test_ml_metadata_read_does_not_wait_for_training_engagement_lock; phase9 browser training cancellation.

## P12-006 — Login eyebrow insufficient contrast

Severity: MEDIUM. Status: FIXED_VERIFIED.

Reproduction: Run axe on /login.

Root cause: Small teal text measured 4.15:1 against white.

Fix: Darken login-form eyebrow to #236b7c.

Regression: phase12 browser WCAG check.

## P12-007 — Mobile login overflow

Severity: MEDIUM. Status: FIXED_VERIFIED.

Reproduction: Open /login at 390px.

Root cause: Fixed 360px form plus padding exceeded viewport.

Fix: Use width:100%, max-width:360px and allow form shrinkage.

Regression: phase12 browser reflow check.

## P12-008 — New staging root build context lacked local-secret exclusions

Severity: HIGH. Status: FIXED_STATICALLY_REVIEWED.

Reproduction: Inspect the root-context staging Dockerfile and root ignore rules; no image build or secret upload was executed.

Root cause: A root Docker build does not inherit backend/.dockerignore.

Fix: Add root .dockerignore for credentials/private/runtime artifacts and restrict runtime COPY to app/migration sources.

Regression: Static source review and Trivy Dockerfile configuration scan; actual image/context build remains an external release gate.

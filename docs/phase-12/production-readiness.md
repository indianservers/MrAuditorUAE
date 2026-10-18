# Release readiness scorecard

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

**Production decision: NO-GO. Internal synthetic evaluation: CONDITIONAL GO. No aggregate percentage offsets a blocking control.**

- Functional coverage: PARTIALLY_VERIFIED; regression and route observations do not cover every primary action.
- Financial accuracy: PARTIALLY_VERIFIED; selected exact fixtures passed, independent professional current-period scope approval pending.
- Security: PARTIALLY_VERIFIED; dependency/SAST/secret checks executed; full ASVS/DAST/container/cloud review outstanding.
- Authorization: PARTIALLY_VERIFIED; tenant, role and professional tests passed in synthetic environments.
- AI/ML validation: PARTIALLY_VERIFIED/EXTERNAL_DEPENDENCY; keep experimental and restricted.
- Test execution: evidence in release-test-matrix; skips retained separately; existing coverage threshold unchanged.
- Performance: PARTIALLY_VERIFIED; bounded local 10/50/100-user read waves and 10k–1m arithmetic/analytics workloads.
- Accessibility: PARTIALLY_VERIFIED; sampled axe/keyboard/reflow, no conformance declaration.
- Infrastructure: NOT_TESTED at provider/container level; templates only.
- Recovery: VERIFIED local synthetic database/private objects; production PITR/regional drill pending.
- Monitoring: PARTIALLY_VERIFIED; structured logs/readiness live, exporters/tracing/paging not connected.
- Documentation: current repository evidence/runbooks prepared; named human sign-offs pending.

Hard blockers include unverified deployment rollback, hosted security/operations qualification, privacy/professional scope acceptance and any failed existing CI coverage gate. See defect-register.json and release-gates.json.

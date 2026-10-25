# Controlled pilot plan

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Recommended decision: **CONDITIONAL GO for internal synthetic evaluation only; NO-GO for customer production**.

Stage 1: internal CA/audit team reviews isolated demo, arithmetic fixtures and workflow/role evidence. Stage 2: invited professional reviewers approve explicit module/version scope and remaining defects. Stage 3: only after all production blockers close, obtain explicit customer/controller authorization for a limited read-only integration pilot; verify lawful data handling, actual source completeness and recovery. Stage 4: controlled computation with independent reconciliation/reviewer sign-off; expand only after acceptance.

Exclude unvalidated ML, semantic/OCR/legal-corpus claims, live filing, unconnected ASP/billing/ERP providers and unsupported complex regulatory treatments. Review all AI narrative and confirm deterministic evidence. No FTA/IFRS Foundation/IAASB certification is claimed. Maintain a signed module enablement/feature-entitlement list, success/stop criteria, support and rollback owner.


## Artifact-bound evidence gate — 25 October 2026

The manual release workflow now consumes the selected evidence manifest, source commit, immutable image digest and exact target-environment identifier. Inputs enter the shell through quoted environment variables. The protected `production-review` environment remains in place, and the workflow contains no deployment step.

Run the checker from the repository root with independently selected artifact values:

```text
python scripts/release_gate.py path/to/reviewed-manifest.json --commit <immutable-source-commit> --image-digest sha256:<image-content-digest> --environment <exact-target-identifier>
```

The version-2 manifest binds `release.commit`, `release.image_digest` and `release.environment` to those arguments. All ten existing required gates remain required. Each gate needs status `VERIFIED`, no open blocker, a repository-relative executed-receipt path and its exact SHA-256. String blocker values, omitted hashes, missing gates and legacy unbound labels are rejected. The unfilled `release-gates.template.json` illustrates the structure and remains unqualified.

Each version-1 receipt names its exact gate and the same release identity, records `PASS` and an actual timezone-aware execution timestamp, and references one to thirty nonempty execution artifacts with their own paths and SHA-256 values. Receipts for another gate, image, commit or target cannot be reused. Partial outcomes, future/invalid timestamps, duplicate JSON fields, duplicate artifact paths, path traversal, references to the receipt/manifest itself, empty files and changed bytes fail closed. JSON reads are bounded to 1 MiB; raw evidence files are hashed in chunks with a 100 MiB per-file bound. `release-gate-receipt.template.json` starts as `NOT_EXECUTED` with no artifact claims.

Evidence paths resolve inside the checked workspace and may be populated by an authorized private evidence-retrieval step; they need not be Git-tracked. Keep sensitive client originals in their approved private evidence store. Bind retained, appropriately redacted execution/review artifacts to the selected release. The gate verifies the integrity and binding of reviewed receipts; their execution, professional content and infrastructure claims still require actual independent assessment. It does not infer a provider run, image build or professional sign-off from a status label.

The historical `release-gates.json` remains a NO-GO scorecard, with hosted security, application rollback, production recovery and professional/customer qualification still open. No existing gate was marked verified and no production deployment was performed by this change. The manual workflow must receive a real reviewed version-2 manifest before it can pass.


Verification: `artifact-bound-release-gate-results.xml` records 1,586 passing tests (four existing skips): the full 1,549-test backend unit suite plus 37 gate checks. Tests cover exact target binding, tampered receipt/raw artifacts, absent hashes, open blockers, partial outcomes, duplicate JSON keys, bounded JSON reads, timestamp handling, path containment, actual CLI success/failure exit codes, historical-manifest refusal and the workflow's quoted input wiring. Positive receipts are confined to explicitly synthetic test fixtures. Scoped Ruff/format checks, YAML parsing and UTF-8 validation pass. No hosted qualification is inferred from these local results.

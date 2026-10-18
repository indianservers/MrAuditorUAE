# Guarded synthetic inventory

Guard conditions require development mode, explicit synthetic enablement, the exact demo database, the fixed synthetic tenant and its marker. Scripts fail closed before mutation. No production tenant data was used. Scripts/enrich_phase10.py is idempotent by stable P10 references and uses actual create/submit/approve endpoints. Original journal count remains 250,024; all original financial facts are retained.

- grc-alert-decision: 1
- grc-assessment: 100
- grc-board: 2
- grc-closure: 1
- grc-control: 200
- grc-deficiency: 51
- grc-engagement: 10
- grc-framework: 1
- grc-kri: 20
- grc-link: 300
- grc-monitor-rule: 32
- grc-obligation: 20
- grc-plan: 1
- grc-policy: 1
- grc-qaip: 1
- grc-remediation: 101
- grc-report: 2
- grc-risk: 100
- grc-scoring: 3
- grc-sod-access: 1
- grc-sod-rule: 1
- grc-test: 102
- grc-third-party: 10
- grc-universe: 10

- Actual immutable alerts: 13,320.
- Annual plan commitments / internal audit scopes: 10.
- Reviewed management action workpapers: 100 base plus proof scenario.
- Base rule definitions: 30, with additional worker and configured SoD proof rules recorded separately.

Proof records and browser-created scoring drafts can increase these values on later reruns. Counts are evidence from demo-verification.json, not hardcoded UI values. Evidence references are explicitly synthetic software fixtures, never real control assurance or market/legal evidence.

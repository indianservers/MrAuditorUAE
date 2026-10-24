# Phase 4 — audit and financial operations

Implemented and verified against labeled synthetic records. This is a bounded strengthening of the existing E10–E14 engines; it is not a claim of production audit, ISA or IFRS compliance. Existing event, revision and JSONB stores carry the new contracts; no additional SQL migration is required. Existing period-lock migrations remain prerequisites.

## Supported capabilities

- Shared `audit-operations/1` receipts retain tenant, entity, period, currency, implementation hash, source versions, parameters, execution mode and exceptions. Execution success, population scope, reviewer approval and professional conclusions remain separate. Source or implementation changes invalidate retained downstream work.
- E10 supports scoped risks, linked procedures and performed steps, independent review, evidence provenance, corrected/uncorrected misstatement registers, deterministic exclusions and certainty selection. Sampling retains the original and residual populations, seed, selected IDs and algorithm version. It explicitly rejects unsupported statistical evaluation and projection.
- E11 retains actual trained-model, statistical-baseline, rules-baseline, diagnostic-mock and unavailable modes. Explicit baseline inference preserves its true mode. Ranked baseline observations can receive human dispositions and become idempotent draft audit workpapers through the existing review chain. Missing operating-calendar inputs make the weekend rule not testable. Feedback does not automatically become a training label.
- E12 adds explicit confirmed-cash allocation against invoice face amounts, rejecting duplicate, excessive, mismatched-currency and unsupported allocations. Unapplied receipts remain separate. Independently reviewed remaining balances feed the existing E09 ECL calculation. ECL retains historical/forward components, evidence and reasoned specific overrides.
- E13 produces draft payment proposals and holds from procurement matching, supplied approval facts and bank-change checks. It creates no payment instruction. Repeated downstream finding adapters reuse their canonical audit record.
- E14 tightens identity matching and ambiguity handling: amount/date alone cannot establish a match; mixed-sign groups cannot silently net fees or refunds. Retained bank reconciliations become stale after source correction and require recalculation and independent reapproval.

## Verification evidence

The isolated runner `scripts/audit_operations_run.py` uses a dedicated test database and object store, with external AI credentials disabled. Integration fixtures replace scanner/broker boundaries with explicit test doubles; calculation, persistence, authorization, review and freshness paths execute against the real application/database.

- [Revenue cycle](revenue-cycle.json): approved E09 revenue schedule; invoice 100, confirmed cash 70, explicit allocation 40, remaining receivable 60 and unapplied cash 30; forward-adjusted 10% ECL produces 6; scoped audit selection and manager/partner evidence review.
- [Procurement and bank revision](procurement-bank-revision.json): order/receipt/invoice matching, draft proposal 100 without payment execution, confirmed payment and independently controlled bank reconciliation; rejected source makes the historic result stale; corrected source, recalculation and review restore current status.
- [Journal review](journal-review.json): actual rules execution and explicitly selected statistical baseline; reproducible sample with certainty items and documented exclusion; human disposition, retry-safe workpaper creation and independent approvals.
- [Audit population revision](audit-source-revision.json): replacement of the underlying imported ledger makes prior testing stale and blocks locking.
- `unit-results.xml`, `integration-results.xml`, `frontend-results.xml` and `tensorflow-results.txt` contain retained execution results. `verification.json` records counts and file hashes. The initial integration run is retained separately; its two failures exposed a missing explicit import-supersession fixture and an obsolete duplicate-evidence fixture. Both fixtures were corrected and rerun.

TensorFlow.js is the local ML runtime. The retained Node test run actually trains and reloads four synthetic pipelines and checks leakage, abstention, tensors, cache and artifact failures. It uses the JavaScript CPU backend; the native Node binding is not installed. Synthetic test success is not client-model validation. The connected journal demonstration deliberately uses the reported statistical baseline, not a claimed trained model or fraud conclusion.

## Limitations and Phase 5 prerequisites

See [gap-matrix.json](gap-matrix.json) for explicit supported and incomplete areas and [source-policy-register.json](source-policy-register.json) for references. Before broader release:

1. Approve the applicable jurisdiction, audit-standard edition, materiality policy, operating calendars, account mappings, source completeness and ECL assumptions with responsible reviewers. The source register is reference metadata, not automatic policy adoption.
2. Supply production evidence for supplier-master approvals, independently verified bank changes and payment-release segregation. Current proposal flags are reviewed supplied facts, not bank-account ownership verification. Add the controlled release workflow before enabling payment execution.
3. Implement and independently validate any required statistical sampling evaluation/projection, arbitrary strata or replacements. Current selections cannot support unsupported confidence or extrapolation claims.
4. Extend controlled credit-note, advance, dispute, write-off and foreign-currency allocation cases before enabling those operations. Add procurement returns, tax-inclusive/service and foreign-currency matching policies as needed.
5. Complete treasury loan/deposit/guarantee/trade-finance/covenant integrations with E09 measurement and E05/E07 tax analysis. Existing forecast and accounting schedules remain available, but a complete automated treasury-to-accounting bridge is not delivered here. Fees and FX reconciliation differences require explicit reviewed bridges.
6. Obtain lawful representative data and independently approved labels, validate held-out client performance and thresholds, and approve model deployment. Verify host memory/process quotas and any native TensorFlow binding installation separately. Language-model availability does not establish local model readiness.
7. Run deployment-specific isolation, recovery and concurrency checks, including source-version staleness and period-lock enforcement, with the final Phase 5 scope frozen. Review the unresolved matrix before any production release.

No demonstration sends messages, releases payments, writes off balances or posts live journals. No final audit opinion is inferred from completed jobs or clean analytics.

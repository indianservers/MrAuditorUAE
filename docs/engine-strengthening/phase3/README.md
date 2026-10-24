# Phase 3 — financial reporting and accounting

This phase strengthens the existing IFRS workbench and its immutable calculation runs. It does **not** certify complete IFRS compliance, operate a production payroll bureau, or release a complete group reporting package. Implemented calculations, technical fixture results and remaining dependencies are distinguished below. Existing source imports, evidence revisions, permissions, independent reviews, tax engines and reporting overlays are retained.

## Runtime and contracts

E09 and E15–E18 use deterministic Python `Decimal` arithmetic. TensorFlow.js and the optional language-model provider do not calculate accounting balances, choose policies or approve journals. The connected tests run with external AI disabled.

Each new IFRS calculation retains an `accounting/1` receipt inside the existing immutable `ifrs_calculation_runs.results` JSONB. It identifies tenant, entity, engagement, period, currencies, implemented framework, approved input record/version, profile/policy version, retained financial/chart snapshots, currency rounding policy, evidence references, calculation version and implementation hash, supporting runs, E05 releases, unresolved issues and draft review state. Profiles implement `full_ifrs` only; that label identifies the selected framework, not compliance certification. Historical receipts are not rewritten. A historical run without the new implementation receipt is stale for new release/proposals.

Schedule arithmetic uses precision 48 and eight-place HALF_UP result schedules. Proposed journals use the tenant's configured currency precision/rounding, falling back to currency minor units and HALF_EVEN. Financial presentation retains its approved profile precision. A changed currency policy, active chart, source record, evidence context, supported run or implementation invalidates dependent use. This is checked on read/review/export and before applying approved overlays; there is no claim that a background service automatically recalculates every stale draft.

No new database migration is needed: this work uses existing JSONB workpapers/runs, immutable history and the Phase 1 period lock. Migration `0020_foundation_periods` and the existing IFRS/tax migrations are prerequisites. The dedicated verification database was migrated with Alembic; the working application database was not migrated by this phase.

## E09 — reporting and tax connections

- Existing approved ledger-to-mapping, original/adjusted balance, statement, note, equity and cash-flow calculations remain authoritative. Unmapped accounts and comparative mappings are rejected; notes are tied to statement amounts. Opposing-sign account aggregation now requires an explicit netting rationale. Mappings retain current/noncurrent, related-party and disaggregation attributes; completeness of those professional classifications is not automatically inferred.
- A retained active chart may supply genuine zero-balance accounts for proposed adjustments. No zero journals or balancing entries are invented. The financial snapshot remains the source of financial balances; a chart change invalidates affected runs.
- A structured `accounting-policy` workpaper captures material policies, judgments, estimation uncertainty, policy/estimate changes, errors, subsequent events, going concern, related parties, commitments and contingencies. It uses existing independent approval and evidence history. It is distinct from sample disclosure wording. It does not replace a licensed complete disclosure checklist.
- Financial release now checks source execution issues, supporting schedule issues and source/evidence freshness in addition to existing statement controls. Approved input assumptions, a calculated schedule, a proposed adjustment, its approval and source-ledger posting remain distinct.
- Deferred tax retains item-specific carrying values/tax bases, approved rates/effective dates, recovery/settlement assessments, recoverability evidence, exceptions and P&L/OCI/equity/business-combination movements. A loss and a recognition tick alone no longer create a DTA. Unsupported recovery recognition is zero with a blocking issue. Ordinary IAS 12 calculations exclude E08 GloBE deferred-tax measurement.
- `current_tax_run_id` consumes the current independently approved ordinary E05 corporate-tax release, checks exact current-tax amount and source freshness, and retains its hash. Reviewers require access to the E05 source. The post-tax report uses a **separate reporting profile**: approved pre-tax financials → E05 → E09 tax schedule → post-tax profile. Changing the E05 base profile instead would create a cycle and is blocked. Accounting recognition never establishes tax deductibility; E05 adjustments remain separately reviewed.

## E15 — assets, leases and impairment

Fixed assets now retain an evidenced available-for-use date separately from capitalisation/acquisition, location, ownership evidence, verification status, components and construction in progress. CIP is not depreciated. Missing availability evidence leaves legacy capitalisation-date arithmetic explicitly provisional and blocks a generated adjustment. Derecognition excludes its date from the charge. Gross cost and accumulated depreciation rollforwards are returned with additions/disposals and closing carrying values. Prospective straight-line estimate changes split the charge at the approved effective date and use revised remaining life/residual; they do not rewrite prior depreciation. Residual above carrying produces zero charge. Diminishing-balance rates must be positive. IAS 40 investment property, IFRS 5 held-for-sale and IAS 38 intangible classifications cannot silently enter the PPE engine.

The existing lease engine retains irregular dated effective-interest/actual-365 measurement, up-front amounts, incentives, direct costs/restoration and reviewed accounting term/options. It now discloses ROU depreciation after the last payment to the approved term end. Initial liability proposals cannot be reused for a modified lease: the existing remeasurement comparison remains a draft requiring modification classification/journals. Lessor, sale/leaseback, terminations, indexed-rent reassessments and full modification accounting remain unsupported.

The existing explicit annual forecast impairment model retains supplied discount/valuation inputs, recoverable amount, goodwill-first loss allocation, reversal ceiling and sensitivities. Missing required valuation inputs fail validation. There is no valuation feed, expert verification, full asset-floor CGU allocation or blanket IAS 36 compliance claim.

## E16 — payroll and benefits

The existing `payroll-settlement` source/channel/bank reconciliation and supplied-regime `uae-benefit-review` calculator are retained. They are not replaced by a second statutory formula. Mainland, DIFC, ADGM and alternative schemes must be assessed separately; source retrieval does not approve employment rules.

New `employee-benefits` workpapers reconcile **aggregate supplied** obligation/service/past-service/interest/remeasurement/settlement figures to ledger provisions, and aggregate payroll expense/deductions/accruals/confirmed-payment inputs to payroll payable. P&L and OCI movements remain separate. Missing actuarial report reference for defined-benefit measurement blocks a proposal. A statutory settlement estimate is separately displayed and never substituted into the IAS 19 obligation.

This bridge stores no employee names, bank accounts or salary master. Existing scoped IFRS permissions limit its accounting information. It does not implement a restricted HR master, compensation changes, automatic joiner/leaver salary generation, overtime/leave formulas, payroll execution or payment instructions. Bank/payment inputs are reviewed supplied facts; actual matching remains in the existing country workflow. These are material E16 limits, not completed capabilities.

## E17 — inventory

New `inventory` calculations extend the existing IFRS calculation/workpaper API; the existing count/cut-off bridge remains the count-review engine. Supported purchased-stock methods are FIFO and moving weighted average, with opening cost, evidenced receipts/landed costs, dispatches, explicit same-day sequence, location/SKU/UOM/ownership and expected closing quantities. Negative stock, duplicate references, out-of-period movement and ambiguous order are rejected. A revised backdated valuation requires a revised/reapproved period input and a new immutable run; old approved valuation history is retained.

Location transfers require two declared legs with the same SKU, UOM, ownership, quantity, chronological sequence and **actual issue cost**. Missing/excess/different-cost legs remain blocking issues; there is no transfer profit or plug. NRV deducts supplied completion and selling costs; write-down reversals cannot raise carrying above cost or exceed the approved remaining prior write-down. Custody-only goods have zero recognized accounting carrying value. Quantity differences and valuation movements remain separate. Ageing does not create an automatic write-down.

Production/WIP/overhead allocation, purchase/sales returns, specific identification, automatic cost corrections across prior closed periods, goods-in-transit legal ownership determination and automated subledger-to-GL population matching are not implemented by this bounded costing schedule. Unsupported fields are rejected; specialist schedules are required.

## E18 — consolidation

Approved, current entity financial packages remain mandatory. The group input records control judgments rather than inferring control from ownership. Effective control dates and special conditions are explicit. Mid-period control changes, IAS 29/hyperinflation, nonrepresentative average rates, common control, equity-method and asset-acquisition packages are blocked. Identical source/presentation currencies require unit rates.

Supported draft aggregation distinguishes closing, representative average and historical rates, retains every source package amount/rate in each group line, identifies translation OCI and records proposed/approved input eliminations. Intercompany reciprocal differences are classified and retained; unmatched, reversed, ambiguous, duplicate or cumulatively excessive elimination attempts are blocked. Separate source evidence and member access checks apply.

With evidenced opening rates and reconciled member cash workings, the output retains opening cash, translated operating/investing/financing flows, local FX and the presentation translation effect. This is explicitly **before group cash eliminations**. The effect is calculated from independently supplied opening/closing cash and their rates plus approved member flows; it is not an invented cash balancing transaction. Member note inputs and group equity closing/profit/OCI are retained.

Group comparative translation, full group equity/ownership-event rollforwards, acquisition journals/valuation allocation, final NCI measurement, group cash eliminations/acquisition-disposal flows and group disclosure release are incomplete. NCI is explicitly provisional percentage-of-closing-net-assets arithmetic. Group `validation.ready` stays false. The group technical workflow demonstrates a reconciled draft and blocked release, not a final statutory consolidated package.

## Verification and technical workflows

All fixtures are clearly synthetic. Tests use actual backend routes, PostgreSQL RLS, retained imports, independent review and immutable records; no successful AI response stands in for verification.

- Baseline: **527 passed, 4 skipped** (`tests/unit` plus original IFRS numeric fixtures). Concurrent workspace work added unrelated tests later; the final aggregate count must not be attributed wholly to this phase.
- See `unit-results.xml`, `integration-results.xml`, `frontend-results.xml` and `verification.json` for the final actual results. The four unit-command skips are connector tests requiring their own database/Redis environment.
- Final retained results: **653 unit/calculation passes, 4 skips; 30 integration passes; 7 frontend passes**. Scoped Python/TypeScript lint, TypeScript checking and diff whitespace checks also passed. The integration suite additionally confirms that an entity currency/master-data change invalidates prior reporting execution without rewriting its historical currency or amounts.
- `operating-company-workflow.json`: same retained ledger, chart, sourced acquisition overlays, asset depreciation 365, inventory write-down 16, benefit movement 20, lease liability/ROU 1000, independent adjustment approvals, pre-tax profit **1,199,599**, cash difference **0**, approved E05 current tax **74,213.91**, E09 deferred liability **25.65**, post-tax profit **1,125,359.44**, cash difference **0**, independent financial release. All entries remain reporting overlays; the source ledger is not posted or overwritten. This validates the selected accounting case, not a full HR/payroll workflow.
- `group-workflow.json`: approved AED parent and USD-functional subsidiary, distinct FX rates, explicit elimination, provisional NCI and reconciled translated member cash workings. The automated test also demonstrates unresolved intercompany balances, blocked elimination, supported matched pairs, blocked midyear control change and blocked hyperinflation. Final group release remains blocked as described above.
- `controlled-revision-workflow.json`: original depreciation **365** remains immutable; a revised useful life produces a new run **730**; the old run becomes stale and cannot approve its pending journal. Revised assumptions and the new control journal receive independent approval. Reopening that journal and locking the period prevents further approval. Duplicate component proposals, including an identical-input rerun with a new calculation ID, and locked-period creation return 409. This fixture tests review/version/lock controls; the separate company fixture demonstrates actual accounting account selection and financial statements.
- Independent numeric fixtures also cover available-for-use/CIP/disposal, prospective estimates, residual floors, FIFO/weighted-average expected results, NRV reversal caps, custody exclusion, sequence/transfer reconciliation, regime labels, actuarial dependencies, missing valuation inputs and unevidenced DTA recognition. Existing reporting tests cover comparatives, permissions, tenant isolation, statement/note review and supported exports. The Phase 2 tax workflows are regression tested through the changed freshness controls.

Reproduce in the authorized local environment without exposing secrets:

```powershell
.\backend\.venv\Scripts\python.exe scripts/accounting_strengthening_run.py prepare
.\backend\.venv\Scripts\python.exe scripts/accounting_strengthening_run.py .venv/Scripts/python.exe -m pytest tests/qa_crud/test_accounting_strengthening.py tests/phase5/test_reporting.py tests/phase5/test_financial_workspace.py tests/phase6/test_workflows.py tests/phase6/test_specialist_workflows.py tests/qa_crud/test_connected_tax.py -q
```

The runner loads the existing private QA configuration without printing it, uses only `auditos_accounting_strengthening_test`, and stores test objects separately. Destructive fixture cleanup is restricted to that disposable database. Do not run those integration fixtures against the working application database.

The first wider regression run retained in `initial-regression-results.xml` had 27 passes and two failures. A group export could not display an explicitly unavailable opening-equity amount; exports now show “Not supplied” and the draft schedule status. The comparative fixture reused approvals after changing its reporting profile; it now reassesses and reapproves dependent mapping, cash-flow, note and disclosure inputs. The freshness control was retained. Final results are recorded separately in `integration-results.xml`.

## Sources, adoption and Phase 4 prerequisites

`source-policy-register.json` retains primary identity, URL, provision, retrieval timestamp/hash or access error, interpretation, edition/effective-date dependency and reviewer adoption state. Public IFRS overviews and selected historical issued provisions were checked against the touched calculations. Complete current licensed text, entity-specific applicability and professional policy approval remain required. UAE employment law, DIFC scheme/transitional requirements and ADGM regulations require separate verification; supplied rule parameters are not adopted simply because a download succeeds.

Before Phase 4 consumes these outputs:

1. Adopt current entity/period framework and source-backed policies, employment regimes, tax bases/rates and approved recovery forecasts; close every blocking receipt/schedule issue. Confirm complete retained populations and actual source evidence.
2. Supply authorized HR masters and a verified payroll/proration/leave/overtime/scheme implementation for real salary processing; supply independent actuarial work where required. Keep personal and bank details in restricted systems until corresponding backend access controls are implemented.
3. Supply real asset ownership/availability/component/valuation evidence; specialist lease modifications, impairment asset-floor allocations, non-PPE classifications and capitalization/borrowing-cost treatment remain separate work.
4. Implement/verify inventory returns, production and any required specific identification or closed-period recosting; reconcile owned quantities, count/cut-off evidence, costing and GL controls.
5. Complete acquisition/ownership/NCI/group-equity, comparative translation, reciprocal population coverage, cash eliminations and group disclosures before relying on a final group or DMTT package. Draft group totals must not be treated as a released package.
6. Keep the E05 base/post-tax-profile boundary acyclic, reapprove stale inputs, and re-run dependent calculations. Journal posting to a real ledger needs a separately authorized, verified posting connector with balanced accounts/period checks and idempotency. No such posting is claimed here.

`gap-matrix.json` is the per-engine capability → actual status → issue → consequence → implementation → verification register. These remaining prerequisites mean the entire five-engine production scope is not complete.

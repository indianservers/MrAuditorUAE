# Connected UAE tax engines — Phase 2

This delivery strengthens E04–E08 in the existing modular monolith. It preserves the Decimal accounting/import services, local TensorFlow.js CPU worker, separate language-model gateway, evidence repository, independent audit/tax review and immutable calculation history. No filing, authority contact, accounting posting or external communication was performed. Deterministic calculations require no language-model credentials.

## Implemented changes

- `tax/1` execution receipts are attached inside the existing CT, QFZP, VAT, TP and DMTT save paths. They identify tenant/entity/engagement/period, active journal snapshots and hashes, source completeness, account mapping receipt, adopted rule versions, calculation version, implementation hash, selected registrations/elections, assumptions, unresolved questions, accounting amount and calculated liability where applicable. Review, payment, filing and authority-assessment states remain separate. No receipt asserts authority acceptance.
- Tax, VAT and TP freshness checks compare saved snapshot and mapping receipts. Implementation fingerprints bind calculations to the deterministic kernel, schema and service files. A changed source population, mapping or calculation implementation requires regeneration; prior saved content remains intact.
- VAT now tracks cumulative credit-note net/VAT amounts against the original invoice and flags mismatched original treatment/currency/supplier. Excess credits block return readiness instead of being silently netted into a return. Optional supply references/stages expose advance/final-invoice overlap; final-after-advance netting remains explicitly blocked pending a separately validated schedule. Existing inclusive/exclusive, discounts, foreign-currency, reverse-charge and reviewed recovery calculations remain authoritative.
- QFZP outputs include classified and unresolved revenue bounds and best/adverse de-minimis sensitivity. Unknown counterparties are not promoted to qualifying income. Existing qualification and CT consequence checks still require reconciled approved segments.
- Duplicate loss lots now fail rather than being utilized twice. Existing posted loss/transfer ledgers, foreign credit restrictions and release guards remain in use. CT results that depend on approved TP judgments now recheck the underlying TP run transitively, so changed benchmark/FAR inputs can invalidate the downstream tax result.
- DMTT incomplete revenue/MNE facts produce `INCOMPLETE_SCOPE`, with no invented zero liability. Pre-2025 fiscal starts are outside the applicable period. UAE investment entities no longer silently disappear from an ordinary-case calculation: special blending is unsupported and blocked. Calculation outputs distinguish a genuine computed zero from applied safe harbour and out-of-scope status. Unsupported computation work is preserved as a blocked immutable result with `uae_dmtt: null` and references to retained source schedules.
- DMTT memo submission/approval now requires a selected immutable calculation, matching group, current sources and a determinate supported result. Calculation listings show freshness. Scope can be assessed separately through `/api/v1/dmtt/engagements/{eid}/scope-assessment`, even while the group information is incomplete.
- Connected assessments at `/api/v1/tax/engagements/{eid}/connected-assessments` reference existing authoritative runs rather than copying calculations. They keep VAT, CT, pricing and UAE top-up bases separate, carry immutable dependencies, block stale selections and unresolved approval, and require an independent authorized tax approver. The CT workspace exposes run selection; existing VAT, CT/QFZP, TP and DMTT result screens show the shared execution/review notice.
- A necessary Phase 1 repair permits explicit tax-group member references while rechecking record access in those member engagements. Other implicit cross-engagement links remain rejected. This restores controlled tax-group aggregation without opening tenant-wide source access.

## Primary-source verification

Eight official-hosted PDFs were retrieved and hashed. `source-retrieval.json` records original URLs, retrieval timestamps, retained local files, hashes and HTTP outcomes. `rule-source-register.json` adds the limited provisions checked, applicability/effective-date metadata and restrictions. Retrieval does not activate a rule or approve an entity's facts. Officially hosted English translations may be labelled unofficial; legal interpretation must account for the controlling Arabic text.

The scoped checks cover CT rate bands in Cabinet Decision 116/2022, DMTT scope/ordinary aggregation/SBIE transitions in Cabinet Decision 142/2024, the adoption/repeal instrument MD96/2026, free-zone de-minimis requirements and amendment relationships in MD229/2025, the extension wording in MD131/2026, VAT rounding in the retained consolidated Executive Regulation, FTA13/2026 identity/commencement, and the official TP guide's identity and methodological context. These checks do not certify all existing tax parameters or implement every adopted international guidance provision.

MD131/2026 extends the specified SBR end date to 31 December 2029, but commences the day after publication. The PDF's signature date does not establish the Gazette/publication date. The extended rule therefore requires a retained source hash, reviewed publication evidence, a publication date and a legal-as-of date after commencement. The application does not silently replace every historical rule with a 2029 default. Test fixtures use explicitly synthetic commencement attestations, not a representation of an actual Gazette publication.

## Per-engine status and supported-case inventory

### E04 — VAT

Runtime: existing invoice validation, VAT201 computation, control-account reconciliation, immutable exports and return review exercised against real local PostgreSQL and HTTP paths.

Supported: explicit human-reviewed standard/zero/exempt/outside/reverse-charge/import/deemed treatments; positive source-document magnitudes with credit-note reversal; inclusive/exclusive calculation, discounts, AED conversion and mathematical fils rounding; reviewed recovery percentages; selected rule/evidence checks; actual source-line and full control-account comparisons. New original-credit caps, source completeness receipts and advance/final overlap blockers strengthen this path.

Rule verification: the retained consolidated Executive Regulation and FTA13 decision were retrieved; rounding and scoped source dates were checked. All statutory conditions, registration facts, FX rates and treatment classifications remain approved inputs. Free-zone status never supplies a VAT classification automatically.

Data/evidence readiness: readiness still depends on reviewed documents, invoice facts, valid selected rules and exact ledger/control reconciliation. A calculated refund or payable is not a return submission or accepted assessment.

Limitations: no general automatic place-of-supply/legal classification, general multipage invoice-item determination, automatic final-invoice/advance netting, general prior-period credit allocation, complete VAT-group membership timeline, or full designated-zone/property/bad-debt expert system was added. Existing special-assessment paths remain fact- and evidence-dependent. Unsupported netting is blocked rather than guessed.

### E05 — corporate tax

Runtime: approved financial packages through adjustments, exemptions, interest, loss allocation, SBR/QFZP, credits, tax computation, release and return-readiness tests exercised.

Supported: reconciled current-tax bridge using existing approved adjustment/election records, applicable rule snapshots, explicit source lines/evidence, limited statutory calculators, existing loss and transfer ledgers, restricted foreign-credit application and approved group aggregation. New receipts and transitive TP checks preserve connections and source versions; duplicate loss-lot application fails.

Rule verification: CT rate decision and SBR amendment text were checked against retained primary sources. The broader existing relief/interest/exemption catalogue was not wholly recertified in this task. Extended SBR adoption is specifically restricted by commencement evidence.

Data/evidence readiness: approved financial statements and reviewed adjustments remain prerequisites. The new connected review is a selected-control assessment, not tax certification. Accounting profit, adjustment, current liability, payments, return and authority statement remain distinct.

Limitations: not a universal current-tax rule executor for every restructuring, participation exemption, accounting-basis election or tax-group attribute. Existing unsupported cases retain professional assessment requirements. Automatic generic recalculation/review-task dispatch on every change remains unfinished; read/action-time stale guards work. Deferred tax is not computed here. `reporting_interface.py` defines a typed E05→E09 handoff for source tax bases, differences and loss/credit references only.

### E06 — free-zone tax

Runtime: existing approved segmentation/condition assessment and the CT consequence path exercised, including correction, rereview and recalculation.

Supported: revenue reconciliation, explicit activity/counterparty classifications, documented denominator exclusions, approved conditions, de-minimis numerator/denominator and existing scoped QFZP tax bridge. Added sensitivity separates confirmed nonqualifying revenue from unresolved revenue and shows both bounds without assigning favourable treatment.

Rule verification: MD229/2025 provisions on de-minimis, repeal/application and cessation period were checked; special activity eligibility still requires actual facts and reviewed sources. Incorporation, VAT designated zones and CT qualification remain separate dimensions.

Data/evidence readiness: contracts, activities, counterparties, substance, audit/TP/election conditions and profit/revenue bridges must be reviewed. Passing a numerical threshold alone cannot establish status.

Limitations: no automatic IP nexus calculation, complete activity-rule inference, or universal continuing-condition/disqualification timeline was added. Unresolved qualification or unreconciled profit blocks the CT release path.

### E07 — transfer pricing

Runtime: existing relationship/transaction reconciliation, segmentation, supplied benchmark imports/screening, loan and specialist calculators, licensing controls, documentation exports and reviewed CT adjustment bridge exercised.

Supported: existing transaction-specific analytical schedules and deterministic ratios/ranges, loan cash-flow accrual conventions, source-constrained benchmarking and review-based adjustments. Source permissions, licensing and synthetic-data labels remain in force. New common receipts and downstream CT freshness checks tie approved judgments to current underlying TP analysis.

Rule verification: official TP guidance was retained; source identity/methodology context is distinct from legislation. No market rates, comparable companies, credit ratings or licensed observations were invented. Synthetic benchmark populations support technical testing only and are explicitly unresolved for live pricing support in the new execution receipt.

Data/evidence readiness: actual conduct, agreements, reconciled transaction population, authorized data, screening and independent judgment are still required. Proposed CT adjustments and VAT effects do not automatically post or establish legal treatment.

Limitations: no universal guarantee/cash-pool/royalty valuation or VAT assessment was added. Existing manual specialist and documentation-readiness paths remain bounded. No live-data benchmarking effectiveness is claimed from synthetic workflow tests.

### E08 — UAE DMTT

Runtime: separate scope endpoint and existing ordinary UAE calculation/source review exercised. Missing scope facts, unsupported categories and stale memo sources now have explicit controls.

Supported: four-year revenue/MNE scope input, proportionate short-year thresholds, approved ordinary-entity financial packages, explicit GloBE and covered-tax adjustments, limited deferred-tax schedules, UAE jurisdictional aggregation, SBIE transition table, supported safe-harbour inputs, ETR/top-up and reconciled allocation. Domestic CT income is not substituted for GloBE income. IIR/UTPR charges are not introduced.

Rule verification: CD142 scope/ordinary arithmetic/SBIE provisions and MD96 adoption instrument were checked. This is not implementation of all commentary or adopted administrative guidance. Special-category and election eligibility remain reviewed inputs.

Data/evidence readiness: exactly one approved source schedule per roster member is required for the detailed computation. Approved source changes or new approved entity/election schedules make the prior result stale. A memo cannot conclude from an incomplete or unsupported null-liability result.

Limitations: investment/PE/JV/minority/stateless blending, group entry/exit/restructuring, technical loss/negative-covered-tax cases, advanced deferred recapture and unsupported elections require specialist schedules. Supported source records are retained when computation is blocked. UPE reporting-package accounting basis remains explicitly unsupported by the existing adapter; the verified case uses approved standalone IFRS financials. Safe-harbour application and a computed ordinary zero are distinct outcomes.

## Workflow evidence

All demonstrations are synthetic technical fixtures; no external filing or authority interaction occurs.

- Trading/current-tax path: existing VAT workflow proves source→classification→control accounts→draft VAT201→review; the CT workflow proves approved ledger/financials→adjustments→110,250 AED draft CT→two-stage review. The new connected assessment test proves current CT selection, independent approval, tenant boundary, subsequent approved adjustment→stale prior assessment and blocked stale reuse. These use the same application source interfaces; **the final test set does not prove one single fixture combining VAT and CT approvals for the same entity**, so do not present that broader A workflow as fully demonstrated.
- Free-zone path: actual revenue segmentation→approved qualification assessment→blocked unreconciled profit bridge→reviewed correction→recalculated CT workpaper and release. The supported synthetic result is zero only under its reviewed facts, not a general free-zone exemption.
- Related-party path: existing loan/authorized synthetic benchmark and CT adjustment workflows are exercised. Synthetic observations cannot establish a live arm's-length position; missing/restricted data remains blocked or explicitly provisional. The test set does not establish a universal financing→VAT→posted-entry workflow.
- Multinational path: approved standalone financial package→reviewed group/entity inputs→ordinary UAE jurisdictional DMTT calculation. A separate missing-information test records unresolved scope; investment/special cases block instead of disappearing. The verified demonstration is not a UPE reporting-package import or all-Pillar-Two implementation.

The scalar arithmetic/reconciliation schedules and their test references are in `calculation-schedules.json`. `connected-workflow.json` retains identifiers from the executed approval/invalidation case. Automated XML results and `verification.json` report actual outcomes; remaining scope is listed in `gap-matrix.json`.

## Migration, deployment and reproduction

No new database tables or migration were necessary: typed fields are additive in the existing versioned JSON bodies/results, while calculation and review histories use established tables. The Phase 1 baseline migration `0020` remains required. Only the dedicated disposable `auditos_connected_tax_test` database was prepared/migrated by this task. Working databases were not migrated and no deployment was performed.

Deploy API/workers/frontend together to use the new schemas. Legacy results are not backfilled with invented execution metadata: existing authoritative service checks remain available, while the new connected assessment requires regeneration where receipts are missing. Saved `tax/1` results become stale if their saved source/mapping receipts or implementation fingerprints differ. This is intentionally conservative. Explicit tax-group cross-engagement source permissions remain mandatory.

`scripts/connected_tax_run.py` uses the existing private local QA environment without printing secrets, pins a dedicated disposable database, and separates retained objects. Its tests intentionally reset that test database; never repoint destructive fixtures at a working database.

```powershell
.\backend\.venv\Scripts\python.exe scripts/connected_tax_run.py prepare
.\backend\.venv\Scripts\python.exe scripts/connected_tax_run.py .venv/Scripts/python.exe -m pytest tests/qa_crud/test_connected_tax.py tests/phase6/test_workflows.py tests/phase6/test_specialist_workflows.py tests/phase7/test_vat_workflows.py tests/phase7/test_regression_fixes.py tests/phase8/test_workflows.py tests/phase9/test_workflows.py::test_dmtt_actual_ifrs_approval_computation_and_ai -q
```

Source retrieval is a separate operator/research action, not a side effect of executing tax calculations. The retained PDF paths/hashes are in the source register. The PDF skill was used read-only for content inspection; no new legal source document was authored. The UI was typechecked and tested for state separation; this is not a claim of a full new browser visual-regression campaign.

## Exact Phase 3 prerequisites

1. Resolve the open selected-use-case gaps in `gap-matrix.json`. Do not assume the new common receipt certifies every legal condition or makes all four requested end-to-end demonstrations complete.
2. Adopt actual verified legal rule versions for each intended entity/period/election. In particular, retain MD131 publication/Gazette evidence before using its extended period window, validate special FZ facts, and qualify each DMTT special/election module before use.
3. Obtain authorized real comparable/loan observations and retain licensing, screening, statistical convention and limitations. Synthetic ranges cannot support live TP eligibility or pricing conclusions.
4. Complete the intended VAT advance/correction/group/special-supply adapters, financial-control reconciliations and financing VAT consequences before treating those cases as filing-ready. Resolve the previously recorded synchronous live-connector transaction blocker before relying on that source route; file-source tax tests do not qualify it.
5. Complete automatic invalidation follow-up/review-task generation and eligible draft recalculation through the existing idempotent job/outbox mechanism. Current read/release-time blocking does not replace those operational requirements.
6. E09 must consume approved current-tax/financial-run references, explicit asset/liability tax bases and difference classifications through the typed handoff. It must separately assess enacted/applicable rates, reversals, recognition/recoverability, losses, consolidation and disclosures. Current-tax adjustments are not a deferred-tax engine.
7. Re-run source/permission/staleness tests after deployment and perform the production-like browser and operational queue/storage/scanner checks required by the intended use case. Keep external filings and communications outside technical verification.

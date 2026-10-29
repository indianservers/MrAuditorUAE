import {useState,useHostTheme,H1,H2,H3,Text} from "cursor/canvas";
const data = {
  "date": "24 October 2026",
  "cases": [
    {
      "title": "01 · TCS reconciliation",
      "url": "https://coraa.ai/products/ai-agents/reconciliation/tcs-reconciliation",
      "scope": "India",
      "phase": "P4",
      "reference": "The page describes buyer-level collection checks, books/returns matching and tax-audit linkage. Its 206C(1H) proposition is historical; the hero is a general Form 3CD screen, not evidence of a working TCS engine.",
      "baseline": "PLANNED statutory adapter. Generic matching and regulatory version records can be reused; India statutory matching is explicitly rejected in intelligence/service.py.",
      "shared": "Create a collection/withholding register with separate collector and collectee roles, transaction dates, receipt dates, cumulative counterparty totals, certificates, payments and amended returns. Preserve gross base and each tax component.",
      "UAE": "No direct India-style TCS equivalent to activate. Show this workflow as not applicable to domestic UAE entities. Cross-border collections require the relevant foreign obligation pack; a UAE entity can have foreign obligations without becoming an Indian entity.",
      "India": "Build historical 27EQ/26AS adapters and qualified current-period successor adapters. Apply historical 206C rules by transaction/receipt period; disable 206C(1H) from 1 April 2025. Maintain old/new Act section and form crosswalks. Handle PAN status, certificates, specified goods, LRS purpose and amendments using approved rules, not page thresholds.",
      "acceptance": "Boundary fixtures straddling 31 March/1 April 2025; no new 1H liability after withdrawal; duplicate returns cannot duplicate collections; missing PAN or legal inputs yield pending review; collector and collectee figures never net together.",
      "current": {
        "id": "01",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Separate deductor/deductee and collector/collectee evidence, assessed rule/certificate references, pooled certificate limits, amendments/status and settlement linkage.",
        "UAE": "India TCS is unavailable for domestic UAE obligations. Use the common evidence/settlement foundations under an explicitly applicable obligation.",
        "India": "Withholding liability and credit workflows now accept controlled assessed TCS populations; historical 1H date guards and role isolation are implemented. Declared annual-credit statement headers now separate historical Form 26AS assessment years from Form 168 tax years, with PAN/period/snapshot consistency and scope retained in result/UI/XLSX.",
        "remaining": "Native 27EQ/current-successor, 26AS/168/AIS/TRACES completeness, full legal rate/threshold/certificate corpus and representative client qualification.",
        "evidence": [
          "backend/app/modules/country_workflows/withholding_schemas.py",
          "backend/app/modules/country_workflows/withholding_calculations.py",
          "backend/tests/qa_crud/test_withholding_workflows.py",
          "backend/app/modules/country_workflows/annual_tax_statement.py",
          "docs/phase-12/annual-statement-validation.json"
        ]
      }
    },
    {
      "title": "02 · Bank reconciliation",
      "url": "https://coraa.ai/products/ai-agents/reconciliation/bank-reconciliation",
      "scope": "Shared",
      "phase": "P1",
      "reference": "Account-level reconciliation, statement ingestion, causes of differences and aging. The advertised bank screenshot actually resolves to the generic Form 3CD image; it does not demonstrate a BRS.",
      "baseline": "PARTIAL. Deterministic transaction matching exists in intelligence/matching.py with 20,000 rows per side, currency separation, tolerances, ambiguity and bounded group matching. Supporting bank tables currently require CSV. This is not yet any-bank PDF ingestion or a fully evidenced closing BRS.",
      "shared": "Add account ownership/IBAN or account-number verification; opening/closing statement controls; exact reference/date/amount matches then bounded splits and settlement groups; partial payments, reversals, fees and interest; outstanding cheque/deposit classifications; aging, carry-forward and subsequent clearance. Generate a signed-balance bridge with zero unexplained residual.",
      "UAE": "Support AED and foreign-currency accounts, bank fees/VAT documents and FX differences separately. Add UAE bank CSV/XLSX templates first, then qualified English/Arabic PDF formats. Local payment rails are adapters, not matching assumptions.",
      "India": "Add Indian bank templates, UTR/NEFT/RTGS/IMPS/UPI identifiers, cheque clearing and payment-gateway settlements. Preserve value date and posting date independently. Tax effects of fees remain in the India pack.",
      "acceptance": "Each statement row accounted for once; correct opening-to-closing equation; duplicate statement prevention; ambiguous same-amount transactions remain unresolved; no cross-account or cross-currency auto-match. Benchmark 100k and 1m rows before expanding the existing bound; report ingestion and matching performance separately.",
      "current": {
        "id": "02",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Controlled BRS, account/owner evidence, ambiguity, opening/closing bridge, dates, outstanding carry-forward, subsequent clearance and cross-engagement cash-allocation checks. Retained matched groups now expose protected original transactions through separately paged read-only inspection. Explicit merchant batches now bridge gross sales, separately checked refunds/chargebacks, fees, assessed tax/withholding and reserves to net signed bank allocations. Partial and pooled payouts retain exact links; residuals block approval. Merchant results also retain separately paged booking/value-date provenance, reject reversed/value-date-only settlements and require regeneration of earlier result contracts. Merchant settlement can now retain a current independent account-document review covering the entire selected period, with unchanged originals and recursive withdrawal staleness. Separate processor reserve continuity now checks dated gross holds/releases, position-level available balances, independently controlled opening/closing statements and assessed receivable GL accounts, reusing the original reviewed processor source. Large XLSX populations retain individual movement and balance links; source withdrawal makes results stale.",
        "UAE": "Authorized committed GL plus bounded reviewed CSV/XLSX/PDF and native bank profiles; account/currency scope remains explicit. Hosted browser verifies committed-GL/native-CAMT matching, invalid-closing rejection, independent review, XLSX and replacement staleness. Merchant component arithmetic uses assessed UAE/foreign fee-tax labels without inferring VAT rates or recovery. Reserve continuity uses explicitly selected original currency and exact receivable controls, without claiming bank receipt, reserve ownership or VAT recovery.",
        "India": "Reuses the same reviewed account, statement, identifier/date and residual controls; no cross-account or currency auto-netting. The same merchant arithmetic uses separately assessed India/foreign fee-tax labels without inferring GST or withholding entitlement. The same reserve engine uses independently assessed India processor facts and original currency, without inferring GST/withholding entitlement or FX.",
        "remaining": "Qualify representative bank-specific files and extraction accuracy; supported profiles do not imply every bank or PDF layout. Qualify processor-native layouts, independent client schedules, reserve account classification/recoverability and any cross-workflow cash-reservation integration. Current reserve browser proof passed with four inspected original images; full current hosted regression remains pending.",
        "evidence": [
          "backend/app/modules/country_workflows/bank_accounts.py",
          "backend/app/modules/country_workflows/bank_consumption.py",
          "backend/tests/qa_crud/test_bank_matching_scope.py",
          "backend/tests/qa_crud/test_pdf_bank_tables.py",
          "backend/app/modules/intelligence/bank_matches.py",
          "frontend/src/features/bank-matched-proposals.tsx",
          "backend/tests/qa_crud/test_bank_matched_proposals.py",
          "frontend/e2e/bank-browser-workflow.ts",
          "docs/phase-12/bank-msme-browser-07f61f1.json",
          "backend/app/modules/country_workflows/merchant_settlements.py",
          "backend/tests/unit/test_merchant_settlements.py",
          "backend/tests/qa_crud/test_merchant_settlements.py",
          "frontend/e2e/merchant-browser-workflow.ts",
          "docs/country-workflows/merchant-settlements.md",
          "frontend/src/features/merchant-settlement-details.tsx",
          "frontend/tests/merchant-settlement-details.test.tsx",
          "backend/app/modules/country_workflows/review.py",
          "docs/phase-12/merchant-browser-20ee29a.json",
          "backend/tests/unit/test_merchant_bank_binding.py",
          "backend/tests/qa_crud/test_merchant_bank_binding.py",
          "docs/phase-12/merchant-account-browser-e119982.json",
          "backend/app/modules/country_workflows/merchant_reserves.py",
          "backend/tests/unit/test_merchant_reserves.py",
          "backend/tests/qa_crud/test_merchant_reserves.py",
          "frontend/e2e/merchant-reserve-browser-workflow.ts",
          "docs/country-workflows/merchant-reserves.md",
          "docs/phase-12/merchant-reserve-validation.json",
          "docs/phase-12/merchant-reserve-browser-9ba08d4.json"
        ]
      }
    },
    {
      "title": "03 · PF / ESI / professional-tax reconciliation",
      "url": "https://coraa.ai/products/ai-agents/reconciliation/pf-esi-pt-reconciliation",
      "scope": "India",
      "phase": "P4",
      "reference": "Monthly document-derived challan register, employee/employer/admin split, state-specific professional tax and differences against books. This page contains no dedicated product screenshot in the retrieved main content.",
      "baseline": "MISSING specialist dues engine. Shared evidence, extraction, ledger snapshots and review are available foundations; payroll enum values do not establish statutory coverage.",
      "shared": "A reusable statutory-dues subledger: employee cohort, wage month, obligation month, filing and payment dates, challan identifiers, employer registration, allocation and unallocated receipts. Compare payroll accrual → return → challan → bank settlement.",
      "UAE": "Use separate WPS/pension workflows where applicable, rather than relabeling PF/ESI/PT. Nationality, pension authority, prior membership and employment jurisdiction determine the pension scheme. No UAE professional-tax default.",
      "India": "Import ECR/EPFO, ESIC and state PT returns/challans; split EPF/EPS/EDLI/admin components; support arrears, supplementary challans and reversals. PT needs state, establishment, employee category and effective-date packs. Deposit timing and tax deductibility are separate tests.",
      "acceptance": "One challan allocated across multiple months without double counting; partial and late settlement explained; employee and employer balances reconcile independently; missing months are missing, never zero; state changes select the right PT rule.",
      "current": {
        "id": "03",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Assessed contribution bases/rules, employer and employee component separation, expected obligation derivation and explicit split bank settlement.",
        "UAE": "Separate WPS settlement and reviewed pension/benefit workflows; authority, cohort, eligibility and source documents are explicit.",
        "India": "Monthly/arrear ECR and bounded ESIC population profiles, source-bound payroll rules and distinct PF/EPS/ESI/PT assessments are implemented.",
        "remaining": "Complete qualified state/cohort packs, native challan coverage and representative portal/client files; administration/EDLI and legal deductibility must not be inferred from the current contribution workflow.",
        "evidence": [
          "backend/app/modules/country_workflows/pension_schemas.py",
          "backend/app/modules/country_workflows/payroll_schemas.py",
          "backend/tests/qa_crud/test_india_ecr_source.py",
          "backend/tests/qa_crud/test_payroll_rule_workflow.py"
        ]
      }
    },
    {
      "title": "04 · GST reconciliation",
      "url": "https://coraa.ai/products/ai-agents/reconciliation/gst-reconciliation",
      "scope": "India",
      "phase": "P3",
      "reference": "Document-level invoice/note matching across books and GSTR-1/2A/2B/3B, multi-GSTIN controls, reverse-charge checks, cess and IMS-rejected records. The actual hero image is a TDS/26AS screen, so GST functionality remains a content claim.",
      "baseline": "PLANNED/UNQUALIFIED India adapter. Source extraction detects GST fields but does not establish GST return parsing, invoice eligibility or return reconciliation.",
      "shared": "Create canonical tax documents with immutable source-file versions, registration, document type, signed amounts, original-note reference, filing period, tax period, supply location and tax components. Keep every registration separate before controlled entity aggregation.",
      "UAE": "Reuse document matching for VAT, but do not create a fake GSTR-2B equivalent. UAE return reconciliation compares transaction registers, VAT201, customs/import records and payment evidence; supplier invoice evidence and input-tax recovery tests are separate.",
      "India": "Prioritize purchase register vs 2B, then sales vs GSTR-1, books vs 3B, 2A historical movements, IMS status, RCM, cess and 9/9C bridges. Handle amendments and delayed credits, blocked/conditional credits, reversals/reclaims, imports, exports and ISD where in scope. Validate current GST rules independently; do not copy the page’s provisional-credit language or link GST variances indiscriminately to TDS Clause 34.",
      "acceptance": "Invoices and credit/debit notes match as separate records; rejected records remain visible; GSTIN-month control totals balance; multiple return versions are never summed; legally unavailable credits stay distinct from timing differences; authoritative schema fixture for each supported return version.",
      "current": {
        "id": "04",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Versioned controlled tax documents, notes, independent source totals, registration/component/period separation and explicit missing/rejected evidence.",
        "UAE": "VAT201 aggregate-14, emirate-20 and ecommerce-20 comparisons, 72 e-commerce split/summary checks, reviewed book composition and source-bound operational report presets. Receipt-location and qualifying-status assessments are separate.",
        "India": "Bounded GSTR-1 document/summary/series and GSTR-2B profiles, notes/amendments and controlled retrieval parts supplement canonical GST comparisons.",
        "remaining": "Complete portal/schema qualification, legally assessed credit/recovery eligibility, full annual-return scope and authorized filing/action execution.",
        "evidence": [
          "backend/app/modules/country_workflows/gstr1_schemas.py",
          "backend/app/modules/country_workflows/gstr2b_parts.py",
          "backend/tests/qa_crud/test_india_gstr1_source.py",
          "backend/tests/qa_crud/test_india_gstr2b_source.py",
          "backend/tests/qa_crud/test_vat_composition.py",
          "backend/app/modules/country_workflows/vat201_arithmetic.py",
          "backend/app/modules/regulatory/report_packs.py",
          "backend/tests/unit/test_vat_ecommerce.py",
          "backend/tests/qa_crud/test_vat_emirates.py",
          "docs/country-workflows/uae-vat201-ecommerce-source.json"
        ]
      }
    },
    {
      "title": "05 · TDS reconciliation",
      "url": "https://coraa.ai/products/ai-agents/reconciliation/tds-reconciliation",
      "scope": "India",
      "phase": "P4",
      "reference": "Deductee credit matching and deductor liability testing are distinct; vendor/section drill-downs and books-only tests support tax-audit preparation. The drill screenshot shows source vouchers and explicitly missing TAN evidence.",
      "baseline": "PLANNED India statutory adapter; reusable matching, approved source tables and immutable calculation receipts exist.",
      "shared": "Keep withheld tax receivable separate from withholding payable. Match by legal counterparty identifiers, section/rule, transaction, assessment/tax year and certificate/return version. Add expected vs deducted vs deposited vs reported columns and cause codes.",
      "UAE": "Do not require Indian 26AS/AIS/24Q/26Q or domestic TDS filing. The current UAE CT withholding rate is 0% under the cited FTA guidance. Track foreign-source withholding and treaty/credit evidence through a separately scoped cross-border workflow.",
      "India": "Import books, 26AS/AIS/TRACES, 24Q/26Q/27Q and challans as applicable to historical periods; qualify current successor forms. Include cumulative thresholds, timing, non-resident cases, certificates, invalid identifiers and amended filings. Reconcile overlapping AIS/26AS observations without duplicating credit.",
      "acceptance": "Deductee credit never clears deductor liability; return correction supersedes prior values; certificates apply only within their dates and amounts; March and other due-date exceptions use legal versions; credit mismatch is not an automatic recoverable-tax conclusion.",
      "current": {
        "id": "05",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Distinct expected, withheld, reported, deposited and credit populations; source-bound assessments, pooled certificate controls and separate bank allocations.",
        "UAE": "Indian domestic TDS workflows stay unavailable. Applicable UAE CT/obligation assessments use their own source-linked workbenches.",
        "India": "Controlled deductor/deductee TDS liability/credit reconciliation and derived payment obligations are implemented, with no inferred legal entitlement. Declared annual-credit statement headers now separate historical Form 26AS assessment years from Form 168 tax years, with PAN/period/snapshot consistency and scope retained in result/UI/XLSX.",
        "remaining": "Native 24Q/26Q/27Q and successor forms, complete 26AS/168/AIS/TRACES profiles, current legal rate/threshold rules and professional expected schedules.",
        "evidence": [
          "backend/app/modules/country_workflows/withholding_obligations.py",
          "backend/tests/qa_crud/test_withholding_workflows.py",
          "backend/tests/qa_crud/test_withholding_obligations.py",
          "backend/app/modules/country_workflows/annual_tax_statement.py",
          "docs/phase-12/annual-statement-validation.json"
        ]
      }
    },
    {
      "title": "06 · Indian tax audit / historical Section 44AB",
      "url": "https://coraa.ai/use-cases/section-44ab-tax-audit-automation",
      "scope": "India",
      "phase": "P5",
      "reference": "Ledger-linked tax-audit clauses, depreciation, disallowances, statutory payments, cash transactions and related parties. The screenshot shows 44 clauses, only 3 active, 32 pending review, yet a Completed badge; it is not proof of comprehensive preparation.",
      "baseline": "PARTIAL infrastructure, MISSING qualified tax-audit calculation pack. New uncommitted regulatory library and statement/report builders are visible in this checkout; they require their own verification and do not establish complete Indian tax-audit coverage.",
      "shared": "Build a report/obligation graph: each disclosure has applicability, required inputs, calculation receipt, supporting schedules, exception disposition and independent approval. Clearly separate generated, prepared, reviewed and issued states.",
      "UAE": "No Form 3CD clone. The corresponding business need is source-linked CT computation, accounting-to-tax adjustments and audited-financial-statement applicability. Reuse existing UAE CT/QFZP/TP workbenches and the common report composer.",
      "India": "Support legacy 3CA/3CB/3CD for FY2025–26 and earlier applicable periods, and the 2025 Act/2026 Rules Form 26 regime for Tax Year2026–27. Maintain clause crosswalks. Add depreciation blocks, payment/disallowance schedules, cash rules, related parties, ICDS/145A historical requirements, MSME payment rules and supporting GST/TDS/TCS schedules in validated increments.",
      "acceptance": "Wrong-period form selection blocked; each derived field links to evidence; no blanket claim that all clauses come from GL; stamp values, contracts, related-party registers and declarations explicitly requested; unresolved mandatory clauses prevent issuance.",
      "current": {
        "id": "06",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Declared report requirements, applicability, evidence-backed non-applicability, current-source validation, authorship separation and unsigned generated drafts.",
        "UAE": "Source-linked CT workbench and audited-financial-statement obligation assessment; nonresident scoped revenue requires retained reviewed evidence.",
        "India": "Tax-period-based legacy/current form selection plus a 65-entry Form 26 numbered-item/schedule-group evidence index for report A/B and particulars C/D. Every covered item must match an exact-period/preset/applicability declaration in a current independently reviewed workpaper, with substantive section and protected source links. Assessed micro/small supplier invoice payment timing now retains supplier eligibility, acceptance/objection/written terms and exact split bank allocations; separate context document bytes, current versions and independent contributor review are required.",
        "remaining": "Full independently approved Form 26/legacy 3CD subfields, statutory schedules/calculations and legal mappings; original Form 26 PDF archival/visual/professional qualification and client expected results. The 65-entry structural index is not a completed official tax-audit form or filing. MSE tax deductibility, statutory interest and complete disclosure packs remain separate unimplemented procedures; timing output is not a tax deduction.",
        "evidence": [
          "backend/app/modules/regulatory/tax_forms.py",
          "backend/app/modules/regulatory/report_requirements.py",
          "backend/app/modules/tax/audit_revenue.py",
          "backend/tests/qa_crud/test_tax_audit_scope.py",
          "backend/tests/qa_crud/test_report_requirements.py",
          "backend/app/modules/regulatory/form26_index.py",
          "backend/app/modules/regulatory/workpaper_report_scope.py",
          "frontend/src/features/workpaper-report-scope.tsx",
          "backend/tests/unit/test_workpaper_report_scope.py",
          "backend/app/modules/country_workflows/msme_payments.py",
          "backend/app/modules/country_workflows/msme_evidence.py",
          "backend/tests/qa_crud/test_msme_payments.py",
          "docs/country-workflows/india-msme-source-scope.json"
        ]
      }
    },
    {
      "title": "07 · GST and tax audit orchestration",
      "url": "https://coraa.ai/use-cases/gst-tax-audit-automation",
      "scope": "India",
      "phase": "P5",
      "reference": "A combined tax engagement joining GST, input-credit checks, withholding and tax-audit reports. This overlaps cases 01/04/05/06 and should be a workflow package rather than another calculation engine.",
      "baseline": "PARTIAL audit orchestration and review; specialist India tax results are still absent/unqualified. Existing UAE VAT/CT calculations are bounded workbenches, not proof of India support.",
      "shared": "Create a tax-close workspace with registration/obligation calendar, source readiness, turnover bridges, missing evidence, exposure summaries, client questions and linked tax schedules. One normalized source powers multiple workpapers with stale-input propagation.",
      "UAE": "UAE tax close joins VAT201, CT, QFZP, transfer pricing and DMTT only when applicable. Corporate-tax, VAT-group and accounting-group boundaries must remain distinct.",
      "India": "Join GST turnover, financial turnover, income-tax turnover and tax-audit disclosures with explained differences. Keep filing period distinct from financial year. Assess GSTR-9/9C applicability and current self-certification requirements; avoid treating every annual reconciliation as a mandatory CA-certified GST audit.",
      "acceptance": "No duplicated tax exposure when the same finding appears in several workpapers; changed source invalidates dependent draft figures; each registration and statutory period is covered or explicitly missing; all source control totals tie.",
      "current": {
        "id": "07",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Tax-close evidence/readiness and exact finding-ID exposure deduplication. Currency/sign and unknown exposure remain distinct; stale sources cannot support current conclusions.",
        "UAE": "Reviewed VAT/CT schedules, exact-layout VAT201 report presets (including e-commerce components), registration-period turnover bridge, committed-GL books and reviewed multi-source composition. Operational agreement does not establish legal completeness.",
        "India": "GST/withholding/payroll evidence joins the same source-linked close. Turnover scope, return and adjustments remain independently reviewed inputs.",
        "remaining": "Qualify complete country obligation/report packs and annual applicability; a reconciled close does not establish legal filing completeness.",
        "evidence": [
          "backend/app/modules/regulatory/exposure_rollup.py",
          "backend/app/modules/country_workflows/turnover_composition.py",
          "backend/tests/qa_crud/test_tax_close_rollup.py",
          "backend/tests/qa_crud/test_turnover_composition.py"
        ]
      }
    },
    {
      "title": "08 · Statutory audit",
      "url": "https://coraa.ai/use-cases/statutory-audit-automation",
      "scope": "Shared",
      "phase": "P2 / P5",
      "reference": "Ledger analytics, CARO clauses, related parties, workpapers and report generation. The CARO image distinguishes manual and automated rows but displays zero addressed clauses; its headline counts also need clarification.",
      "baseline": "PARTIAL substantial foundation: external-audit execution, materiality, risks, testing, evidence, review and reporting. India Schedule III drafts and applicability/report composition code are work in progress. No complete Companies Act/CARO qualification is established.",
      "shared": "Strengthen assertion-to-risk-to-procedure-to-evidence-to-conclusion traceability; confirmations, subsequent events, going concern, component work, estimates and management representations. Full-population analytics do not replace sufficient appropriate evidence.",
      "UAE": "Select framework and audit requirements by legal form, licensing authority, mainland/free zone, regulated status and group. Assess CT audited-statement obligations separately: MD84/2025 addresses >AED50m non-tax-group persons, QFZPs and tax-group special-purpose statements, with period transition. Free-zone company audit requirements are not identical to CT requirements.",
      "India": "Build Companies Act applicability, CARO2020, IFC applicability, Schedule III division, AS/Ind AS reporting and related-party disclosures as separate qualified modules. Inventory visits, title evidence, fraud inquiries and approvals require actual evidence. Do not equate IFRS output with Ind AS compliance.",
      "acceptance": "Exemption test cases; no CARO for UAE engagement; correct report version/period; unresolved clauses cannot be masked by an overall Completed label; opinion issuance requires authorized professional approval and current evidence.",
      "current": {
        "id": "08",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Audit execution, retained evidence/workpapers, reviewed requirements, confirmations, cutoff, inventory/asset procedures and source-linked draft reporting.",
        "UAE": "Country/framework binding and CT audit-obligation checks remain separate from licensing/free-zone/sector audit requirements.",
        "India": "Schedule III/reporting foundations and form/applicability controls exist; India clauses are not reused as UAE requirements.",
        "remaining": "Complete qualified Companies Act/CARO/IFC and UAE authority/sector reporting packs, actual physical/confirmation evidence and authorized professional issuance.",
        "evidence": [
          "backend/app/modules/regulatory/india_reporting.py",
          "backend/app/modules/regulatory/reporting.py",
          "backend/tests/qa_crud/test_statutory_reporting.py",
          "backend/tests/qa_crud/test_report_requirements.py"
        ]
      }
    },
    {
      "title": "09 · SOX and internal controls",
      "url": "https://coraa.ai/use-cases/sox-compliance-internal-controls",
      "scope": "Shared",
      "phase": "P2 / P6",
      "reference": "Journal tests, segregation of duties, ITGC evidence, continuous monitoring and controls reporting. Claims about 100% coverage describe analytics over supplied data, not all control assertions.",
      "baseline": "PARTIAL existing GRC risk/control matrices, tests, SoD, remediation and bounded deterministic monitoring. Live enterprise access/event connectors and full standards qualification remain gaps.",
      "shared": "Extend process/control/assertion ownership, design vs operating effectiveness, population completeness, frequency/sample rationale, deficiency evaluation, compensating controls, retesting and management certification. Ingest user-role assignments, permissions, privileged changes and workflow approvals; GL alone cannot test SoD/ITGC.",
      "UAE": "Provide UAE internal controls/ICFR methodology by entity/regulator. Enable SOX only for an applicable issuer, group reporting instruction or contractual scope, not because the client selects UAE.",
      "India": "Provide Indian IFC/ICFR scope using applicable Companies Act requirements. Enable SOX separately when applicable to issuer/group; it is not the Indian default. Assess sector requirements independently.",
      "acceptance": "Known conflicting access creates explainable findings; revoked access and compensating controls retain history; failed connector means incomplete monitoring; SOX404(a) and auditor404(b) applicability stay separate; no claim that analytics removes all sampling or proves control effectiveness.",
      "current": {
        "id": "09",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "GRC risk/control/testing foundations plus retained SoD permission/assignment populations, reviewed policy, interval checks, paging, reporting and historical evidence.",
        "UAE": "Common control review can be scoped to the entity; SOX remains an issuer/group/contractual overlay rather than a UAE default.",
        "India": "Common control and SoD review can be scoped to IFC/ICFR or SOX as actually applicable; a country selection does not decide legal applicability.",
        "remaining": "Authorized live enterprise-access/event connectors, complete framework-specific methods and professional design/operating-effectiveness conclusions.",
        "evidence": [
          "backend/app/modules/grc/service.py",
          "backend/tests/qa_crud/test_sod_reporting.py",
          "frontend/tests/sod-results.test.tsx"
        ]
      }
    },
    {
      "title": "10 · Nonprofit / implementing-partner due diligence",
      "url": "https://coraa.ai/use-cases/nonprofit-due-diligence",
      "scope": "Shared",
      "phase": "P6",
      "reference": "Legal eligibility, financial health, governance and reputation, ending with human-validated assurance. A professional validator network and optional insurance are service dependencies, not features software can manufacture.",
      "baseline": "MISSING specialized diligence case model and licensed screening/registry adapters. Reuse client/evidence/review/report infrastructure and source-linked financial analysis.",
      "shared": "Add entity and ownership identity, document validity/expiry, grant restrictions, utilization, related-party conflicts, board/governance evidence, adverse-media references, risk rationale and periodic revalidation. Separate document authenticity, registry verification and professional attestation.",
      "UAE": "Check authorized legal form, charity/fundraising permissions, relevant federal/emirate authority, grant restrictions and sanctions. India CSR-1/80G/FCRA labels have no UAE default equivalent. Public-benefit CT exemption is a separate applicability assessment.",
      "India": "Assess CSR implementing-agency eligibility, CSR-1, applicable 12AB/80G status, FCRA only when relevant, audited accounts/10B/10BB, utilization and governance. Registry availability and access vary; a user-uploaded certificate is not a live registry verification.",
      "acceptance": "Expired or unavailable registry evidence yields pending, not verified; adverse-media identity collisions require review; every risk grade has rationale and sources; only authorized qualified humans sign attestation; insurance is excluded unless separately contracted.",
      "current": {
        "id": "10",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "Diligence subjects, document validity, ownership look-through, uploaded-list screening, adverse-media adjudication and grant mandate/utilisation controls.",
        "UAE": "Uses explicit country/date policy and retained mandate, identity, ownership and governance evidence; no live registry or professional attestation is inferred.",
        "India": "Reuses the same controls with separately assessed legal/grant context; uploaded evidence does not establish registration authenticity or eligibility.",
        "remaining": "Licensed live registry/PEP/sanctions services, qualified local legal requirements, professional validators, consented partner pilots and any insurance/service arrangement.",
        "evidence": [
          "backend/app/modules/country_workflows/diligence_schemas.py",
          "backend/app/modules/country_workflows/grant_utilisation.py",
          "backend/tests/qa_crud/test_ownership_paths.py",
          "backend/tests/qa_crud/test_screening_candidates.py"
        ]
      }
    },
    {
      "title": "11 · Vendor due diligence",
      "url": "https://coraa.ai/use-cases/vendor-due-diligence",
      "scope": "Shared",
      "phase": "P6",
      "reference": "Identity/ownership, financial and compliance review, sanctions/PEP/media and recurring validation. Do not assume public access to every beneficial-ownership database named in marketing.",
      "baseline": "MISSING end-to-end vendor risk product; reusable party data, evidence, tax IDs, analysis, findings and approvals exist. Public/paid registry and screening access is an external dependency.",
      "shared": "Introduce vendor legal entities, beneficial-owner relationships, identifier verification, bank-account ownership evidence, conflict declarations, financial metrics, watchlist matches, service criticality and revalidation schedules. Add explainable risk dimensions and documented procurement disposition.",
      "UAE": "Trade licence and issuing authority, TRN verification where applicable, ownership/UBO evidence, sanctions and local regulator requirements. Assess free-zone registry availability individually. Use licensed screening feeds where needed.",
      "India": "CIN/LLPIN/PAN/GSTIN and applicable ownership, tax/filing history, MSME status with evidence and effective dates. Separate invalid tax registration from insolvency, sanctions and procurement policy risk.",
      "acceptance": "Name-only sanctions hits never auto-reject a vendor; unavailable registry is not a clean result; changed bank details require controlled review; source licence and query timestamp retained; recurring review is off until explicitly configured.",
      "current": {
        "id": "11",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "Vendor identity/diligence, ownership and conflicts, uploaded-list screening, adverse-media evidence and separate procurement/payment controls.",
        "UAE": "UAE entity/policy scope is retained; unsupported or unavailable external searches remain unresolved evidence.",
        "India": "India entity/policy scope is retained; registry/tax registration authenticity is not inferred from document syntax or uploaded declarations. India supplier-payment review additionally supports source-assessed micro/small eligibility and acceptance-based due dates with retained document dependencies.",
        "remaining": "Authorized provider integrations, complete country diligence criteria and independently checked vendor cases; software cannot manufacture authenticity or professional attestation.",
        "evidence": [
          "backend/app/modules/country_workflows/adverse_media.py",
          "backend/app/modules/country_workflows/ownership_paths.py",
          "backend/tests/qa_crud/test_ownership_paths.py",
          "backend/tests/qa_crud/test_screening_candidates.py"
        ]
      }
    },
    {
      "title": "12 · Stock / inventory audit",
      "url": "https://coraa.ai/solutions/stock-audit",
      "scope": "Shared",
      "phase": "P5",
      "reference": "The reference is explicitly ledger-side preparation: closing inventory, prior-year/gross-margin analysis, count coverage, cutoff/obsolescence/third-party prompts. Physical verification and bank drawing-power calculations are excluded.",
      "baseline": "PARTIAL generic inventory reconciliation designation and IFRS/audit workpapers; no verified item/site count, condition or valuation workflow established by the reviewed code.",
      "shared": "Add SKU/site/lot/UOM master, stock rollforward, physical count sheets, count date and movements to reporting date, test counts, ownership/consignment and third-party confirmations. Distinguish count quantity, monetary coverage and evidence completeness; test cost and NRV with supporting sales/purchase data.",
      "UAE": "Use approved IFRS/other applicable framework and inventory audit methodology. Treat customs/designated-zone facts as tax inputs, not proof of title. Add Arabic document extraction qualification.",
      "India": "Select AS2 or IndAS2 independently; map evidence to SA501 and applicable CARO inventory reporting. If lender stock audit/drawing power is later requested, build a separately specified mandate using sanctioned margins, eligible receivables and lender rules.",
      "acceptance": "Count coverage denominator disclosed; absence of inventory is separately evidenced; movement from count date reconciles; quantities cannot be summed across incompatible UOMs; third-party stock not silently included; no claim that GL analytics verifies existence or condition.",
      "current": {
        "id": "12",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Stock quantities/site/UOM, controlled count-date movement bridge, custody confirmations, cost/NRV evidence, GL valuation controls and missing monetary coverage.",
        "UAE": "Shared stock procedures use explicit ownership/custody, framework and valuation evidence; no physical attendance or automatic customs ownership conclusion.",
        "India": "The same controlled quantities and valuation procedures support separately assessed audit/tax requirements; local statutory disclosures remain country-pack work.",
        "remaining": "Actual count attendance, title/condition/third-party evidence, industry-specific valuation methods and representative client qualification.",
        "evidence": [
          "backend/app/modules/country_workflows/inventory_valuation.py",
          "backend/app/modules/country_workflows/inventory_custody.py",
          "backend/tests/qa_crud/test_inventory_controlled_bridge.py",
          "backend/tests/unit/test_inventory_valuation.py"
        ]
      }
    },
    {
      "title": "13 · Payroll audit",
      "url": "https://coraa.ai/use-cases/payroll-audit-pf-esi",
      "scope": "Shared",
      "phase": "P2 / P4",
      "reference": "Whole-register salary tests, statutory reconciliation, joiners/leavers, benefits, accruals and unusual entries. The page’s PF membership threshold wording is misleading: eligibility is not a simple greater-than-₹15,000 rule.",
      "baseline": "MISSING qualified employee-level payroll engines. Reuse generic matching, journal tests, confidential evidence, workpapers and review. A generic payroll reconciliation option is not a payroll compliance engine.",
      "shared": "Employee-employment-contract history, pay components, leave/attendance, payroll runs, amendments, joiner/leaver calculations, approved master changes and bank settlements. Add duplicate employee/bank checks, unexpected adjustments, benefits and GL-to-payroll-to-bank bridge. Restrict employee data by role.",
      "UAE": "Prioritize payroll register → WPS/SIF → bank → GL. Assess MOHRE/WPS applicability and exclusions with effective-dated Resolution340/2026 rather than hardcoding 2022 rules. Add gratuity/end-of-service, leave and pension authority/cohort checks; DIFC/ADGM/other special regimes need distinct packs and applicable benefit schemes.",
      "India": "Prioritize payroll → ECR/ESIC → challans → bank/GL, salary withholding/24Q/Form16 historical and current successor formats. Membership continuity, excluded employees, pension eligibility, wage definitions, state PT, bonus/gratuity and salary-tax elections need versioned facts. EPFO guidance says existing membership may continue above the ceiling; never infer membership from salary alone.",
      "acceptance": "Joiners/leavers and arrears reconcile by employee and month; no double-booking corrected payroll; correct pension/membership cohort; UAE employee never gets PF/PT by default; sensitive fields stay out of unrelated audit exports; timing failures retain actual payment evidence.",
      "current": {
        "id": "13",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Payroll accrual/posting controls, employee/channel settlement, contributions, assessed expected remittances and split payment allocation with retained rule/source lineage.",
        "UAE": "WPS, pension/cohort and benefit reviews remain separate purpose-bound workflows with independently reviewed published rule profiles and supporting evidence. Reviewed constant-model full-time/part-time gratuity now bridges to independently controlled expected settlements, with typed employment-service scopes and independent HR/bank allocation evidence; rule or supporting-context replacement stales dependent approvals.",
        "India": "PF/EPS/ESI/PT assessed component calculations, ECR/ESIC member/day/wage population checks and payroll-to-GL controls are implemented.",
        "remaining": "Complete legal cohort/state/schema qualification, representative payroll clients, statutory charges not covered by current formulas and actual filing/payment execution.",
        "evidence": [
          "backend/app/modules/country_workflows/payroll_ledger_schemas.py",
          "backend/tests/qa_crud/test_payroll_ledger.py",
          "backend/tests/qa_crud/test_published_pension_source.py",
          "backend/tests/qa_crud/test_published_payroll_source.py",
          "backend/app/modules/country_workflows/benefit_settlement_source.py",
          "docs/country-workflows/benefit-settlement.md",
          "docs/phase-12/benefit-settlement-validation.json",
          "docs/phase-12/gratuity-browser-b315b53.json"
        ]
      }
    }
  ],
  "sections": [
    [
      "Decision and evidence boundary",
      [
        "Yes: all 13 business needs are addressable through one global platform, seven reusable engines and jurisdiction packs. They are not 13 independent products. Delivering every legal conclusion, registry lookup or attestation also requires qualified content, access rights and professional review. No claim of current complete parity is justified.",
        "Review date: 24 October 2026. All 13 supplied public pages were read. Four distinct embedded product image assets were visually inspected. No competitor authenticated workflow, output correctness, performance or production capability was tested. Several pages are marketing use cases rather than evidenced client case studies.",
        "TheAuditor assessment is a static review of current source and repository reports, including uncommitted work. No application tests were run for this planning-only task. Existing test receipts are historical evidence, not fresh certification. The working tree already contains substantial concurrent changes; this delivery changes planning artifacts only.",
        "Shared engines: ingestion/normalization; reconciliation and balance bridges; effective-dated obligations and calculations; audit procedures/controls; party/employee/inventory subledgers; evidence/review/lineage; report composition and client collaboration. Use dedicated domain tables for operational populations; reuse append-only evidence events for receipts and reviews."
      ]
    ],
    [
      "Screenshot review and product lessons",
      [
        "Form 3CD image: 44 total clauses, 3 active, 32 pending review, 9 entries; overall Completed appears alongside outstanding review. Adopt the clause navigation and embedded reconciliation idea, but distinguish calculation complete from professionally reviewed and issued. Never interpret counts as evidence of all clauses being automated.",
        "Image routing mismatch: both TCS and bank pages resolve to 14-form-3cd-all-clauses.png; GST resolves to 15-form-3cd-tds-recon.png. Therefore those heroes do not visually substantiate TCS, bank or GST workflows. Keep the written requirements, downgrade the screenshot evidence.",
        "TDS image: shows a missing 26AS upload, one books-only entry, separate vendor/section/books-only tabs and four buckets. Adopt visible source-readiness and unmatched amounts. Do not display a missing portal population as zero matched evidence or successful completion.",
        "TDS deductee drill: voucher date/reference/gross/tax/net and a clearly missing TAN block. Adopt two-sided drilldown and explicit missing identifiers. A materiality tolerance is not legal permission to under-deduct tax, so tax rounding and investigation tolerances must be separate.",
        "CARO image: manual vs auto rows and Yes/No/N/A answers are useful; zero of 21 addressed confirms that generated scaffolding is not completed audit evidence. The text claims 17 auto-drafted plus 5 manual against 21 clauses: clarify overlapping counts rather than reproduce them.",
        "No dedicated in-product hero screenshot was present in the retrieved main content of PF/ESI/PT, combined GST/tax audit, SOX, nonprofit diligence, vendor diligence, stock or payroll pages. Those were assessed from text; no invisible UI capability is inferred."
      ]
    ],
    [
      "Country-rule architecture: extend the existing foundation",
      [
        "Preserve the existing immutable engagement country-package binding and working-paper dependency receipts. Regulatory RuleVersion/RuleAction code already exists in the working tree; extend and qualify it rather than starting a parallel rule service. Keep legal rule version, calculation implementation, parser schema and report template versions independently pinned.",
        "Select obligations using legal-entity country + registrations/branches + tax nexus + transaction/supply country + employee employment regime + issuer/group requirements + effective period. User-selected working country is a browsing preference, not a legal applicability decision. A UAE parent and Indian subsidiary retain separate entity packs and group reporting overlays.",
        "Precedence: authoritative applicable law and approved interpretations; local/regulator/subnational pack; applicable standard and entity framework; group instructions; firm policy. Firm materiality and matching tolerances cannot override statutory thresholds. Conflicting rules stop the legal conclusion and request review.",
        "Rule schema: stable key; jurisdiction/subjurisdiction/regulator; obligation type; authoritative citation and retained source hash; publication/retrieval dates; effective-from/to; relevant date basis; entity/cohort predicates; exemptions/elections; formula/threshold bands/currency/rounding; required inputs; output/report mapping; reviewer and approval; supersession relation; content/engine/test versions.",
        "Use both legal validity time and knowledge/publication time. A backdated amendment creates a new rule version and an impact assessment; it does not rewrite old approved workpapers. A period spanning rule changes may need transaction-level selection. No date match, overlapping unresolved versions or missing facts yields PENDING/UNSUPPORTED, not compliant.",
        "Current declarative evaluator supports bounded predicates and a flat-rate method. Extend with reviewed typed implementations for cumulative thresholds, slabs, wage ceilings, carryforwards, arrears, due-date calendars and elections. Never execute uploaded expressions or trust AI-created law. Retain Decimal arithmetic and explicit rule rounding.",
        "Model each result with applicability status, data completeness, machine calculation, reviewer conclusion and issuance status separately. Track source counts/totals by registration/account/month, missing partitions, errored refreshes and source supersession. Failed imports cannot overwrite a last-known-good approved source.",
        "Rule lifecycle: draft → source verification → independent legal/professional review → fixture validation → published → superseded/withdrawn. Record impacted entities and workpapers; upgrade engagements only through an approved append-only transition. A country profile or menu registration never means a qualified operational engine."
      ]
    ],
    [
      "UAE-first release scope",
      [
        "UAE MVP: bank BRS; VAT register-to-VAT201/customs reconciliation; payroll-to-WPS/bank/GL; source-linked audit workpapers and controlled reporting. Reuse current CT/IFRS/TP engines within their documented scope. Avoid adding India-only forms to the UAE navigation.",
        "UAE second wave: deeper VAT recovery/RCM and amendments; end-of-service and leave tests; pension cohorts; free-zone/regulator audit/report templates; vendor and charitable-partner diligence. Qualify one authority/regime before advertising all free zones.",
        "UAE domestic TCS and Indian PF/ESI/PT are NOT_APPLICABLE, not missing UAE features. Current CT withholding at 0% is distinct from foreign-source withholding. Preserve extension points for rate changes and cross-border evidence.",
        "Emirate, licensing authority, mainland/free-zone, designated-zone VAT status, QFZP status, pension scheme and employment regime are independent facts. Do not store them as a single free_zone boolean. Include Arabic/English document and date/number-format qualification.",
        "UAE content owners must validate current tax, labour, pension, charity, data protection and industry-specific obligations before release. Residency and retention are tenant/data-category decisions supported by applicable law and contracts; do not infer a universal localization mandate from country selection."
      ]
    ],
    [
      "India release scope",
      [
        "India MVP follows the shared foundation: multi-GSTIN purchase/2B and sales/GSTR-1 reconciliation, source-controlled 3B tie-out and reviewable exceptions. Next add TDS/TCS and payroll statutory dues. Tax-audit orchestration consumes these results later.",
        "Maintain parallel historical and current income-tax law/form packs. Official Income Tax guidance distinguishes FY2025–26 legacy 3CA/3CB/3CD from TaxYear2026–27 Form26 under the new rules. Do not reuse section numbers, form names or deadlines across regimes without an approved crosswalk.",
        "State packs: PT, labour/welfare obligations and local calendars only where applicable. Employee membership and registration evidence are necessary for PF/ESI; salary and state alone are insufficient. Include establishment coverage and historical continuity.",
        "Corporate reporting packs: Companies Act/CARO/IFC applicability, ScheduleIII division, AS/IndAS basis and sector overlays. Tax audit and Companies Act statutory audit are distinct engagements and opinions even if they share evidence.",
        "GST annual-report/9C applicability and year-specific schemas need qualification. Source conflicts must be resolved using enacted/current materials, not old official tutorials or competitor text. No filing API or automatic submission is included in MVP."
      ]
    ],
    [
      "Roadmap and sequencing — estimates, not delivery commitments",
      [
        "Planning assumption: 2 backend engineers, 2 frontend/full-stack engineers, 1 data/parser engineer, 1 QA engineer, fractional security/operations; named UAE and Indian tax/audit/payroll professionals available throughout. No licensing or portal-access lead time is assumed resolved. Ranges below overlap; they must not be added as independent fixed estimates.",
        "P0 · Weeks1–3 · Evidence baseline and rule qualification. Owner: technical lead + country professionals. Inventory actual routes/engines; catalogue production blockers; select UAE pilot entities and India return years; approve canonical schemas and version precedence. Exit: signed capability matrix, input samples, rule/source inventory and country-negative fixtures. Dependency: access to representative redacted data.",
        "P1 · Weeks3–8 · Shared reconciliation and UAE bank pilot. Owner: data/backend + QA. Add control totals, operational document tables, job idempotency, bank templates, balance bridge, aging and review drilldowns. Exit: independent BRS fixtures and pilot account ties with no unexplained residual. Existing 20k matching bound remains until measured and safely replaced.",
        "P2 · Weeks7–14 · UAE VAT/payroll/audit-close pilot. Owner: UAE product team + professional lead. Ship VAT201 bridges, WPS ingestion/payment reconciliation, report status controls and evidence-linked audit/controls templates. Exit: reviewed UAE cases across agreed scope, legal-version receipts and authorized exports. Reuse GRC; do not promise complete SOX yet.",
        "P3 · Weeks11–19 · India GST. Owner: India tax/data team. Build versioned GSTR adapters, multi-GSTIN controls, invoice/note matching, amendments, RCM/IMS/cess and annual reconciliation draft bridge. Exit: representative GSTIN-period fixtures with independent expected results; unrecoverable/timing/format errors classified separately.",
        "P4 · Weeks17–25 · India withholding and payroll. Owner: India tax/payroll lead + engineers. Build separate TDS/TCS roles, certificates/returns/challans, PF/ESI/state PT and payroll-source bridges. Exit: historical/current period selection, membership/threshold boundaries, corrected returns and partial settlements validated.",
        "P5 · Weeks22–31 · Tax audit, statutory packs and stock evidence. Owner: audit/reporting team. Implement legacy/new tax-audit templates and clause graph, CARO/IFC/applicability, inventory quantity/valuation workpapers and country report publishing. Exit: each mandatory report item traced, reviewed and blocked on missing prerequisites; professional export schema review.",
        "P6 · Weeks28–38 · Vendor/nonprofit diligence and enterprise controls. Owner: diligence/GRC lead. Integrate authorized registry/screening providers, scheduled revalidation, access/event connectors, deficiency workflow and regime-qualified report templates. Exit: licensed access, identity collision tests, unavailable-source behavior, practitioner sign-off and privacy review.",
        "P7 · Weeks35–42+ · Hardening and controlled rollout. Owner: QA/security/operations and country leads. Complete real-data pilot reconciliation, concurrency/large-population benchmarks, tenant isolation, recovery, accessibility, observability and professional scope qualification. Exit: close existing release blockers plus new module gates; release UAE/India capabilities independently.",
        "Expected horizon with the assumed team: useful UAE pilot in roughly10–14 weeks; broad UAE+India controlled coverage in roughly9–12 months. Full all-sector/all-state/all-authority coverage is an ongoing content program. Smaller staffing or missing legal/data access extends the plan; no empirical velocity estimate is claimed."
      ]
    ],
    [
      "Implementation backlog and API contracts",
      [
        "Data model: source_document + document_version; import_partition + control_total; tax_registration; bank_account + statement + statement_line; canonical_tax_document + line + note_link; employee + employment_history + payroll_run; statutory_obligation + return + payment_allocation; inventory_item + movement + count; party_relationship + verification_case; rule_release + applicability_result; reconciliation_run + match_group + exception + disposition. Use existing tenant scoping, engagement scope and private-object references.",
        "APIs should reuse current run/job conventions: validate import → preview controls → commit immutable source → calculate against pinned inputs → propose matches → review/dispose → publish working paper. Expose cursor pagination, resumable jobs, explicit source versions and idempotency keys. New legal rules and professional decisions remain independently authorized.",
        "Source contracts must capture actual format version, account/registration/period coverage, row count and debit/credit/tax totals, parser warnings and source hash. XLSX/JSON/CSV first where schemas are reliable; PDF requires real format fixtures; scanned PDF and Arabic/Indian-language OCR are separately qualified.",
        "Connector strategy: uploaded official exports first; ERP adapters second; authorized portal/provider integrations third. Existing Tally/Zoho code is useful but is not proof that tax, payroll, inventory or access-log fields are available. Verify source report semantics and populations. No CAPTCHA bypass or assumption of unrestricted registry APIs.",
        "AI may classify document candidates, propose mappings, draft evidence-linked narratives and summarize exceptions. Deterministic engines perform tax arithmetic and reconciliation; humans resolve uncertain applicability and sign professional reports. Record prompt/model/source receipts for material AI-generated drafts.",
        "Product UI: country/obligation scope bar; source-readiness panel; tabs for books-only and independent-source checks; match buckets; two-sided drill with original evidence; cause/disposition/assignee/due date; version and freshness indicators; linked report destination. Show not applicable, unsupported, missing evidence and genuine zero as different states."
      ]
    ],
    [
      "Acceptance, release gates and operating model",
      [
        "Financial correctness: independently computed golden fixtures for each declared parser/rule version. Test threshold−1/threshold/threshold+1 in minor currency units, effective-date boundaries, negative values, notes, amendments, partial payments, holidays, leap days and period changes. Re-running identical pinned inputs must yield identical result hashes.",
        "Reconciliation invariants: all source rows represented once; no uncontrolled many-to-many netting; amounts conserved across match groups and residuals; tax components/registrations/currencies not silently mixed. Distinguish 100% of imported rows processed from population completeness and audit assurance.",
        "Country isolation: India-only rules cannot run against UAE domestic obligations; foreign obligations require explicit scope. Test a UAE parent/India subsidiary, multiple GSTINs, multiple UAE licences, tax/VAT groups and employee regime changes. Unsupported countries remain shared-core only until a published pack qualifies them.",
        "Professional controls: preparer cannot approve own material conclusions; source changes mark dependents stale; issue/export gates reject missing mandatory evidence, unresolved applicability and stale inputs. Preserve manual overrides with reason, author, date and original machine result.",
        "Security/operations: tenant and engagement authorization, employee/UBO least privilege, object quarantine and scanning, encrypted private storage, job restart/idempotency, audit logs and retention. Qualify production recovery, incident response and monitoring. Existing repository NO-GO reports remain unresolved unless new evidence closes them.",
        "Pilot sequence: UAE service company and trading/importer with agreed free-zone scope; India service/manufacturing clients with multiple GSTINs, corrected returns and mixed payroll cohorts. Use consented/redacted data and independent expected schedules. Suggested target: 3–5 UAE and 3–5 India pilot engagements, adjusted for representative coverage.",
        "Metrics: source completeness, independently measured extraction accuracy by document type/field, match precision/false matches, unresolved monetary residual, exception aging, reviewer override rates, time per engagement and reproducibility. Set numeric release thresholds after baseline measurement; do not inherit competitor time-saving percentages.",
        "Operating model: country content owner, independent approving professional, parser owner, release owner and security owner. Track source updates, affected rules and affected open engagements. Maintain a source ledger with retrieved/verified/approved states. Any later-country launch repeats this process rather than enabling a menu flag."
      ]
    ],
    [
      "Later-country expansion policy",
      [
        "All countries may use qualified common audit/reconciliation workflows with explicit entity frameworks. Local tax/payroll/statutory modules remain unsupported until separately published. Do not advertise worldwide legal compliance from ISO-country selection.",
        "Candidate sequence after UAE/India: Saudi Arabia, then selected Singapore/UK markets, then US according to demand and professional/data access. This is a commercial sequencing proposal only, not a researched legal-coverage claim. Saudi tax/e-invoicing, UK tax/payroll, Singapore tax/payroll and US federal/state controls each need separate discovery and effective-dated packs.",
        "SOX is an issuer/group overlay that can apply across countries, not a country synonym. International standards likewise require actual framework adoption and engagement scope. Add a new country only after authoritative research, rule qualification, local representative data and release sign-off."
      ]
    ]
  ],
  "sources": [
    [
      "India tax-audit form transition — Income Tax Department",
      "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/income-tax-forms?mobile-app=1"
    ],
    [
      "TCS1H withdrawal — Finance Act2025 amendment, official section72",
      "https://www.incometaxindia.gov.in/w/section-72-94"
    ],
    [
      "EPFO membership FAQ — official",
      "https://www.epfindia.nic.in/site_hi/FAQ.php"
    ],
    [
      "UAE MD84/2025 audited financial statements — MoF",
      "https://www.mof.gov.ae/wp-content/uploads/2025/04/Ministerial-Decision-No.-84-of-2025-on-Audited-Financial-Statements.pdf"
    ],
    [
      "UAE WPS and Resolution340/2026 — official government",
      "https://u.ae/en/information-and-services/jobs/employment-in-the-private-sector/payment-of-wages"
    ],
    [
      "UAE VAT returns guide — FTA",
      "https://tax.gov.ae/-/media/Files/EN/PDF/Guides/VAT-Returns-User-Guide.pdf"
    ],
    [
      "UAE withholding tax FAQ — FTA",
      "https://tax.gov.ae/en/faq.aspx?keyword=Does+the+UAE+CT+regime+have+withholding+tax%3F"
    ],
    [
      "UAE Federal Donations Law — official legislation",
      "https://www.uaelegislation.gov.ae/en/legislations/1500"
    ],
    [
      "GST9C self-certification change — GST Council material",
      "https://gstcouncil.gov.in/node/3908"
    ],
    [
      "SOX404(a)/(b) distinctions — SEC Financial Reporting Manual",
      "https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual/frm-topic-10"
    ]
  ],
  "evidence": [
    "backend/app/modules/intelligence/service.py: statutory adapter rejection, CSV source-table support and source receipts",
    "backend/app/modules/intelligence/matching.py: deterministic matching and 20,000-row bound",
    "backend/app/modules/jurisdictions/packages.py and profiles.py: country package/context and readiness metadata",
    "backend/app/modules/regulatory/evaluation.py and models.py: bounded rule evaluation and version/action records; uncommitted work",
    "backend/app/modules/regulatory/india_reporting.py: source-reconciled ScheduleIII drafts with explicit limitations; uncommitted work",
    "backend/app/modules/vat/ and tax/: existing bounded UAE workbenches",
    "docs/global-platform/README.md: immutable bindings, freshness and country capability boundaries",
    "docs/phase3/baseline-and-gap-analysis.md: existing gaps and source retrieval limitations; work in progress",
    "docs/phase-12/production-readiness.md and README.md: historical release NO-GO and later QA caveats"
  ],
  "checkpoint": {
    "as_of": "29 October 2026",
    "source_revision": "9ba08d4920c598b1137761180e246858a71d1e1f",
    "release_status": "NOT_QUALIFIED_FOR_PRODUCTION_STATUTORY_USE",
    "scope": "Operational implementation and bounded synthetic verification through 9ba08d4. UAE-first processor reserve continuity now reuses reviewed merchant settlements, checks separate dated holds/releases and independent opening/closing balances, then exact receivable GL controls; the same workflow supports India in original currency with country-specific processor tax labels. It blocks omitted offsetting components, interim overdrafts and cross-merchant pooling and preserves complete XLSX movement details. Local proof: 3,203 backend units, four focused API workflows, 307 frontend tests, production build/types/lint and mypy passed. Current hosted browser, frontend, security, ML and containers passed. All three browser cases passed in 1.7m; four exact UAE/India reserve images were downloaded, digest verified and individually inspected. Full current hosted backend remains running and is not claimed as passing. Prior b315b53 complete hosted proof remains historical and does not verify new code. Legal/native/provider/client and production qualification remain open.",
    "verification": [
      {
        "label": "Backend units",
        "result": "3,203 passed; five skipped",
        "path": "docs/phase-12/merchant-reserve-backend.xml",
        "limit": "Includes 33 new reserve tests alongside all 154 authored scenarios and prior annual-statement/gratuity/merchant controls. Covers gross completeness, exact opening/closing, dated availability, shared-GL merchant isolation and complete 401-movement export. Skipped infrastructure checks and independent-client/legal qualification remain separate."
      },
      {
        "label": "Focused database regressions",
        "result": "Four passed",
        "path": "docs/phase-12/merchant-reserve-api.xml",
        "limit": "Two new UAE/India reserve workflows plus two existing merchant workflows. Real HTTP/database/storage/job processing verifies independent review, exact XLSX and GL-review withdrawal staleness with unchanged saved rows. Scanner/dispatch are explicit doubles; not all APIs or actual providers."
      },
      {
        "label": "Prior complete hosted backend",
        "result": "4,069 passed; nine skipped; overall coverage 86.21%, core 89.35%",
        "path": "docs/phase-12/b315b53-hosted-verification.json",
        "limit": "Complete original JUnit/coverage archived for b315b53, before reserve code. This remains historical; the current 9ba08d4 full backend run is in progress and must be observed separately. Neither suite establishes actual clients, providers, a complete legal corpus or production deployment."
      },
      {
        "label": "Frontend",
        "result": "307 tests across 65 files passed; production build, TypeScript and lint passed",
        "path": "docs/phase-12/merchant-reserve-validation.json",
        "limit": "Local current-source proof includes blank independent reserve controls, distinct held/released versus opening/closing payloads, explicit zeros and reset on source-type changes. One pre-existing unused-variable warning remains in uae-business-cases.tsx. Both hosted frontend jobs also passed on this source; exact 307 tests/65 files and production build confirmed from terminal logs."
      },
      {
        "label": "Current reserve browser proof",
        "result": "All three cases passed on 9ba08d4 in 1.7m; four original UAE/India reserve images inspected",
        "path": "docs/phase-12/merchant-reserve-browser-9ba08d4.json",
        "limit": "Both country cases reuse the original reviewed processor source and verify UI reserve calculation, independent final review, complete XLSX, withdrawn-GL staleness and whole saved-body equality. API source setup/reviews use real scanner/broker/worker. Exact images show separate 100/145 balances, 50/5 movements, three matched rows and STALE/disabled approval. Collapsed provenance is not a visual proof of dated movement detail. Synthetic mechanics, not independent clients or all 154 scenarios."
      }
    ],
    "hosted_runs": [
      {
        "label": "Current reserve source CI",
        "url": "https://github.com/indianservers/MrAuditorUAE/actions/runs/40879567200",
        "status_at_checkpoint": "9ba08d4: browser-smoke, frontend, security, ML and containers passed; verify/full backend observed in progress. Three browser cases passed in 1.7m and four original reserve images individually inspected. Separate Frontend checks run 40879567139 passed with 307 tests/65 files and production build. Full backend pending is not a pass."
      },
      {
        "label": "Prior complete application backend proof",
        "url": "https://github.com/indianservers/MrAuditorUAE/actions/runs/40747196323/job/123024022320",
        "status_at_checkpoint": "PASSED on b315b53: 4,069 passed, nine skipped, 86.21% overall and 89.35% core coverage. All six jobs passed on this source. Exact JUnit and coverage retained; Subsequent reserve changes in 9ba08d4 contain application code and require separate proof."
      },
      {
        "label": "Prior linked-account merchant browser and CI",
        "url": "https://github.com/indianservers/MrAuditorUAE/actions/runs/40733634486/job/122976244121",
        "status_at_checkpoint": "Browser, frontend, security, ML and containers PASSED on e119982. Three cases include linked merchant UI selection, approval, XLSX and linked-review withdrawal staleness in both countries alongside existing native-bank/MSE flows. Four exact linked-merchant screenshots individually inspected."
      },
      {
        "label": "Prior gratuity bridge browser and CI",
        "url": "https://github.com/indianservers/MrAuditorUAE/actions/runs/40747196323/job/123024022741",
        "status_at_checkpoint": "All six jobs PASSED on b315b53: full backend 4,069 passed/nine skipped, all three browser cases in 1.3m with three original gratuity images individually inspected, frontend 302/build/types/lint, security, ML and containers. This is bounded synthetic/application proof, not independent client or professional qualification."
      }
    ],
    "open_gates": [
      {
        "priority": "UAE first",
        "work": "Qualify representative bank/PDF, VAT201/customs and WPS inputs, employment/pension cohorts and complete reporting obligations against retained authoritative versions and independently checked schedules. Qualify merchant processor file layouts and independently checked component/reserve schedules; canonical gross-to-net arithmetic alone does not establish these.",
        "proof": "Approved country/rule/parser versions, boundary fixtures and independent expected results for every claimed cohort and layout."
      },
      {
        "priority": "India second",
        "work": "Complete native withholding-return/26AS/168/AIS formats, state/cohort payroll packs and legacy/current tax-audit clause mappings. Declared annual-statement period/form guards are implemented, not native portal readers. Complete MSE tax-deduction, statutory-interest and disclosure procedures with qualified legal versions and independent schedules.",
        "proof": "Source-bound applicable form/rule versions, exact clause coverage, representative amendments and professional approval."
      },
      {
        "priority": "Shared integrations",
        "work": "Qualify authorized registry, sanctions/PEP and enterprise-access providers. Uploaded documents/lists and declared access populations do not establish live external verification.",
        "proof": "Authorized provider connectivity, completeness/error handling, licensing scope and measured representative inputs."
      },
      {
        "priority": "Client pilots",
        "work": "Populate the UAE and India pilot folders with consented redacted inputs and independently checked results. Folders and templates exist; no real-client result is claimed.",
        "proof": "Representative pilot manifests, original hashes, independent expected schedules and reviewer records."
      },
      {
        "priority": "Release",
        "work": "Qualify actual production deployment/rollback, recovery, monitoring, privacy and professional sign-off. All six jobs passed on prior b315b53 with exact JUnit/coverage and browser images retained. Current reserve changes in 9ba08d4 have local tests/build and five hosted job passes including browser and containers; full current backend verification is still running. Synthetic CI mechanics do not close real-client or production gates.",
        "proof": "Passing source-pinned jobs plus actual provider/runtime drills and named approvals. Local/container checks alone do not prove production readiness."
      }
    ],
    "cases": [
      {
        "id": "01",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Separate deductor/deductee and collector/collectee evidence, assessed rule/certificate references, pooled certificate limits, amendments/status and settlement linkage.",
        "UAE": "India TCS is unavailable for domestic UAE obligations. Use the common evidence/settlement foundations under an explicitly applicable obligation.",
        "India": "Withholding liability and credit workflows now accept controlled assessed TCS populations; historical 1H date guards and role isolation are implemented. Declared annual-credit statement headers now separate historical Form 26AS assessment years from Form 168 tax years, with PAN/period/snapshot consistency and scope retained in result/UI/XLSX.",
        "remaining": "Native 27EQ/current-successor, 26AS/168/AIS/TRACES completeness, full legal rate/threshold/certificate corpus and representative client qualification.",
        "evidence": [
          "backend/app/modules/country_workflows/withholding_schemas.py",
          "backend/app/modules/country_workflows/withholding_calculations.py",
          "backend/tests/qa_crud/test_withholding_workflows.py",
          "backend/app/modules/country_workflows/annual_tax_statement.py",
          "docs/phase-12/annual-statement-validation.json"
        ]
      },
      {
        "id": "02",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Controlled BRS, account/owner evidence, ambiguity, opening/closing bridge, dates, outstanding carry-forward, subsequent clearance and cross-engagement cash-allocation checks. Retained matched groups now expose protected original transactions through separately paged read-only inspection. Explicit merchant batches now bridge gross sales, separately checked refunds/chargebacks, fees, assessed tax/withholding and reserves to net signed bank allocations. Partial and pooled payouts retain exact links; residuals block approval. Merchant results also retain separately paged booking/value-date provenance, reject reversed/value-date-only settlements and require regeneration of earlier result contracts. Merchant settlement can now retain a current independent account-document review covering the entire selected period, with unchanged originals and recursive withdrawal staleness. Separate processor reserve continuity now checks dated gross holds/releases, position-level available balances, independently controlled opening/closing statements and assessed receivable GL accounts, reusing the original reviewed processor source. Large XLSX populations retain individual movement and balance links; source withdrawal makes results stale.",
        "UAE": "Authorized committed GL plus bounded reviewed CSV/XLSX/PDF and native bank profiles; account/currency scope remains explicit. Hosted browser verifies committed-GL/native-CAMT matching, invalid-closing rejection, independent review, XLSX and replacement staleness. Merchant component arithmetic uses assessed UAE/foreign fee-tax labels without inferring VAT rates or recovery. Reserve continuity uses explicitly selected original currency and exact receivable controls, without claiming bank receipt, reserve ownership or VAT recovery.",
        "India": "Reuses the same reviewed account, statement, identifier/date and residual controls; no cross-account or currency auto-netting. The same merchant arithmetic uses separately assessed India/foreign fee-tax labels without inferring GST or withholding entitlement. The same reserve engine uses independently assessed India processor facts and original currency, without inferring GST/withholding entitlement or FX.",
        "remaining": "Qualify representative bank-specific files and extraction accuracy; supported profiles do not imply every bank or PDF layout. Qualify processor-native layouts, independent client schedules, reserve account classification/recoverability and any cross-workflow cash-reservation integration. Current reserve browser proof passed with four inspected original images; full current hosted regression remains pending.",
        "evidence": [
          "backend/app/modules/country_workflows/bank_accounts.py",
          "backend/app/modules/country_workflows/bank_consumption.py",
          "backend/tests/qa_crud/test_bank_matching_scope.py",
          "backend/tests/qa_crud/test_pdf_bank_tables.py",
          "backend/app/modules/intelligence/bank_matches.py",
          "frontend/src/features/bank-matched-proposals.tsx",
          "backend/tests/qa_crud/test_bank_matched_proposals.py",
          "frontend/e2e/bank-browser-workflow.ts",
          "docs/phase-12/bank-msme-browser-07f61f1.json",
          "backend/app/modules/country_workflows/merchant_settlements.py",
          "backend/tests/unit/test_merchant_settlements.py",
          "backend/tests/qa_crud/test_merchant_settlements.py",
          "frontend/e2e/merchant-browser-workflow.ts",
          "docs/country-workflows/merchant-settlements.md",
          "frontend/src/features/merchant-settlement-details.tsx",
          "frontend/tests/merchant-settlement-details.test.tsx",
          "backend/app/modules/country_workflows/review.py",
          "docs/phase-12/merchant-browser-20ee29a.json",
          "backend/tests/unit/test_merchant_bank_binding.py",
          "backend/tests/qa_crud/test_merchant_bank_binding.py",
          "docs/phase-12/merchant-account-browser-e119982.json",
          "backend/app/modules/country_workflows/merchant_reserves.py",
          "backend/tests/unit/test_merchant_reserves.py",
          "backend/tests/qa_crud/test_merchant_reserves.py",
          "frontend/e2e/merchant-reserve-browser-workflow.ts",
          "docs/country-workflows/merchant-reserves.md",
          "docs/phase-12/merchant-reserve-validation.json",
          "docs/phase-12/merchant-reserve-browser-9ba08d4.json"
        ]
      },
      {
        "id": "03",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Assessed contribution bases/rules, employer and employee component separation, expected obligation derivation and explicit split bank settlement.",
        "UAE": "Separate WPS settlement and reviewed pension/benefit workflows; authority, cohort, eligibility and source documents are explicit.",
        "India": "Monthly/arrear ECR and bounded ESIC population profiles, source-bound payroll rules and distinct PF/EPS/ESI/PT assessments are implemented.",
        "remaining": "Complete qualified state/cohort packs, native challan coverage and representative portal/client files; administration/EDLI and legal deductibility must not be inferred from the current contribution workflow.",
        "evidence": [
          "backend/app/modules/country_workflows/pension_schemas.py",
          "backend/app/modules/country_workflows/payroll_schemas.py",
          "backend/tests/qa_crud/test_india_ecr_source.py",
          "backend/tests/qa_crud/test_payroll_rule_workflow.py"
        ]
      },
      {
        "id": "04",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Versioned controlled tax documents, notes, independent source totals, registration/component/period separation and explicit missing/rejected evidence.",
        "UAE": "VAT201 aggregate-14, emirate-20 and ecommerce-20 comparisons, 72 e-commerce split/summary checks, reviewed book composition and source-bound operational report presets. Receipt-location and qualifying-status assessments are separate.",
        "India": "Bounded GSTR-1 document/summary/series and GSTR-2B profiles, notes/amendments and controlled retrieval parts supplement canonical GST comparisons.",
        "remaining": "Complete portal/schema qualification, legally assessed credit/recovery eligibility, full annual-return scope and authorized filing/action execution.",
        "evidence": [
          "backend/app/modules/country_workflows/gstr1_schemas.py",
          "backend/app/modules/country_workflows/gstr2b_parts.py",
          "backend/tests/qa_crud/test_india_gstr1_source.py",
          "backend/tests/qa_crud/test_india_gstr2b_source.py",
          "backend/tests/qa_crud/test_vat_composition.py",
          "backend/app/modules/country_workflows/vat201_arithmetic.py",
          "backend/app/modules/regulatory/report_packs.py",
          "backend/tests/unit/test_vat_ecommerce.py",
          "backend/tests/qa_crud/test_vat_emirates.py",
          "docs/country-workflows/uae-vat201-ecommerce-source.json"
        ]
      },
      {
        "id": "05",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Distinct expected, withheld, reported, deposited and credit populations; source-bound assessments, pooled certificate controls and separate bank allocations.",
        "UAE": "Indian domestic TDS workflows stay unavailable. Applicable UAE CT/obligation assessments use their own source-linked workbenches.",
        "India": "Controlled deductor/deductee TDS liability/credit reconciliation and derived payment obligations are implemented, with no inferred legal entitlement. Declared annual-credit statement headers now separate historical Form 26AS assessment years from Form 168 tax years, with PAN/period/snapshot consistency and scope retained in result/UI/XLSX.",
        "remaining": "Native 24Q/26Q/27Q and successor forms, complete 26AS/168/AIS/TRACES profiles, current legal rate/threshold rules and professional expected schedules.",
        "evidence": [
          "backend/app/modules/country_workflows/withholding_obligations.py",
          "backend/tests/qa_crud/test_withholding_workflows.py",
          "backend/tests/qa_crud/test_withholding_obligations.py",
          "backend/app/modules/country_workflows/annual_tax_statement.py",
          "docs/phase-12/annual-statement-validation.json"
        ]
      },
      {
        "id": "06",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Declared report requirements, applicability, evidence-backed non-applicability, current-source validation, authorship separation and unsigned generated drafts.",
        "UAE": "Source-linked CT workbench and audited-financial-statement obligation assessment; nonresident scoped revenue requires retained reviewed evidence.",
        "India": "Tax-period-based legacy/current form selection plus a 65-entry Form 26 numbered-item/schedule-group evidence index for report A/B and particulars C/D. Every covered item must match an exact-period/preset/applicability declaration in a current independently reviewed workpaper, with substantive section and protected source links. Assessed micro/small supplier invoice payment timing now retains supplier eligibility, acceptance/objection/written terms and exact split bank allocations; separate context document bytes, current versions and independent contributor review are required.",
        "remaining": "Full independently approved Form 26/legacy 3CD subfields, statutory schedules/calculations and legal mappings; original Form 26 PDF archival/visual/professional qualification and client expected results. The 65-entry structural index is not a completed official tax-audit form or filing. MSE tax deductibility, statutory interest and complete disclosure packs remain separate unimplemented procedures; timing output is not a tax deduction.",
        "evidence": [
          "backend/app/modules/regulatory/tax_forms.py",
          "backend/app/modules/regulatory/report_requirements.py",
          "backend/app/modules/tax/audit_revenue.py",
          "backend/tests/qa_crud/test_tax_audit_scope.py",
          "backend/tests/qa_crud/test_report_requirements.py",
          "backend/app/modules/regulatory/form26_index.py",
          "backend/app/modules/regulatory/workpaper_report_scope.py",
          "frontend/src/features/workpaper-report-scope.tsx",
          "backend/tests/unit/test_workpaper_report_scope.py",
          "backend/app/modules/country_workflows/msme_payments.py",
          "backend/app/modules/country_workflows/msme_evidence.py",
          "backend/tests/qa_crud/test_msme_payments.py",
          "docs/country-workflows/india-msme-source-scope.json"
        ]
      },
      {
        "id": "07",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Tax-close evidence/readiness and exact finding-ID exposure deduplication. Currency/sign and unknown exposure remain distinct; stale sources cannot support current conclusions.",
        "UAE": "Reviewed VAT/CT schedules, exact-layout VAT201 report presets (including e-commerce components), registration-period turnover bridge, committed-GL books and reviewed multi-source composition. Operational agreement does not establish legal completeness.",
        "India": "GST/withholding/payroll evidence joins the same source-linked close. Turnover scope, return and adjustments remain independently reviewed inputs.",
        "remaining": "Qualify complete country obligation/report packs and annual applicability; a reconciled close does not establish legal filing completeness.",
        "evidence": [
          "backend/app/modules/regulatory/exposure_rollup.py",
          "backend/app/modules/country_workflows/turnover_composition.py",
          "backend/tests/qa_crud/test_tax_close_rollup.py",
          "backend/tests/qa_crud/test_turnover_composition.py"
        ]
      },
      {
        "id": "08",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Audit execution, retained evidence/workpapers, reviewed requirements, confirmations, cutoff, inventory/asset procedures and source-linked draft reporting.",
        "UAE": "Country/framework binding and CT audit-obligation checks remain separate from licensing/free-zone/sector audit requirements.",
        "India": "Schedule III/reporting foundations and form/applicability controls exist; India clauses are not reused as UAE requirements.",
        "remaining": "Complete qualified Companies Act/CARO/IFC and UAE authority/sector reporting packs, actual physical/confirmation evidence and authorized professional issuance.",
        "evidence": [
          "backend/app/modules/regulatory/india_reporting.py",
          "backend/app/modules/regulatory/reporting.py",
          "backend/tests/qa_crud/test_statutory_reporting.py",
          "backend/tests/qa_crud/test_report_requirements.py"
        ]
      },
      {
        "id": "09",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "GRC risk/control/testing foundations plus retained SoD permission/assignment populations, reviewed policy, interval checks, paging, reporting and historical evidence.",
        "UAE": "Common control review can be scoped to the entity; SOX remains an issuer/group/contractual overlay rather than a UAE default.",
        "India": "Common control and SoD review can be scoped to IFC/ICFR or SOX as actually applicable; a country selection does not decide legal applicability.",
        "remaining": "Authorized live enterprise-access/event connectors, complete framework-specific methods and professional design/operating-effectiveness conclusions.",
        "evidence": [
          "backend/app/modules/grc/service.py",
          "backend/tests/qa_crud/test_sod_reporting.py",
          "frontend/tests/sod-results.test.tsx"
        ]
      },
      {
        "id": "10",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "Diligence subjects, document validity, ownership look-through, uploaded-list screening, adverse-media adjudication and grant mandate/utilisation controls.",
        "UAE": "Uses explicit country/date policy and retained mandate, identity, ownership and governance evidence; no live registry or professional attestation is inferred.",
        "India": "Reuses the same controls with separately assessed legal/grant context; uploaded evidence does not establish registration authenticity or eligibility.",
        "remaining": "Licensed live registry/PEP/sanctions services, qualified local legal requirements, professional validators, consented partner pilots and any insurance/service arrangement.",
        "evidence": [
          "backend/app/modules/country_workflows/diligence_schemas.py",
          "backend/app/modules/country_workflows/grant_utilisation.py",
          "backend/tests/qa_crud/test_ownership_paths.py",
          "backend/tests/qa_crud/test_screening_candidates.py"
        ]
      },
      {
        "id": "11",
        "status": "COMMON_CONTROLS_IMPLEMENTED",
        "shared": "Vendor identity/diligence, ownership and conflicts, uploaded-list screening, adverse-media evidence and separate procurement/payment controls.",
        "UAE": "UAE entity/policy scope is retained; unsupported or unavailable external searches remain unresolved evidence.",
        "India": "India entity/policy scope is retained; registry/tax registration authenticity is not inferred from document syntax or uploaded declarations. India supplier-payment review additionally supports source-assessed micro/small eligibility and acceptance-based due dates with retained document dependencies.",
        "remaining": "Authorized provider integrations, complete country diligence criteria and independently checked vendor cases; software cannot manufacture authenticity or professional attestation.",
        "evidence": [
          "backend/app/modules/country_workflows/adverse_media.py",
          "backend/app/modules/country_workflows/ownership_paths.py",
          "backend/tests/qa_crud/test_ownership_paths.py",
          "backend/tests/qa_crud/test_screening_candidates.py"
        ]
      },
      {
        "id": "12",
        "status": "OPERATIONAL_WORKFLOWS_IMPLEMENTED",
        "shared": "Stock quantities/site/UOM, controlled count-date movement bridge, custody confirmations, cost/NRV evidence, GL valuation controls and missing monetary coverage.",
        "UAE": "Shared stock procedures use explicit ownership/custody, framework and valuation evidence; no physical attendance or automatic customs ownership conclusion.",
        "India": "The same controlled quantities and valuation procedures support separately assessed audit/tax requirements; local statutory disclosures remain country-pack work.",
        "remaining": "Actual count attendance, title/condition/third-party evidence, industry-specific valuation methods and representative client qualification.",
        "evidence": [
          "backend/app/modules/country_workflows/inventory_valuation.py",
          "backend/app/modules/country_workflows/inventory_custody.py",
          "backend/tests/qa_crud/test_inventory_controlled_bridge.py",
          "backend/tests/unit/test_inventory_valuation.py"
        ]
      },
      {
        "id": "13",
        "status": "PARTIAL_SPECIALIST_COVERAGE",
        "shared": "Payroll accrual/posting controls, employee/channel settlement, contributions, assessed expected remittances and split payment allocation with retained rule/source lineage.",
        "UAE": "WPS, pension/cohort and benefit reviews remain separate purpose-bound workflows with independently reviewed published rule profiles and supporting evidence. Reviewed constant-model full-time/part-time gratuity now bridges to independently controlled expected settlements, with typed employment-service scopes and independent HR/bank allocation evidence; rule or supporting-context replacement stales dependent approvals.",
        "India": "PF/EPS/ESI/PT assessed component calculations, ECR/ESIC member/day/wage population checks and payroll-to-GL controls are implemented.",
        "remaining": "Complete legal cohort/state/schema qualification, representative payroll clients, statutory charges not covered by current formulas and actual filing/payment execution.",
        "evidence": [
          "backend/app/modules/country_workflows/payroll_ledger_schemas.py",
          "backend/tests/qa_crud/test_payroll_ledger.py",
          "backend/tests/qa_crud/test_published_pension_source.py",
          "backend/tests/qa_crud/test_published_payroll_source.py",
          "backend/app/modules/country_workflows/benefit_settlement_source.py",
          "docs/country-workflows/benefit-settlement.md",
          "docs/phase-12/benefit-settlement-validation.json",
          "docs/phase-12/gratuity-browser-b315b53.json"
        ]
      }
    ],
    "unit_receipt": "docs/phase-12/merchant-reserve-backend.xml",
    "database_receipt": "docs/phase-12/merchant-reserve-api.xml",
    "unit_summary": {
      "tests": 3208,
      "passed": 3203,
      "skipped": 5,
      "failures": 0,
      "errors": 0
    },
    "database_summary": {
      "tests": 4,
      "passed": 4,
      "skipped": 0,
      "failures": 0,
      "errors": 0
    },
    "synthetic_scenarios": {
      "count": 154,
      "by_country": {
        "AE": 101,
        "IN": 53
      },
      "interpretation": "Authored synthetic operational scenarios with retained passing unit cases; not real-client or legal qualification"
    }
  }
} as const;
export default function Roadmap() {
  const t = useHostTheme();
  const [country, setCountry] = useState("Both");
  const [query, setQuery] = useState("");
  const [discovery, setDiscovery] = useState(false);
  const checkpoint = data.checkpoint;
  return <main style={{padding:24,maxWidth:1100,margin:"auto",color:t.text.primary,background:t.bg.editor,fontSize:14,lineHeight:1.6}}>
    <H1>TheAuditor · implementation and remaining work</H1>
    <Text>{checkpoint.as_of} · UAE first · India second · 13 reference use cases</Text>
    <p style={{fontSize:18,color:t.accent.primary}}>Operational workflows implemented; complete country-law and client qualification remain open.</p>
    <p>{checkpoint.scope}</p>
    <p><strong>{checkpoint.release_status.replaceAll("_", " ")}</strong></p>
    <div style={{display:"flex",gap:24,flexWrap:"wrap",margin:"24px 0",padding:"16px 0",borderTop:`1px solid ${t.stroke.secondary}`,borderBottom:`1px solid ${t.stroke.secondary}`}}>
      <div><strong>{checkpoint.synthetic_scenarios.count}</strong><br/>Authored synthetic scenarios</div>
      <div><strong>{checkpoint.unit_summary.passed.toLocaleString()}</strong><br/>Backend units passed · {checkpoint.unit_summary.skipped} skipped</div>
      <div><strong>{checkpoint.database_summary.passed}</strong><br/>Latest focused database cases passed</div>
    </div>
    <Text>{checkpoint.synthetic_scenarios.interpretation}</Text>
    <p>Source revision: <code>{checkpoint.source_revision}</code>. These counts do not establish 154 qualified clients or a complete legal corpus.</p>
    <H2>Verification scope</H2>
    <ul>{checkpoint.verification.map(v => <li key={v.label}><strong>{v.label}: {v.result}.</strong> {v.limit} <code>{v.path}</code></li>)}</ul>
    <ul>{checkpoint.hosted_runs.map(r => <li key={r.url}><a href={r.url} style={{color:t.text.link}}>{r.label}</a> — {r.status_at_checkpoint}</li>)}</ul>
    <H2>All 13 use cases</H2>
    <div style={{display:"flex",gap:16,flexWrap:"wrap",margin:"16px 0"}}>
      <label>Country treatment <select value={country} onChange={e => setCountry(e.target.value)}>{["Both","UAE","India"].map(c => <option key={c}>{c}</option>)}</select></label>
      <label style={{flex:1}}>Search current scope <input value={query} onChange={e => setQuery(e.target.value)} style={{width:"100%"}}/></label>
      <label><input type="checkbox" checked={discovery} onChange={e => setDiscovery(e.target.checked)}/> Show original discovery and plan</label>
    </div>
    {data.cases.filter(c => JSON.stringify(c).toLowerCase().includes(query.toLowerCase())).map(c => <details key={c.title} style={{borderBottom:`1px solid ${t.stroke.secondary}`,padding:"16px 0"}}>
      <summary style={{cursor:"pointer",fontWeight:600}}>{c.title} · {c.current.status.toLowerCase().replaceAll("_", " ")}</summary>
      <p><a href={c.url} style={{color:t.text.link}}>Original reference page</a> · discovery reviewed 24 October 2026</p>
      <H3>Shared implementation</H3><p>{c.current.shared}</p>
      {country !== "India" && <><H3>UAE now</H3><p>{c.current.UAE}</p></>}
      {country !== "UAE" && <><H3>India now</H3><p>{c.current.India}</p></>}
      <H3>Still required</H3><p>{c.current.remaining}</p>
      <H3>Repository evidence</H3><ul>{c.current.evidence.map(p => <li key={p}><code>{p}</code></li>)}</ul>
      {discovery && <><H3>Original discovery — {data.date}</H3><p>{c.reference}</p><p>{c.baseline}</p><H3>Original shared build specification</H3><p>{c.shared}</p>{country !== "India" && <p>UAE: {c.UAE}</p>}{country !== "UAE" && <p>India: {c.India}</p>}<H3>Acceptance criteria</H3><p>{c.acceptance}</p></>}
    </details>)}
    <H2>Remaining work and proof required</H2>
    {checkpoint.open_gates.map(g => <section key={g.priority} style={{marginTop:24}}><H3>{g.priority}</H3><p>{g.work}</p><p><strong>Completion evidence:</strong> {g.proof}</p></section>)}
    {discovery && <><H2>Original planning sections — {data.date}</H2>{data.sections.map(([title,paras]) => <section key={title} style={{marginTop:24}}><H3>{title}</H3>{paras.map((p,i) => <p key={i}>{p}</p>)}</section>)}<H2>Original authoritative source ledger</H2><ul>{data.sources.map(([title,url]) => <li key={url}><a href={url} style={{color:t.text.link}}>{title}</a></li>)}</ul></>}
    <p>Discovery observations, implementation evidence, synthetic checks and professional release qualification are separate claims. No signed opinion, filed return, live registry verification or real-client qualification is established by this roadmap.</p>
  </main>;
}

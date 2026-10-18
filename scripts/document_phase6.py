"""Generate reproducible implementation inventories and local arithmetic benchmarks."""
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.core.permissions import ROLE_PERMISSIONS
from app.main import app
from app.modules.tax.catalogue import AI_TASKS, KINDS, SOURCES
from app.modules.tax.calculations import standard_tax
from app.modules.tax.schemas import RuleParameters

out = root / "docs/phase-6"
out.mkdir(exist_ok=True)
schema = app.openapi()
(out / "openapi.json").write_text(json.dumps(schema, indent=2))
paths = [(path, method.upper(), spec.get("summary", "")) for path, operations in schema["paths"].items() if path.startswith("/api/v1/tax") for method, spec in operations.items() if method in {"get", "post", "patch", "delete"}]
(out / "api-inventory.md").write_text("# Phase 6 API inventory\n\n" + "\n".join(f"- `{method} {path}` — {summary}" for path, method, summary in paths) + "\n\nTax records also use the existing engagement audit PATCH and actions endpoints for optimistic versioning, independent approval and immutable history. Tax schemas are returned by the engagement workspace endpoint. Lists accept bounded pagination. Exports require tax.return.export and engagement access. Full request/response schema: openapi.json.\n")
roles = ["Corporate Tax Preparer", "Senior Tax Consultant", "Tax Manager", "Tax Director", "Tax Partner", "Chartered Accountant", "Independent Reviewer", "Client Finance User", "Firm Administrator"]
(out / "role-permissions.md").write_text("# Phase 6 role permissions\n\nPermissions are checked against active tenant membership and live engagement assignment, including each group-member engagement. No source is exposed merely because a user knows its UUID.\n\n" + "\n\n".join(f"## {name}\n\n" + ", ".join(f"`{p}`" for p in ROLE_PERMISSIONS[name] if p.startswith(("tax.", "portal.", "ifrs.read"))) for name in roles) + "\n\nFinal computation/return approvals require Tax Manager then Tax Partner (Tax Director can satisfy either stage; Chartered Accountant satisfies partner). Different independent reviewers are required; preparers and historical editors cannot approve their own work. Independent Reviewer permission alone does not satisfy the named final approval role. Client Finance User receives the existing restricted request/evidence portal; internal tax workpapers and tax exports are not published to clients in this phase.\n")
(out / "legislation-registry.md").write_text("# Phase 6 legislation registry\n\nOfficial-source metadata is held in tax/catalogue.py. Engagement-owned tax-rule records carry source ID, article, decision, effective interval, legal knowledge date, document version/hash, conditions, exceptions, typed parameters, technical-review rationale and lifecycle. Their revisions and independent review decisions persist. Approved legal records cannot reopen: amendments require a new rule/version. Technical review is required before a profile can reference a rule; catalogue metadata is never automatically approved. Document hashes are optional and must be supplied when an exact acquired document is retained; this registry is not a full-text legal archive.\n\n" + "\n\n".join(f"- **{key}** — [{value['title']}]({value['url']}). Coverage: {value['coverage']}." for key,value in SOURCES.items()) + "\n\nResearch cut-off: 18 October 2026. MD229/2025 issued 28 August 2025 but applies from 1 June 2023, replacing MD265/2023. MD131/2026 issued 29 July 2026 extends the SBR tax-period end boundary to 31 December 2029. Its exact Gazette publication/effective date is not independently established here; a technical reviewer must verify it before production adoption. FTA6/2026 issued 2 June 2026 applies to periods commencing from 1 January 2026. MD84/2025 applies to periods commencing from 1 January 2025. MD302/2024 applies from 2025; earlier participation/foreign-PE rules require their historical source version. FTA12/2026, FTA15/2026 and the 2026 clarification index are reference metadata only, without automatic computational activation.\n")
coverage = [
    ("Standard bands", "Fully calculated and tested", "CT-RATES", "Taxable income through AED375,000 at 0%; excess at 9%; approved version parameters"),
    ("Accounting-to-tax bridge", "Fully calculated and tested", "CT-LAW", "Approved IFRS PBT, source-bounded reviewed adjustments, approved exempt-income schedules"),
    ("Expense deductibility", "Supported with manual professional input", "CT-LAW", "Entertainment recipient scope/50%, fines, nonbusiness, explicit permanent/timing/other decisions; no blanket provisions add-back"),
    ("SBR", "Supported with manual professional input", "MD73-2023 / MD131-2026", "3M current/history ceiling, election, residence, MNE/QFZP and anti-fragmentation facts; historical completeness reviewed"),
    ("QFZP conditions/activity", "Supported with manual professional input", "CT-LAW / MD229-2025", "Canonical evidence-backed conditions, reviewed contracts and transaction classifications; unresolved IP nexus blocked"),
    ("De minimis", "Fully calculated and tested", "MD229-2025", "Lower of5% applicable revenue and5M; explicit special-category denominator exclusions; no generic 9% nonqualifying-revenue shortcut"),
    ("2026 distribution procedures", "Assessment checklist only", "FTA6-2026", "Period/as-of gating, approved procedures rule, evidence-backed AUP condition; sample-size helper and 30-day submission due date; no auditor AUP report creation"),
    ("Interest limitation", "Supported with manual professional input", "MD126-2023 / CTGIDL1", "Statutory EBITDA bridge, pro-rated12M/30%, older carry first,10 subsequent periods, amortized capitalized interest; reviewed manual source balances"),
    ("Loss utilization", "Fully calculated and tested", "CT-LAW37", "75% cap, eligible prior-period lots, immutable postings, serialized posting, correction reversals; no automatic eligibility conclusion"),
    ("Loss eligibility/transfer", "Supported with manual professional input", "CT-LAW38/39", "Continuity/same-business and75% common ownership facts reviewed; explicit prior-period transfer posted once; current-year loss transfer excluded"),
    ("Tax Group", "Supported with manual professional input", "CT-LAW40–42 / CTP007", "Full-period95% three-rights tests, aligned resident members, FTA and audit evidence; one group threshold, explicit consolidated tax adjustments"),
    ("Qualifying group/restructuring relief", "Assessment checklist only", "CT-LAW26/27", "Evidence-backed election/eligibility,75% qualifying group threshold and two-year clawback monitoring; no automatic tax-neutral journal"),
    ("Transitional", "Supported with manual professional input", "CT-LAW61", "First-period election, valuation evidence, manual assessed adjustment; standalone workpaper does not automatically post adjustment"),
    ("Domestic dividend/participation/foreignPE", "Supported with manual professional input", "CT-LAW22–24 / MD302-2024", "Reviewed canonical conditions and source-bounded exemption; complex eligibility/netting remains professional input"),
    ("Foreign tax credit", "Supported with manual professional input", "CT-LAW47", "Min foreign paid/UAE attributable, capped current tax; source-income ceiling and no overlap with exempt line; allocation is manual"),
    ("Related/connected persons", "Assessment checklist only", "CT-LAW34–36", "Dated relationships, contracts/accounts, risk review and separate approved adjustment link; no TP benchmarking"),
    ("Foundations", "Assessment checklist only", "CTGFF1", "Governance, beneficiaries, application and FTA approval evidence; never automatic transparency"),
    ("Returns/deadlines", "Fully calculated and tested", "CT-LAW53", "Nine-month calendar deadline plus explicitly approved overrides; checklist and current computation gate; external filing evidence only"),
    ("Registration/exemption2026", "Research/reference only", "FTA12-2026 / FTA15-2026", "Manual event-based deadline assessments; no automatic application"),
    ("Pillar Two/special taxpayer computations", "Not implemented", "N/A", "Pillar Two blocks release; natural persons, transparent partnerships, exempt persons and foundations require specialist methodology"),
]
(out / "regulatory-coverage.json").write_text(json.dumps([dict(zip(["feature", "coverage", "sources", "scope"], row)) for row in coverage], indent=2))
(out / "rule-version-matrix.md").write_text("# Phase 6 regulatory coverage matrix\n\nCoverage describes the implemented scope, not legal certification. No source coverage means every provision in that instrument is supported.\n\n" + "\n\n".join(f"- **{feature} — {status}.** Sources: {sources}. {scope}." for feature,status,sources,scope in coverage) + "\n\nEvery profile selects approved rule IDs for its tax period and legal-as-of date. Computation snapshots include full selected rule bodies and source URLs. Later rule versions do not alter an existing run. Effective interval must contain the tax period, knowledge date cannot be after the selected legal-as-of date, and known dates for the three verified new decisions cannot predate issuance. New legal amendments are records and typed parameters; new legal formulas still require code and independent tests.\n")
parameters = RuleParameters()
start = time.perf_counter()
for _ in range(10000):
    result = standard_tax(Decimal("1600000"), parameters)
elapsed = time.perf_counter() - start
(out / "benchmarks.json").write_text(json.dumps({"standard_tax_calls":10000, "elapsed_seconds":elapsed, "result":"110250.00000000", "scope":"Local CPU arithmetic only; excludes API, database, concurrent exports and large group workloads"}, indent=2))
print(f"Generated {len(paths)} tax API operations, {len(coverage)} coverage rows; benchmark {elapsed:.4f}s")

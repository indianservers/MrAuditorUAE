"""Build the Phase 3 capability/verification register from retained test results."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/engine-strengthening/phase3"


def gap(engine, capability, status, issue, consequence, fix, verification):
    return {
        "engine": engine,
        "capability": capability,
        "actual_status": status,
        "issue": issue,
        "consequence": consequence,
        "implementation_or_required_fix": fix,
        "verification": verification,
    }


ROWS = [
    gap(
        "shared",
        "Execution receipts and approved history",
        "implemented",
        "Earlier schedules lacked common provenance/version metadata",
        "Historical results could be reused without establishing current sources",
        "accounting/1 inside existing immutable runs; code/source/chart/currency/policy/current-tax dependency checks",
        "operating-company workflow and revision/lock integration tests",
    ),
    gap(
        "shared",
        "Journal lifecycle, locks and duplicates",
        "implemented_reporting_overlays_only",
        "Calculated journal could be confused with posting; late stale inputs and period changes",
        "Unsupported/duplicate or stale reporting adjustments",
        "Currency-rounded proposals, distinct review, locked-period rejection, serialized reference/component checks; no source-ledger posting",
        "revision/duplicate/period-lock and independent approval tests",
    ),
    gap(
        "shared",
        "Automatic recalculation and live ledger posting",
        "not_implemented",
        "No universal invalidation worker or verified posting connector",
        "Stale outputs require explicit recalculation/reapproval; reporting approval is not GL posting",
        "Keep fail-closed checks; implement authorized connector with exact accounts/period/version/balance and idempotency before posting",
        "No live posting or automatic background regeneration claimed",
    ),
    gap(
        "E09",
        "Statements, comparative mapping, notes and cash flow",
        "existing_strengthened_and_reverified",
        "Source freshness and unsupported netting needed enforcement",
        "Apparently reconciled output could reference stale assumptions or hide opposing balances",
        "Recheck all approved inputs; netting rationale; comparative section validation; current/noncurrent/RP/disaggregation attributes; original/adjusted views",
        "phase5 reporting/workspace and connected company workflows",
    ),
    gap(
        "E09",
        "Framework and policy/estimate/disclosure facts",
        "bounded_implementation",
        "Full licensed disclosure coverage and entity-specific legal applicability not established",
        "Framework label must not be read as compliance certification",
        "full_ifrs-only profiles plus approved structured accounting-policy facts; missing facts/checks remain issues",
        "schema/numeric/reporting tests; source-policy register; no comprehensive checklist certification",
    ),
    gap(
        "E09",
        "E05 current tax and IAS12 deferred tax",
        "implemented_for_ordinary_reviewed_case",
        "No reviewed current-tax consumption; DTA could be recognized from a flag without recovery evidence",
        "Tax/accounting cycles or unsupported DTA recognition",
        "Current E05 release/hash/access check; distinct post-tax profile; item-specific tax base/rate/locations; zero unevidenced DTA; GloBE separate",
        "company profit1199599 -> current74213.91/deferred25.65 -> profit1125359.44, cash difference0; DTA negative fixture",
    ),
    gap(
        "E09",
        "Complete tax/disclosure specialist cases",
        "not_implemented",
        "Complex exceptions, group packages, full Pillar Two accounting and complete current-licensed disclosure implementation",
        "No blanket IAS12/IFRS compliance claim",
        "Specialist source review and independently verified schedules before consumption",
        "Unsupported cases documented; E08 accounting bridge not claimed",
    ),
    gap(
        "E15",
        "Available-for-use, components, CIP, disposal and estimate changes",
        "implemented_bounded_ppe",
        "Legacy capitalisation date was implicitly the depreciation start; no prospective estimate split",
        "Premature depreciation or altered prior estimates",
        "Evidenced commencement/CIP; exclude derecognition date; residual floor; prospective split; gross/accumulated rollforwards",
        "independent asset numeric tests and approved company depreciation365",
    ),
    gap(
        "E15",
        "Capitalization, partial disposals and non-PPE measurement",
        "partial_or_blocked",
        "No complete borrowing-cost/inspection/capitalization workflow or IAS40/IFRS5/IAS38 measurement",
        "Incorrect asset-class treatment if a generic PPE formula were reused",
        "Explicitly block non-PPE classes; use approved components/specialist schedules; complete policy/valuation evidence",
        "non-PPE rejection and CIP tests; broader measurement not claimed",
    ),
    gap(
        "E15",
        "Lease measurement and remeasurement comparison",
        "existing_strengthened",
        "Initial liability journal could duplicate a remeasured liability; ROU tail not explicit",
        "Overstatement or incomplete expense period",
        "Preserve dated actual/365 kernel; disclose remaining ROU depreciation; block initial journal on modification runs",
        "existing dated-payment/reassessment tests; company lease liability/ROU1000",
    ),
    gap(
        "E15",
        "Complete lease modifications/lessor and full CGU allocation",
        "not_implemented",
        "No validated modification/termination/lessor treatment or per-asset impairment floors",
        "Draft computations cannot justify generic specialist journals",
        "Obtain approved classification/expert inputs and implement appropriate specialist schedules; missing valuation fields fail",
        "missing valuation rejection; existing impairment numeric sensitivities; limitations retained",
    ),
    gap(
        "E16",
        "Payroll ledger/payment/provision accounting bridge",
        "implemented_aggregate_reviewed_inputs",
        "Accounting movement and statutory settlement estimate were not explicitly distinct",
        "Simple gratuity or payment-file totals could be misrepresented as IAS19/bank assurance",
        "Aggregate payroll payable and benefit provision rollforwards; distinct P&L/OCI; actuarial reference required; no employee names/bank master",
        "three regime labels, actuarial missing-input cases, company benefit20 and tax-source permission test",
    ),
    gap(
        "E16",
        "Statutory settlement and payment-source reconciliation",
        "existing_engine_retained",
        "Legal and scheme cohort applicability depends on supplied reviewed evidence",
        "Mainland formula cannot be universally used for DIFC/ADGM/alternative schemes",
        "Reuse country_workflows payroll-settlement and uae-benefit-review; no duplicated hardcoded gratuity rates",
        "existing supplied-rule eligibility/cap/ambiguous/missing/alternative-scheme unit tests",
    ),
    gap(
        "E16",
        "Employee masters and actual salary/proration/payroll generation",
        "not_implemented_by_this_phase",
        "Restricted HR master, joiner/leaver compensation, leave/overtime schemes and payroll controls absent",
        "Cannot operate real payroll or claim complete E16 coverage",
        "Implement authorized salary-specific storage/access, effective compensation, verified rules, payroll uniqueness and bank confirmation before production",
        "No salary-generation or payment-instruction workflow claimed",
    ),
    gap(
        "E17",
        "FIFO/moving weighted-average purchased-stock valuation",
        "implemented",
        "Only a count/NRV audit comparison existed; reproducible costing missing",
        "Closing valuation could not be reconstructed from movements",
        "Existing IFRS workpaper/calculation path now processes evidenced opening/receipts/landed-cost/issues, explicit ordering, negative/duplicate/cut-off checks",
        "independent FIFO cost176 versus average128; sequence/negative/duplicate/backdated tests",
    ),
    gap(
        "E17",
        "Transfers, ownership, NRV and counts",
        "implemented_bounded_bridge",
        "Custody, cost and count differences require separate treatment",
        "Unsupported recognition or transfer/NRV plug",
        "Exclude custody; reciprocal same-SKU/UOM/ownership/quantity/cost transfers; net selling/completion costs; reversal ceiling; separate count issues",
        "transfer cost100, mismatch33 retained; custody and quantity variance; NRV reversal cap; existing count bridge",
    ),
    gap(
        "E17",
        "Returns, production, specific identification and closed-period recosting",
        "not_implemented",
        "No verified return layers/WIP/overhead/specific-identification or cross-period correction engine",
        "These cases must not be processed as ordinary receipts/issues without specialist work",
        "Implement and independently reconcile necessary schedules; revise/reapprove input versions rather than altering approved history",
        "Unsupported input fields rejected; no production/return golden workflow claimed",
    ),
    gap(
        "E18",
        "Approved member packages and translation",
        "implemented_draft_only",
        "Control dates, special rate cases and source access needed explicit guards",
        "Unsupported member aggregation could appear releasable",
        "Approved current packages; three-part control; effective dates; explicit closing/average/historical/opening rates; same-currency unit rates; block hyperinflation/midyear control",
        "AED parent/USD-functional subsidiary fixture, translated assets390/profit75, FX cash effect115; blocked special cases",
    ),
    gap(
        "E18",
        "Reciprocal differences and eliminations",
        "implemented_bounded_pairs",
        "No structured mismatch classification or cumulative limit",
        "Unmatched/excess balances could be eliminated",
        "Declared counterparties/pair amounts, classifications, source evidence, exact pair reference, cumulative cap and duplicate checks",
        "unmatched draft issue; elimination409; matched draft output",
    ),
    gap(
        "E18",
        "Member cash workings and group disclosure inputs",
        "implemented_pre_group_elimination_draft",
        "Opening FX/cash workings were not available in group output",
        "No auditable cash bridge",
        "Retain evidenced opening/closing/flow rates, member workings, presentation translation effect, member note inputs; missing data explicit",
        "group-workflow/intercompany-workflow technical artifacts; draft export verified",
    ),
    gap(
        "E18",
        "Final consolidated release, ownership events, acquisition/NCI/equity and comparatives",
        "blocked_not_implemented",
        "Acquisition journals/valuation, group equity/NCI rollforward, cash eliminations and group notes incomplete",
        "Cannot release statutory consolidated statements or treat provisional NCI as final",
        "Keep ready=false and provisional statuses; complete specialist packages, comparatives, group CF/equity/disclosures before release",
        "Group fixture explicitly asserts release blocked; no final consolidated package claimed",
    ),
]


def xml_summary(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    return {
        "tests": len(cases),
        "passed": sum(
            not any(c.find(tag) is not None for tag in ["failure", "error", "skipped"])
            for c in cases
        ),
        "failures": sum(c.find("failure") is not None for c in cases),
        "errors": sum(c.find("error") is not None for c in cases),
        "skipped": sum(c.find("skipped") is not None for c in cases),
        "path": str(path),
    }


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "gap-matrix.json").write_text(
        json.dumps(
            {
                "phase": 3,
                "production_scope_complete": False,
                "rows": ROWS,
                "migration": "No new schema; requires existing IFRS/tax migrations and 0020_foundation_periods",
            },
            indent=2,
        )
    )
    results = {
        name: xml_summary(DOCS / name)
        for name in [
            "unit-results.xml",
            "integration-results.xml",
            "frontend-results.xml",
        ]
        if (DOCS / name).exists()
    }
    paths = [
        *sorted((ROOT / "backend/app/modules/ifrs").glob("*.py")),
        ROOT / "backend/app/api/v1/ifrs.py",
    ]
    sources = json.loads((DOCS / "source-policy-register.json").read_text())["sources"]
    (DOCS / "verification.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "baseline": {"passed": 527, "skipped": 4},
                "actual_results": results,
                "primary_sources_retrieved": sum(
                    s["status"] == "RETRIEVED" for s in sources
                ),
                "primary_source_total": len(sources),
                "source_adoption": "NOT_ADOPTED_BY_RETRIEVAL",
                "live_gl_posting": False,
                "complete_five_engine_production_scope": False,
                "ai_execution": "Disabled for deterministic verification",
                "implementation_files": [
                    {
                        "path": str(p.relative_to(ROOT)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in paths
                ],
            },
            indent=2,
        )
    )

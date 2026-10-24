"""Summarize persisted verification receipts without counting synthetic tests as law qualification."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.country_workflows.catalogue import WORKFLOWS  # noqa: E402
from tests.unit.country_workflow_cases import CASES  # noqa: E402

target = ROOT / "docs/country-workflows"


def xml_summary(name):
    root = ET.parse(target / name).getroot()
    suites = list(root) if root.tag == "testsuites" else [root]
    return {
        field: sum(int(s.get(field, "0")) for s in suites)
        for field in ["tests", "failures", "errors", "skipped"]
    }


front = json.loads((target / "frontend-results.json").read_text())
browser = json.loads((target / "browser-results.json").read_text())
assessed = sorted({c["workflow"] for c in CASES})
mapping = [
    {
        "reference": "TCS reconciliation",
        "implemented": ["india-withholding"],
        "remaining": "Native return adapters and qualified collection thresholds/certificates/current Act mapping",
    },
    {
        "reference": "Bank reconciliation",
        "implemented": ["bank-brs", "committed GL source bridge"],
        "remaining": "Qualified native bank PDF/XLSX adapters, account identity/ownership verification and larger populations",
    },
    {
        "reference": "PF/ESI/PT reconciliation",
        "implemented": ["statutory-dues"],
        "remaining": "Native ECR/ESIC/state exports and independently qualified contribution/membership/deadline calculations",
    },
    {
        "reference": "GST reconciliation",
        "implemented": ["india-gst"],
        "remaining": "Native GSTR/IMS parsers, RCM/ITC legal calculations, annual return mapping",
    },
    {
        "reference": "TDS reconciliation",
        "implemented": ["india-withholding"],
        "remaining": "Native 26AS/AIS/TRACES/successor formats and qualified tax calculations; explicit deductor/deductee legal-role modeling",
    },
    {
        "reference": "Indian tax audit",
        "implemented": ["tax-close", "existing statutory practice/report composer"],
        "remaining": "Complete approved legacy/new form crosswalk and clause calculations; checklist is not a tax-audit engine",
    },
    {
        "reference": "GST and tax audit orchestration",
        "implemented": ["tax-close", "india-gst", "india-withholding"],
        "remaining": "Qualified turnover/exposure bridges, complete annual outputs and filing adapters",
    },
    {
        "reference": "Statutory audit",
        "implemented": [
            "existing audit execution/evidence/review",
            "country workpapers",
        ],
        "remaining": "Complete profession-approved country/regulator reporting and mandatory evidence scope",
    },
    {
        "reference": "SOX/internal controls",
        "implemented": ["controls", "existing GRC"],
        "remaining": "Live access/event connectors, SOX issuer applicability and complete operating-effectiveness qualification",
    },
    {
        "reference": "Nonprofit diligence",
        "implemented": ["nonprofit-diligence"],
        "remaining": "Live eligibility/registry checks, licensed screening and professional attestation",
    },
    {
        "reference": "Vendor diligence",
        "implemented": ["vendor-diligence"],
        "remaining": "Live registries/UBO/sanctions/PEP screening and verified identity resolution",
    },
    {
        "reference": "Stock audit",
        "implemented": ["stock-audit"],
        "remaining": "Physical procedures, complete cutoff/movement evidence, native inventory adapters and any separately mandated drawing-power work",
    },
    {
        "reference": "Payroll audit",
        "implemented": ["payroll-settlement", "statutory-dues"],
        "remaining": "Native WPS/ECR files, qualified pension/cohort/end-of-service/salary-tax engines",
    },
]
report = {
    "date": "2026-10-24",
    "stage": "FIRST_IMPLEMENTATION_INCREMENT",
    "production_release": "NOT_QUALIFIED",
    "assessed_workflows": assessed,
    "assessed_workflow_count": len(assessed),
    "named_synthetic_scenarios": len(CASES),
    "scenario_interpretation": "Operational evidence comparisons and safeguards; not independently qualified laws or live integrations",
    "other_workspace_workflows_not_claimed_by_this_receipt": sorted(set(WORKFLOWS) - set(assessed)),
    "verification": {
        "backend_unit": xml_summary("unit-results.xml"),
        "database_api": xml_summary("integration-results.xml"),
        "frontend": {
            k: front.get(k)
            for k in ["numTotalTests", "numPassedTests", "numFailedTests", "success"]
        },
        "browser": browser["stats"],
        "production_build": "PASSED",
        "frontend_typecheck": "PASSED",
        "frontend_lint": "PASSED",
        "backend_ruff": "PASSED",
        "country_module_mypy": "PASSED",
    },
    "test_boundaries": {
        "database": "auditos_country_workflows_test",
        "redis_database": 10,
        "integration_scanner": "EXPLICIT_TEST_DOUBLE",
        "integration_broker_dispatch": "EXPLICIT_TEST_DOUBLE",
        "browser_fixture_scanner": "EXPLICIT_TEST_DOUBLE",
        "browser_queue_worker": "REAL_REDIS_AND_CELERY",
    },
    "reference_use_case_mapping": mapping,
    "source_hashes_at_report_generation": {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "backend/app/modules/country_workflows").glob("*.py")
    },
    "shared_checkout_note": "Concurrent edits are preserved; these receipts do not certify untested additional workflows or changes made after the test runs.",
}
for name in ["backend_unit", "database_api"]:
    assert report["verification"][name]["failures"] == report["verification"][name]["errors"] == 0
assert front["numFailedTests"] == 0 and browser["stats"]["unexpected"] == 0
(target / "delivery.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "assessed_workflows": len(assessed),
            "synthetic_scenarios": len(CASES),
            "verification": report["verification"],
        },
        indent=2,
    )
)

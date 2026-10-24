"""Build the 100-case matrix (original 01–50 plus incremental 51–100) from the runtime UAE manifest and real receipts."""

import csv

import html

import json
import sys

from datetime import UTC, datetime

from pathlib import Path

from xml.etree import ElementTree



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "backend"))
from app.modules.jurisdictions.ae.advanced_specs import spec
PACKAGE = ROOT / "backend/app/modules/jurisdictions/ae"

DOCS = ROOT / "docs/mr-auditor-business"

DOCS.mkdir(parents=True, exist_ok=True)

manifest = json.loads((PACKAGE / "use_cases.json").read_text(encoding="utf-8"))

source_register = json.loads((PACKAGE / "source_register.json").read_text(encoding="utf-8"))

engine_definitions = [

    ("E01", "Jurisdiction, legal sources and effective rules", "jurisdictions; regulatory; approved tax/VAT/TP rule records"),

    ("E02", "Ingestion, OCR and extraction", "intelligence.documents; enterprise_ai.documents; clean evidence versions"),

    ("E03", "Ledger normalization and quality", "accounting; intelligence.foundations; approved mapping and source snapshots"),

    ("E04", "VAT", "vat.service; jurisdictions.ae.registration; jurisdictions.ae.vat_errors"),

    ("E05", "Corporate tax", "tax.service; tax.contracts; reviewed adjustment/loss/election records"),

    ("E06", "Free-zone CT", "tax.calculations.qfzp and approved activity/substance classifications"),

    ("E07", "Transfer pricing and relationships", "tp.service; supplied datasets; approved relationship/transaction records"),

    ("E08", "DMTT", "dmtt.service; separate group/entity inputs and scope decisions"),

    ("E09", "IFRS and disclosures", "ifrs.service; ifrs.contracts; ifrs.calculations; ifrs.fx"),

    ("E10", "Audit planning and sampling", "audit_execution; audit_analytics; approved materiality policies"),

    ("E11", "Journal analytics", "audit_analytics; explicit ML/rules/statistical execution modes"),

    ("E12", "Receivables and revenue", "ifrs ECL/revenue; country_workflows settlement/ECL procedures"),

    ("E13", "Payables and procurement", "country_workflows procurement, expenses and cutoff"),

    ("E14", "Cash, bank and treasury", "country_workflows bank-brs; reconciliation; ifrs.fx"),

    ("E15", "Assets, leases and impairment", "ifrs fixed-assets/lease/impairment engines"),

    ("E16", "Payroll and benefits", "country_workflows payroll/benefit sources; ifrs employee-benefits"),

    ("E17", "Inventory", "ifrs inventory/NRV; country_workflows count/movement bridge"),

    ("E18", "Group reporting", "ifrs consolidation/intercompany; tax groups remain separate"),

    ("E19", "Compliance readiness", "regulatory templates/checklists; tax-deadline records; supplied obligations"),

    ("E20", "Engagement, approval and evidence", "audit_execution; lineage; immutable versions and source ACL inheritance"),

    ("E21", "Controlled AI orchestration", "enterprise_ai.business; reviewed recipes; separate optional language gateway"),

    ("E22", "External integration health", "connectors; stored scoped connection/sync status; controlled file import"),

]

engines = [{"id": key, "responsibility": title, "implementation": implementation,

            "state": "Partial", "meaning": "Existing bounded core plus connected adapters; not a standalone new microservice or blanket qualification"}

           for key, title, implementation in engine_definitions]

rows = []

for case in manifest["items"]:

    identifier = case["id"]

    tests = ["tests/unit/test_uae_business_cases.py::test_fifty_distinct_cases_have_bounded_approved_engine_graphs",

             "tests/qa_crud/test_uae_business_cases.py::test_all_fifty_case_entries_validate_real_scope_and_first_collection_step"]

    if identifier == 1:

        tests += ["tests/unit/test_uae_business_cases.py::test_registration_arithmetic_is_policy_driven_decimal_and_not_a_legal_determination"]

    if identifier == 7:

        tests += ["tests/unit/test_uae_property_facts.py"]

    if identifier == 8:

        tests += ["tests/unit/test_uae_vat_errors.py"]

    if identifier == 31:

        tests += ["tests/qa_crud/test_uae_business_cases.py::test_assistant_lease_action_matches_specialist_engine_and_rechecks_source",

                  "frontend/e2e/uae-business-cases.spec.ts"]

    if identifier == 45:

        tests += ["tests/unit/test_uae_business_cases.py::test_monetary_fx_is_not_realized_or_presentation_fx"]

    if identifier == 49:

        tests += ["tests/phase7/test_vat_workflows.py"]

    if identifier >= 51:

        tests = ["tests/unit/test_uae_advanced.py", "tests/qa_crud/test_uae_advanced.py::test_all_new_cases_have_real_approved_engine_actions_and_lineage"]

        if identifier==97:tests += ["tests/unit/test_workbook_integrity.py","tests/qa_crud/test_uae_advanced.py::test_original_xlsx_scanner_respects_quarantine_and_source_replacement"]

        if identifier in {52,91}:tests += ["frontend/e2e/uae-business-cases.spec.ts"]

    rows.append({**case,

                 "existing_capability": "; ".join(e["id"]+": "+e["implementation"] for e in engines if e["id"] in case["engines"]),

                 "incremental_work": (spec(identifier)["name"]+"; fields: "+", ".join(f["name"] for f in spec(identifier)["fields"])) if identifier>=51 else "Existing 01–50 connected adapter",

                 "missing_work": case["limitations"], "ui": "/ai/uae-use-cases (authorized engagement/entity/period context)",

                 "api": f"GET /ai/engagements/{{eid}}/use-cases/{identifier}/inputs; POST /ai/command task={case['key']}; POST /ai/engagements/{{eid}}/use-cases/{identifier}/actions",

                 "engine": ", ".join(case["engines"]),

                 "data_source": ", ".join(case["input_kinds"]) + "; current scoped snapshots/clean evidence and specialist runs as selected",

                 "approval": "Underlying specialist input approval; independent source/result review; consequential posting/sending/filing actions excluded",

                 "evidence": "Versioned source receipts, hashes, context/catalogue receipts, retained engine ID; generated papers inherit source permissions",

                 "tests": tests,

                 "test_scope": ("Typed contract, calculation/checklist, approved-input HTTP execution for this case, idempotency and source-change propagation; independent numerical expectations cover selected computations. Browser coverage is cases 52 and 91, not every sector/legal scenario." if identifier>=51 else "Original entries: scope/recipe/first read plus separately named specialist tests. Full specialist acceptance is not established."),

                 "new_capability_claim": "Connected business adapter/control improvement; existing numeric engines are reused, not counted as new engines"})



verification = {"generated_at": datetime.now(UTC).isoformat(), "runs": [], "overlap_warning": "Test runs overlap; counts must not be added as unique coverage"}

for path in sorted((DOCS / "evidence").glob("*.xml")):

    root = ElementTree.parse(path).getroot()

    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")

    verification["runs"].append({"file": path.name, **{key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}})

browser = DOCS / "evidence/browser-results.json"

if browser.exists():

    verification["browser"] = json.loads(browser.read_text(encoding="utf-8"))["stats"]

(DOCS / "capability-matrix.json").write_text(json.dumps({"scope": "100 business cases: preserved 01–50 plus incremental 51–100", "release_status": "Partial specialist coverage; all cases have explicit limits", "items": rows}, indent=2))

(DOCS / "engine-connection-map.json").write_text(json.dumps({"engines": engines}, indent=2))

(DOCS / "legal-source-register.json").write_text(json.dumps(source_register, indent=2))

(DOCS / "verification.json").write_text(json.dumps(verification, indent=2))

columns = ["id", "title", "scope_status", "completion_status", "existing_capability", "incremental_work", "missing_work", "ui", "api", "engine", "data_source", "approval", "evidence", "test_scope", "limitations"]

with (DOCS / "capability-matrix.csv").open("w", newline="", encoding="utf-8-sig") as stream:

    writer = csv.DictWriter(stream, fieldnames=columns)

    writer.writeheader()

    for row in rows:

        writer.writerow({key: "; ".join(row[key]) if isinstance(row[key], list) else row[key] for key in columns})

headings = ["Case", "Status", "UI / API", "Engine", "Sources / approval / evidence", "Verification", "Limits / blockers"]

cells = [[f"{r['id']:02}. {r['title']}",r["completion_status"],r["ui"]+"; "+r["api"],r["engine"],r["data_source"]+"; "+r["approval"]+"; "+r["evidence"],r["test_scope"],"; ".join(r["limitations"])] for r in rows]

body = ''.join('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in row) + '</tr>' for row in cells)

(DOCS / "capability-matrix.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Mr Auditor UAE business capability matrix</title><style>body{font:14px system-ui;margin:24px;color:#17212b}h1{font-size:24px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #d7dce2;vertical-align:top;text-align:left}th{background:#edf2f6;position:sticky;top:0}</style><h1>Mr Auditor · 100 UAE business workstreams</h1><p>Connected bounded implementations and existing-engine improvements. Schedules and engine adapters do not establish full financial/legal acceptance.</p><p>Cases 46, 48 and 49 remain blocked for their full requested scope; every case retains explicit limitations. New cases 51–100 have real approved-schedule HTTP execution checks. Full legal/sector acceptance is not established.</p><table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headings)+'</tr></thead><tbody>'+body+'</tbody></table></html>', encoding='utf-8')

canvas = '''import {H1,H2,Text,Table,Stack,TextInput,useState} from 'cursor/canvas';

const rows=__ROWS__;

const engines=__ENGINES__;

export default function UAECaseMatrix(){const [query,setQuery]=useState('');const visible=rows.filter(r=>r.join(' ').toLowerCase().includes(query.toLowerCase()));return <Stack style={{padding:24,gap:16}}>

<H1>Mr Auditor: UAE business workstreams</H1><Text>100 connected case entries; existing calculation engines are reused. Full specialist acceptance is not established for all cases. Cases 46, 48 and 49 remain blocked for their full requested scope.</Text>

<Text tone="secondary" size="small">Source: current repository manifest and actual synthetic HTTP/browser receipts. Entry-path verification does not establish legal correctness or production readiness.</Text>

<TextInput value={query} onChange={setQuery} placeholder="Filter by case, engine or blocker" />

<Text tone="secondary" size="small">{visible.length} matching cases</Text>{visible.length>0&&<Table headers={__HEADINGS__} rows={visible} stickyHeader />}

<H2>Connected engine responsibilities</H2><Table headers={['Engine','Responsibility','Repository services','Scope']} rows={engines} />

<H2>Evidence and outstanding controls</H2><Text>Actual browser verification covers synthetic record ingestion, assistant collection, shared lease calculation, source inspection and an unposted workpaper. Permission inheritance prevents a general paper reader from gaining access to IFRS evidence. Current e-invoicing readiness requires MD197/2026 adoption review. Notification delivery and restricted AML case storage remain incomplete.</Text>

</Stack>}

'''.replace('__ROWS__', json.dumps(cells)).replace('__HEADINGS__',json.dumps(headings)).replace('__ENGINES__',json.dumps([[e['id'],e['responsibility'],e['implementation'],e['state']] for e in engines]))

target = Path.home() / ".cursor/projects/c-Indian-Servers-TheAuditor/canvases/mr-auditor-uae-business-cases.canvas.tsx"

target.write_text(canvas, encoding="utf-8")

print(json.dumps({"cases": len(rows), "engines": len(engines), "blocked_full_scope": [r['id'] for r in rows if r['completion_status']=='Blocked'], "canvas": str(target)}))


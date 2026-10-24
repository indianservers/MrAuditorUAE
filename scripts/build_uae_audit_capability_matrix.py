"""Publish the 01â€“50 scope matrix from inspected capabilities and real test receipts."""

import csv
import html
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/uae-audit-implementation"
EVIDENCE = DOCS / "evidence"
rows = json.loads((DOCS / "capability-manifest.json").read_text(encoding="utf-8"))
assert [r["id"] for r in rows] == list(range(1, 51))


def receipt(filename):
    tree = ET.parse(EVIDENCE / filename)
    cases = tree.findall(".//testcase")
    failed = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {"file": filename, "tests": len(cases), "passed": len(cases) - failed - skipped,
            "failed": failed, "skipped": skipped,
            "skip_reasons": sorted({c.find("skipped").get("message", "") for c in cases
                                    if c.find("skipped") is not None})}


verification = {"backend_unit_and_calculation_regression": receipt("unit-results.xml"),
                "backend_broad_integration": receipt("integration-results.xml"),
                "backend_final_focused_integration": receipt("final-focused-results.xml"),
                "backend_latest_integration": receipt("post-fix-integration-retest.xml"),
                "backend_intermediate_run": receipt("post-fix-integration-results.xml"),
                "backend_final_ml_financial": receipt("ml-financial-final-results.xml"),
                "backend_final_label_gate": receipt("final-label-gate-results.xml"),
                "backend_final_extension_unit": receipt("final-extension-unit-results.xml"),
                "backend_restricted_diligence": receipt("restricted-diligence-results.xml"),
                "counts_overlap": True,
                "integration_boundary_doubles": ["malware scanner", "broker dispatch"],
                "real_execution": ["PostgreSQL", "HTTP services", "private evidence objects",
                                   "job processors", "TensorFlow.js CPU fitting/inference"],
                "new_browser_scenario": "Not executed; UI type/build/component checks and real backend workflow checks were executed",
                "production_qualified": False}
verification["intermediate_run_note"] = (
    "Three intermediate setup rejections occurred while shared tax publication-attestation rules/fixtures changed. "
    "The strict source gate was retained. Consult backend_latest_integration for the subsequent retest; "
    "counts and intermediate failure receipts are preserved."
)
frontend = json.loads((EVIDENCE / "frontend-unit-results.json").read_text(encoding="utf-8"))
verification["frontend_unit"] = {"tests": frontend["numTotalTests"],
                                  "passed": frontend["numPassedTests"],
                                  "failed": frontend["numFailedTests"]}
verification["backend_types"] = (EVIDENCE / "backend-types.txt").read_text().strip()
verification["frontend_build"] = "passed" if "prerendered as static content" in (EVIDENCE / "frontend-build.txt").read_text(encoding="utf-8", errors="replace") else "inspect receipt"
ml_text = (EVIDENCE / "ml-runtime-tests.txt").read_text(encoding="utf-8", errors="replace")
verification["local_ml_runtime"] = {"receipt": "ml-runtime-tests.txt", "passed": "pass 5" in ml_text,
                                    "scope": "Synthetic pipeline, CPU, hashes/schema, queue bounds and tensor ownership; not an accuracy benchmark"}
(DOCS / "verification-summary.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
with (DOCS / "capability-matrix.csv").open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows([{**r, "workflows": "; ".join(r["workflows"])} for r in rows])

esc = html.escape
counts = {s: sum(r["implementation_status"] == s for r in rows)
          for s in ["Scoped core", "Partial", "Evidence only"]}
body = "".join(
    '<tr data-status="' + r["implementation_status"] + '"><td>' + str(r["id"]) + '</td><td>' +
    esc(r["use_case"]) + '</td><td>' + r["implementation_status"] + '</td><td>' +
    esc(r["deterministic_engines"]) + '<br><small>' + esc(", ".join(r["workflows"])) + '</small></td><td>' +
    esc(r["ml_execution_mode"] or "Not required") + '<br><small>' + esc(r["ml_note"]) + '</small></td><td>' +
    esc(r["language_model_dependency"]) + '</td><td>' + esc(r["evidence_approval_status"]) + '</td><td>' +
    esc(r["actual_verification_results"]) + '</td><td>' + esc(r["remaining_blockers"]) + '</td></tr>' for r in rows
)
page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TheAuditor: 01â€“50 implementation and verification</title><style>body{font:14px/1.55 system-ui;margin:30px;color:#20242b;background:#fafafa}h1{font-size:24px}h2{font-size:19px}table{border-collapse:collapse;background:white;width:100%}th,td{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd}th{background:#eee;position:sticky;top:0}td{min-width:160px}td:first-child{min-width:25px}td:last-child{min-width:320px}small{color:#555}input,select{padding:10px;margin:8px 14px 16px 0}input{width:320px}.scroll{overflow:auto}.stats{display:flex;gap:20px}.stats div{background:#eee;padding:14px}.notice{padding:16px;background:#eceff1}li{margin:7px 0}</style><h1>TheAuditor Â· Use cases 01â€“50</h1><p>25 October 2026 Â· implemented scoped extensions and actual verification Â· no production release</p><p class="notice"><b>The full 50-use-case plan is not complete.</b> This delivery adds 23 bounded audit procedures, strengthens local ML execution/provenance and connects retained engine results to the command centre. Remaining engineering, domain-content and external-service qualification are listed per use case.</p><div class="stats">COUNTS</div><p>Scoped core means a dedicated bounded workflow exists; partial means material engineering/qualification remains; evidence only means generic workpapers/checklists. No category means full legal or production readiness.</p><h2>What works without external AI credentials</h2><ul><li>Deterministic calculations/reconciliations, source-linked evidence, independent review, exports and the new audit workflows.</li><li>Explicit rules/statistical baselines. Explicit diagnostic mode produces a diagnostic result and no model score.</li><li>TensorFlow.js CPU inference when an approved compatible private artifact exists. Synthetic real fitting/inference was tested; no real-client quality or production promotion is claimed.</li></ul><p>A configured OpenAI-compatible gateway is needed only for optional language-model explanations/drafts. Diagnostic gateway responses are labelled. Account suggestions never determine VAT treatment or tax deductibility.</p><h2>Verification receipts</h2>VERIFICATION<p>Counts overlap and must not be added. Integration tests use real services/objects/job processors, with explicit scanner and dispatch doubles. No new browser end-to-end scenario was executed.</p><h2>Complete capability matrix</h2><select id="status"><option>All</option><option>Scoped core</option><option>Partial</option><option>Evidence only</option></select><input id="q" placeholder="Search case, workflow, engine or blocker"><p id="count">50 of 50 use cases</p><div class="scroll"><table><thead><tr><th>#</th><th>Use case</th><th>Scope</th><th>Deterministic engines / workflows</th><th>ML execution mode if relevant</th><th>Language-model dependency</th><th>Evidence / approval</th><th>Verification scope</th><th>Remaining blockers</th></tr></thead><tbody>ROWS</tbody></table></div><h2>Next engineering priorities</h2><ol><li>Finish cross-entity intercompany/consolidation, complete disclosure coverage, complex contract schedules and group release controls.</li><li>Complete payroll gross/net, alternative benefit schemes, dedicated property VAT, tax retention/holds and the unified FTA request package.</li><li>Build restricted AML case management, qualified screening/identity feeds and operational rescreening/reminder delivery.</li><li>Qualify source connectors, sector edge cases, real-client datasets, scanner/recovery/load behavior and controlled pilot acceptance.</li></ol><script>function update(){let n=0;const s=document.querySelector('#status').value,q=document.querySelector('#q').value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>{const yes=(s==='All'||r.dataset.status===s)&&r.innerText.toLowerCase().includes(q);r.hidden=!yes;if(yes)n++});document.querySelector('#count').textContent=n+' of 50 use cases'}document.querySelector('#status').addEventListener('change',update);document.querySelector('#q').addEventListener('input',update);</script></html>'''
verification_items = []
for name, item in verification.items():
    if isinstance(item, dict) and "tests" in item:
        suffix = " (historical intermediate run; see later retest)" if name == "backend_intermediate_run" else ""
        verification_items.append(f"{name}: {item['passed']} passed; {item['failed']} failed; {item.get('skipped', 0)} skipped" + suffix)
verification_items += ["Backend types: " + verification["backend_types"],
                       "Frontend production build: " + verification["frontend_build"],
                       "Local ML runtime: five passing pipeline/runtime tests; no accuracy benchmark"]
page = page.replace("COUNTS", "".join(f"<div><b>{v}</b> {k}</div>" for k, v in counts.items())).replace("ROWS", body).replace("VERIFICATION", "<ul>" + "".join("<li>" + esc(v) + "</li>" for v in verification_items) + "</ul>")
(DOCS / "capability-matrix.html").write_text(page, encoding="utf-8")
if len(sys.argv) > 1:
    destination = Path(sys.argv[1])
    (destination / "uae-audit-capability-matrix.html").write_text(page, encoding="utf-8")
    canvas = '''import {H1,H2,Text,Table,Stack,Row,useHostTheme,useState} from "cursor/canvas";
const data=DATA;
export default function Capabilities(){const t=useHostTheme();const [status,setStatus]=useState('All');const [query,setQuery]=useState('');const visible=data.filter(r=>(status==='All'||r.implementation_status===status)&&JSON.stringify(r).toLowerCase().includes(query.toLowerCase()));return <Stack style={{padding:24,background:t.bg.editor,color:t.text.primary}}><H1>TheAuditor: 01â€“50 implementation status</H1><Text>The full plan is not complete. 23 bounded procedures were added; all remaining gaps are explicit. No production release or real-client model qualification is claimed.</Text><H2>Independent execution paths</H2><Text>Deterministic engines and explicit baselines work without external AI credentials. Trained local inference requires approved compatible artifacts; a synthetic CPU pipeline was verified. Optional explanations/drafts require a configured language gateway, with diagnostic responses labelled.</Text><Row><select aria-label="Scope filter" value={status} onChange={e=>setStatus(e.target.value)} style={{background:t.bg.elevated,color:t.text.primary}}>{['All','Scoped core','Partial','Evidence only'].map(s=><option key={s}>{s}</option>)}</select><input aria-label="Search cases" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search workflows and blockers" style={{padding:8,background:t.bg.elevated,color:t.text.primary}}/></Row><Text>{visible.length} of 50 cases. Source: local code and verification receipts, 25 October 2026.</Text>{visible.length>0&&<Table headers={['# / use case','Scope','Engines / workflows','ML mode','Language model','Evidence / approval','Verification scope','Remaining blockers']} rows={visible.map(r=>[`${r.id}. ${r.use_case}`,r.implementation_status,r.deterministic_engines+'; '+r.workflows.join(', '),r.ml_execution_mode||'Not required',r.language_model_dependency,r.evidence_approval_status,r.actual_verification_results,r.remaining_blockers])} striped/>}<Text>Scoped core is bounded implementation, not legal/production readiness. Tests of shared infrastructure do not establish every specialist scenario. No new browser end-to-end scenario was executed.</Text></Stack>}
'''.replace("DATA", json.dumps(rows))
    (destination / "uae-audit-capability-matrix.canvas.tsx").write_text(canvas, encoding="utf-8")
print(json.dumps({"use_cases": len(rows), "scope_counts": counts, "verification": verification}))

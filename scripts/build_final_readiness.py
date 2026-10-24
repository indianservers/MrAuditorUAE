"""Evidence-linked engineering readiness registers; unknown coverage never becomes complete."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.connectors.catalogue import PROVIDERS, REQUIREMENTS
from app.modules.connectors.native_config import EDITIONS, SOURCE_DOCS
from app.modules.ml.foundation import TASKS

OUT = ROOT / "docs/engine-strengthening/phase5"
OUT.mkdir(exist_ok=True)


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def results(name):
    path = OUT / name
    if not path.exists():
        return {"status": "not_run"}
    cases = list(ET.parse(path).getroot().iter("testcase"))
    failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {"total":len(cases), "passed":len(cases)-len(failed)-skipped, "failed":len(failed), "skipped":skipped,
        "failures":[c.attrib.get("classname", "")+"::"+c.attrib.get("name", "") for c in failed]}


latest = {}
report_order = ["backend-results.xml", "focused-integration-results.xml", "unit-results.xml", "filing-integration-results.xml", "final-integration-results.xml", "connector-database-results.xml"]
for name in report_order:
    path = OUT / name
    if not path.exists():
        continue
    for case in ET.parse(path).getroot().iter("testcase"):
        identifier = case.attrib.get("classname", "") + "::" + case.attrib.get("name", "")
        status = "failed" if case.find("failure") is not None or case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
        latest[identifier] = {"id":identifier,"status":status,"report":name}
write("test-verification.json", {"method":"Latest retained result per test across initial full campaign and post-fix targeted/unit reruns; not a second uninterrupted full campaign", "items":list(latest.values())})


limitations = {
    "E01":"Primary-source retention, professional applicability and effective-date approval remain mandatory; no blanket legal certification.",
    "E02":"Qualified OCR/templates and completeness of real client documents; corrupt/quarantined evidence is not usable.",
    "E03":"Client population completeness and account mappings need independent controls; imports are not live sync.",
    "E04":"Advanced supply/advance cases remain bounded; no live authority filing or acceptance.",
    "E05":"Client adjustments, elections, tax basis and actual rule adoption require professional review.",
    "E06":"Unresolved activity/counterparty/substance facts block qualification; no automatic eligibility conclusion.",
    "E07":"Licensed comparable data and qualified economic judgments; no inferred market research.",
    "E08":"Unsupported special blending and incomplete MNE facts remain blocked; no invented zero tax.",
    "E09":"Complete disclosure checklist, client mappings/policies, unsupported accounting cases and final release qualification.",
    "E10":"Statistical projection/evaluation, arbitrary strata/replacements and professional audit opinion are not delivered.",
    "E11":"Client-trained quality, independent labels and approved thresholds remain unqualified despite synthetic CPU tests.",
    "E12":"Advanced FX, credit, advance, dispute and write-off lifecycle remains incomplete.",
    "E13":"Supplier-master/bank ownership verification and actual payment-release workflow remain incomplete.",
    "E14":"Full treasury-to-accounting/tax bridges and live bank connectivity; explicit fees/FX bridges require review.",
    "E15":"Advanced asset/lease/impairment cases and client assumptions need separate qualification.",
    "E16":"Jurisdiction-specific payroll/pension rules and payroll runs remain bounded; not a complete payroll product.",
    "E17":"Advanced inventory costing/production and complete client stock populations remain dependencies.",
    "E18":"Final group release, advanced ownership/FX/consolidation cases and group tax bridges remain bounded.",
    "E19":"Obligations require explicitly reviewed rules/facts; automatic discovery of all statutory obligations is not implemented. Reminders are in-app only; no authority submission.",
    "E20":"Production role assignments, record retention, scanner deployment, recovery and professional quality gates require operational approval.",
    "E21":"Local gateway is not configured; diagnostic narratives are not independent verification. Unrestricted execution and self-approval are excluded.",
    "E22":"No live provider is qualified here. Tenant consent, provider edition, scopes, source totals and sandbox/live qualification remain prerequisites.",
}
connections = json.loads((ROOT / "docs/mr-auditor-business/engine-connection-map.json").read_text())
engines = []
for item in connections["engines"]:
    eid = item["id"]
    phase = 1 if eid in {"E01","E02","E03","E20"} else 2 if eid in {"E04","E05","E06","E07","E08"} else 3 if eid in {"E09","E15","E16","E17","E18"} else 4 if eid in {"E10","E11","E12","E13","E14"} else 5
    engines.append({"id":eid,"name":item["responsibility"],"classification":"Implemented with limitations",
        "runtime_status":"bounded implementation; see actual test reports, not an uptime certification",
        "supported_capabilities":item["implementation"],"data_readiness":"synthetic verification; client data completeness not qualified",
        "rule_model_verification":"explicit reviewed inputs; see source-policy-model-register.json",
        "evidence_approval_controls":"tenant/engagement permissions, versioned evidence, separate preparer/reviewer and stale-source guards; operation-specific limits in phase report",
        "verification_evidence":[f"../phase{phase}/README.md", "backend-results.xml", "focused-integration-results.xml"],
        "remaining_limitations":limitations[eid]})
selectors = {
    "E01":["regulatory","jurisdiction","foundation"],"E02":["document","evidence","native_workflow_sources"],
    "E03":["pipeline","foundation","accounting_connectors"],"E04":["vat","phase7"],"E05":["phase6","tax_"],
    "E06":["qfzp","phase6"],"E07":["phase8","relationship"],"E08":["dmtt","phase9"],"E09":["phase5","accounting_strengthening"],
    "E10":["phase4","audit_operations"],"E11":["analytics","ml_","foundation"],"E12":["audit_operations","shared_audit","practice_audit"],
    "E13":["audit_operations","practice_audit"],"E14":["audit_operations","country_workflows","supporting_bank"],
    "E15":["accounting_strengthening","phase5"],"E16":["payroll","benefit","phase5"],"E17":["inventory","accounting_strengthening"],
    "E18":["consolidation","intercompany","group"],"E19":["final_foundations","phase10"],"E20":["phase4","foundation","tenant_isolation"],
    "E21":["phase11","final_foundations"],"E22":["connector","native_workflow_sources","final_foundations"],
}
for engine in engines:
    matched = [r for r in latest.values() if any(s in r["id"].lower() for s in selectors[engine["id"]])]
    engine["actual_verification"] = {"index":"test-verification.json","selectors":selectors[engine["id"]],
        "passed":sum(r["status"]=="passed" for r in matched),"failed":sum(r["status"]=="failed" for r in matched),
        "skipped":sum(r["status"]=="skipped" for r in matched),"meaning":"Keyword-indexed technical tests, not complete engine acceptance or client-data qualification"}
write("engine-readiness.json", {"production_ready":False,"engines":engines,"dependency_map":
    "E01/E02/E03 inputs -> E04-E08 tax and E09/E15-E18 accounting -> E10-E14 audit/operations -> E19 obligations/E20 review; E21 authorized orchestration and E22 controlled external inputs",
    "cycle_prevention":"E09 pre-tax profile -> E05 -> separate E09 post-tax profile; lineage traversal detects cycles and stale references. Not every execution calls every engine."})
write("remaining-blockers.json", {"production_release_blocked":True,"items":[
    {"id":"scope-"+e["id"],"affected_engines":[e["id"]],"affected_workflows":e["name"],
        "blocker":e["remaining_limitations"],"required_resolution":"Approve bounded production scope and supply the missing evidence/implementation/qualification described here and in the linked phase report"} for e in engines
] + [{"id":"catalogue-200","affected_engines":[e["id"] for e in engines],"affected_workflows":"Authoritative use cases 001-200",
      "blocker":"Definitions and authoritative ID mapping were not supplied/found","required_resolution":"Provide the exact 200-case catalogue, then reconcile and verify each defined workflow"},
     {"id":"operations","affected_engines":["E02","E20","E21","E22"],"affected_workflows":"Production storage, credentials, scanning, recovery and live integrations",
      "blocker":"Local synthetic verification does not qualify deployment or live providers","required_resolution":"Complete operations.md and existing release gates with the final release artifacts"}]})
write("scenario-register.json", {"synthetic_only":True,"scenarios":[
    {"id":"A","name":"UAE trading company","classification":"Implemented with limitations","evidence":["../phase2/trading-workflow.json","../phase3/operating-company-workflow.json","../phase4/revenue-cycle.json","backend-results.xml"],"limitations":"Separate retained connected demonstrations, not a newly approved complete client reporting pack; all source and professional release guards remain applicable"},
    {"id":"B","name":"Free-zone services","classification":"Implemented with limitations","evidence":["../phase2/connected-workflow.json","backend-results.xml"],"limitations":"QFZP/CT/TP components require reconciled approved activity/substance facts; no new complete free-zone evidence-pack certification"},
    {"id":"C","name":"Multi-entity group","classification":"Implemented with limitations","evidence":["../phase3/group-workflow.json","../phase3/intercompany-workflow.json","backend-results.xml"],"limitations":"Draft consolidation and separate tax/DMTT scope; advanced group tax bridges and final group release remain incomplete"},
    {"id":"D","name":"AI evidence to approved draft action","classification":"Implemented with limitations","evidence":["backend-results.xml","focused-integration-results.xml","configuration-status.json"],"test":"tests.phase11.test_workflows::test_investigation_permissions_resume_proposal_and_stale_approval","limitations":"Actual authorized retrieval and draft execution; narrative uses explicitly diagnostic provider, no live gateway or professional conclusion"},
    {"id":"E","name":"Source correction","classification":"Implemented with limitations","evidence":["../phase4/audit-source-revision.json","../phase4/procurement-bank-revision.json","filing-lifecycle.json","backend-results.xml"],"limitations":"Stale guards and reviewed replacements; no global automatic recalculation of every draft"}
]})

candidate = json.loads((ROOT / "docs/uae-audit-implementation/capability-manifest.json").read_text())
write("recognized-50-case-assessment.json", {"namespace":"existing-uae-audit-implementation-50; not assumed to equal global 01-200 IDs",
    "items":[{**c,"classification":"Implemented with limitations" if c["implementation_status"] in {"Partial","Scoped core"} else "Blocked",
        "verification_scope":"representative engine regressions; individual case qualification not established",
        "connector_dependency":"controlled imports available; live-provider qualification absent",
        "current_verification_evidence":"backend-results.xml; see case-specific retained evidence in original manifest"} for c in candidate]})
write("use-cases-001-200.json", {"authoritative_catalogue_found":False,"recognized_catalogues":["50-case UAE audit manifest","50-case UAE business manifest","165-module jurisdiction registry"],
    "mapping_rule":"No assumption that different catalogues share IDs; definitions 001-200 must be supplied before authoritative reconciliation",
    "items":[{"id":i,"classification":"Blocked","definition":None,"relevant_engines":[],
        "actual_implementation_status":"not assessable without authoritative definition",
        "deterministic_calculation_availability":"unresolved","ml_execution_mode":"unavailable",
        "language_model_dependency":"unresolved","connector_dependency":"unresolved",
        "evidence_and_approval_controls":"not assessed for undefined case; shared engine controls do not establish case completion",
        "verification_evidence":[],"remaining_blockers":["Authoritative catalogue definition and mapping required"]} for i in range(1,201)]})

auth = {"zoho":"OAuth client/refresh-token flow, region and organization binding", "tally":"authorized local read-only HTTP/XML agent and enrolled company fingerprint", "file":"authorized file upload, no provider credentials",
    "quickbooks":"Online OAuth; Desktop requires explicit partner SDK/API contract", "xero":"OAuth read scopes and tenant binding", "netsuite":"edition-specific OAuth/token configuration", "sap-b1":"Service Layer session credentials", "sap-s4":"approved basic/bearer credential and released endpoint", "dynamics":"Entra client credentials or explicit partner interface", "busy":"vendor-approved partner contract credentials", "marg":"vendor-approved partner contract credentials"}
write("connector-register.json", {"live_qualification_performed":False,"items":[{**p,"classification":"Implemented with limitations","authorization_method":auth[p["id"]],"supported_operations":["read extraction","controlled GL/TB/COA import"],
    "write_scope":"no remote financial mutation or filing", "data_freshness":"per-run health and checkpoints; not inferred from reachability",
    "environment":"controlled synthetic tests; authorized live account not qualified", "configuration_requirements":REQUIREMENTS[p["id"]],"editions":EDITIONS.get(p["id"],[]),"provider_reference":SOURCE_DOCS.get(p["id"]),
    "verification_evidence":["focused-integration-results.xml","backend-results.xml"],"known_limitations":"mock transports test failure handling only; independent count/balance controls and real edition qualification remain required"} for p in PROVIDERS]})
write("source-policy-model-register.json", {"automatic_legal_policy_adoption":False,"primary_references":[
    {"url":"https://mof.gov.ae/en/public-finance/tax/corporate-tax/","purpose":"CT deadline reference, no automatic entity applicability or extension inference"},
    {"url":"https://tax.gov.ae/en/faq.aspx?keyword=When+are+registered+businesses+required+to+file+VAT+returns%3F","purpose":"VAT deadline reference; authority-assigned periods and extensions require retained evidence"},
    {"url":"https://www.tensorflow.org/js/guide/platform_environment","purpose":"JavaScript CPU/native runtime distinction"}],
    "retained_phase_registers":["../phase1/README.md","../phase2/rule-source-register.json","../phase3/source-policy-register.json","../phase4/source-policy-register.json"],
    "deadline_policy":"No hardcoded new legal deadline; approved evidence, explicit trigger, validity, timezone, convention and rule version required for calculated obligations",
    "models":[{"task":t,"runtime":"TensorFlow.js Node JavaScript CPU","test_evidence":"tensorflow-results.txt","training_data":"labeled synthetic fixtures in verification only","client_validation":"not established","deployment":"per-model independent approval required; no automatic activation","language_dependency":False} for t in TASKS],
    "language_model":"separate OpenAI-compatible gateway; local presence-only configuration is in configuration-status.json; diagnostic output is not verification"})
write("verification.json", {"reports":{name:results(name) for name in ["backend-results.xml","focused-integration-results.xml","unit-results.xml","filing-integration-results.xml","final-integration-results.xml","connector-database-results.xml","frontend-results.xml"]},
    "consolidated_backend_results":{"passed":sum(r["status"]=="passed" for r in latest.values()),"failed":sum(r["status"]=="failed" for r in latest.values()),"skipped":sum(r["status"]=="skipped" for r in latest.values()),"method":"Latest result per test, full initial run plus post-fix reruns; see test-verification.json"},
    "tensorflow_report":"tensorflow-results.txt","restore_report":"restore-results.json","production_readiness":False,
    "sha256":{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="verification.json"}})
print("Wrote 22 engine assessments, 200 explicitly blocked catalogue slots, recognized 50-case assessment and operational registers")

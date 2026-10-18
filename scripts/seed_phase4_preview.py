"""Explicitly synthetic browser fixtures through real APIs. Does not reset databases."""
import json
import os
import uuid
from pathlib import Path

import httpx


def main():
    raise SystemExit("Legacy preview seeding is disabled: use the guarded Phase 7 seed-demo command against its explicit demo database and tenant.")
    if os.getenv("DEMO_SEED") != "1":
        raise SystemExit("Set DEMO_SEED=1 against a disposable local preview only")
    with httpx.Client(base_url="http://127.0.0.1:58002/api/v1",timeout=60) as c:
        def call(method,path,**kwargs):
            r=c.request(method,path,**kwargs)
            if r.status_code>=400:
                raise RuntimeError(f"{method} {path}: {r.status_code} {r.text}")
            return r.json()
        r=c.post("/auth/bootstrap",headers={"X-Bootstrap-Secret":"test-bootstrap-secret"},json={"email":"admin@example.com","password":"test-strong-password-123","tenant_name":"SYNTHETIC Phase 4 demonstration firm"})
        if r.status_code==409:
            tokens=call("POST","/auth/login",data={"username":"admin@example.com","password":"test-strong-password-123"})
        else:
            r.raise_for_status();tokens=r.json()
        c.headers["Authorization"]="Bearer "+tokens["access_token"]
        tenant=call("GET","/tenants")[0]["id"];c.headers["X-Tenant-ID"]=tenant
        customer=call("POST","/clients",json={"code":"P4-"+uuid.uuid4().hex[:8],"name":"SYNTHETIC — Gulf Demonstration LLC"})
        entity=call("POST","/entities",json={"client_id":customer["id"],"name":"SYNTHETIC Trading Entity","country":"AE","jurisdiction":"Synthetic UAE test","functional_currency":"AED","presentation_currency":"AED"})
        period=call("POST","/financial-periods",json={"entity_id":entity["id"],"start_date":"2026-01-01","end_date":"2026-12-31"})
        engagement=call("POST","/engagements",json={"entity_id":entity["id"],"period_id":period["id"],"name":"SYNTHETIC — FY2026 External Audit","engagement_type":"External Audit"})
        base="/engagements/"+engagement["id"]+"/audit"
        roles=call("GET","/admin/roles")["items"]
        identities={}
        for name,email in [("Auditor","auditor@phase4.example"),("Audit Manager","manager@phase4.example"),("Audit Partner","partner@phase4.example"),("Client Accountant","client@phase4.example")]:
            role=next(r for r in roles if r["name"]==name)
            users=call("GET","/admin/users",params={"search":email})["items"]
            if not users:
                invitation=call("POST","/admin/invitations",json={"email":email,"role_ids":[role["id"]]})
                call("POST","/admin/invitations/redeem",json={"token":invitation["token"],"password":"synthetic-password-123"})
                users=call("GET","/admin/users",params={"search":email})["items"]
            member=users[0]
            if name.startswith("Client"):
                call("POST","/admin/client-access",json={"membership_id":member["id"],"client_id":customer["id"]})
            else:
                call("POST",base+"/team",json={"membership_id":member["id"],"role_id":role["id"]})
            identities[name]={"email":email,"user_id":member["user_id"]}
        def audit(kind,body,reference):
            return call("POST",base+"/"+kind,json={"reference":reference,"title":{"risks":"Revenue cut-off and occurrence","materiality":"PBT benchmark assessment","working-papers":"Revenue testing and evidence evaluation","requests":"Sales invoice and delivery support"}.get(kind,"SYNTHETIC "+kind.replace("-"," ").title()),"body":body})
        acceptance=audit("acceptance",{k:"Synthetic documented response; requires independent human review" for k in ["background","ownership","operations","ethics","conflicts","management_integrity","capability","staffing","previous_auditor","scope_and_terms"]},"AC-001")
        independence=audit("independence",{"financial_interests":False,"relationships":False,"other_services":False,"threats":"No threats disclosed in synthetic declaration","safeguards":"Subject to partner review","expires_on":"2027-12-31"},"IN-001")
        planning=audit("planning",{"strategy":"Risk-focused statutory audit strategy for synthetic trading entity","scope":"FY2026 financial statements; no opinion generated","timetable":"Planning → fieldwork → independent review","methodology_version":"Draft original methodology v1","standards_edition":"2026 handbook; applicability subject to human validation"},"PL-001")
        mat=audit("materiality",{"benchmark":"profit_before_tax","benchmark_amount":"10000000","selected_percentage":"5","performance_percentage":"70","trivial_percentage":"5","benchmark_source":"SYNTHETIC benchmark supplied for demonstration","rationale":"Illustrative user-selected percentages; not ISA-prescribed","effective_date":"2026-10-18"},"MAT-001")
        risk=audit("risks",{"level":"assertion","inherent_risk":"high","control_risk":"not_assessed","significant":True,"fraud":False,"assertions":["occurrence","cut_off"],"area":"Revenue","response":"Trace year-end invoices to delivery documentation and subsequent receipts","narrative":"Synthetic risk prepared by a human test user; no factual allegation"},"R-001")
        program=audit("programs",{"methodology_version":"Original draft v1","objective":"Revenue recognition and completeness","area":"Revenue","sources":[{"kind":"record","id":risk["id"]}]},"G-001")
        procedure=audit("procedures",{"methodology_version":"Original draft v1","objective":"Test occurrence and cut-off","area":"Revenue","instructions":"Inspect original supporting invoice and dispatch documentation","required_evidence":"Invoice, dispatch record and authorization","owner_id":identities["Auditor"]["user_id"],"due_date":"2026-12-31","sources":[{"kind":"record","id":risk["id"]}]},"G-010")
        paper=audit("working-papers",{"folder":"Revenue","area":"Revenue","assertions":["occurrence","cut_off"],"sections":[{"heading":"Objective","text":"Evaluate recorded revenue against original supporting evidence."},{"heading":"Work performed","text":"Synthetic draft for browser verification. Original evidence must be inspected by the auditor."}],"conclusion":"Draft for independent human review; no sufficiency determination made by AI","sources":[{"kind":"record","id":risk["id"]},{"kind":"record","id":procedure["id"]}]},"G-WP-001")
        evidence=audit("evidence",{"category":"Sales invoice","retain_until":"2036-12-31","sources":[{"kind":"record","id":paper["id"]}]},"EV-001")
        call("POST",base+"/evidence-files/"+evidence["id"],files={"file":("SYNTHETIC-invoice.csv",b"invoice,amount\nSYNTHETIC-001,12500.00\n","text/csv")})
        finding=audit("findings",{"finding_type":"missing_evidence","severity":"medium","area":"Revenue","narrative":"Original dispatch documentation has been requested in this synthetic workflow","sources":[{"kind":"record","id":evidence["id"]}]},"F-001")
        note=audit("review-notes",{"target_id":paper["id"],"assigned_reviewer":identities["Audit Partner"]["user_id"],"narrative":"Clarify the population reconciliation and source documentation references"},"RN-001")
        completion=audit("completion",{"subsequent_events":"Pending documented human procedures","going_concern":"Pending human consideration","unadjusted_misstatements":"Pending human evaluation","human_evidence_assessment":"Draft only; outstanding records prevent engagement completion"},"J-001")
        request=audit("requests",{"client_id":customer["id"],"question":"Upload the original sales invoice and delivery support for the selected transaction.","due_date":"2026-12-31","narrative":"Internal planning context must never be exposed to client users"},"PBC-001")
        call("POST",base+"/records/"+request["id"]+"/actions",json={"version":request["version"],"action":"SENT","comments":"Synthetic request issued by authorized auditor"})
        ai=call("POST",base+"/ai-actions",json={"task":"financial_statement_risks","sources":[{"kind":"record","id":risk["id"]}]})
        csv_data=b"Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n100,Cash,OPEN,2026-01-01,10.10,0,L1,true,false,Opening\n300,Equity,OPEN,2026-01-01,0,10.10,L2,true,false,Opening\n500,Expense,1,2026-12-26,100.20,0,L3,false,true,Adjustment\n100,Cash,1,2026-12-26,0,100.20,L4,false,true,Adjustment\n"
        options={"client_id":customer["id"],"entity_id":entity["id"],"period_id":period["id"],"expected_rows":4,"expected_debit":"110.30","expected_credit":"110.30","source_complete":True}
        batch=call("POST","/accounting/imports",data={"options":json.dumps(options)},files={"file":("SYNTHETIC-ledger.csv",csv_data,"text/csv")})
        call("POST","/accounting/imports/"+batch["id"]+"/validate")
        call("POST","/accounting/imports/"+batch["id"]+"/commit")
        detail=call("GET","/accounting/imports/"+batch["id"])
        sample=call("POST",base+"/select-sample",json={"snapshot_id":detail["snapshot_id"],"method":"random","size":2,"seed":42})
        testing=audit("testing",{"sample_id":sample["id"],"population_completeness":"Synthetic source row counts reconciled","reconciliation":"Four-row synthetic ledger committed through the accounting engine","methodology_rationale":"Human-selected illustrative sample size, no statistical assurance inferred","conclusion":"Draft observations; original evidence requires professional inspection","sources":[{"kind":"sample","id":sample["id"]},{"kind":"record","id":procedure["id"]}]},"T-001")
        fixture={"synthetic":True,"tenant_id":tenant,"client_id":customer["id"],"entity_id":entity["id"],"period_id":period["id"],"engagement_id":engagement["id"],"paper_id":paper["id"],"risk_id":risk["id"],"identities":identities}
        target=Path(__file__).resolve().parents[1]/"docs/phase-4/browser-fixture.json"
        target.write_text(json.dumps(fixture,indent=2),encoding="utf-8")
        print("Seeded explicitly synthetic records and real invitation-based test identities; fixture saved")


if __name__=="__main__":main()

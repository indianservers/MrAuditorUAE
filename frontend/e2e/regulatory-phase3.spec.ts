import {test,expect,Page} from "@playwright/test";
import {readFileSync} from "node:fs";
const credentials=JSON.parse(readFileSync("../.local-runtime/qa-campaign/environment.local.json","utf8"));
async function login(page:Page,email:string) {
  await page.goto("/login");await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password",{exact:true}).fill(credentials.QA_PASSWORD);
  await page.getByRole("button",{name:"Sign in",exact:true}).click();await page.waitForURL("**/dashboard");
}
test("two real regulatory administrators propose, independently review and publish a version",async({page,browser})=>{
  await expect.poll(async()=>{try{return(await page.request.get("http://127.0.0.1:58009/health/ready")).status();}catch{return 0;}}).toBe(200);
  await login(page,"qa.admin@auditos.example");await page.goto("/settings");
  await page.getByLabel("Working country",{exact:true}).selectOption("AE");
  await page.goto("/settings/regulatory-rules");
  await page.getByText("Firm regulatory reference copies",{exact:true}).click();
  await page.getByLabel("Reference title",{exact:true}).fill("SYNTHETIC browser reference copy");
  await page.getByLabel("Source HTTPS URL").fill("https://mof.gov.ae/");
  await page.getByLabel("Source retrieved on").fill("2026-10-24");
  await page.getByLabel("Regulatory reference file").setInputFiles({name:"SYNTHETIC-rule.txt",mimeType:"text/plain",buffer:Buffer.from("SYNTHETIC workflow reference only; not official legislation")});
  const retained=page.waitForResponse(r=>r.url().endsWith("/regulatory/sources")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Retain scanned reference copy",exact:true}).click();
  const retainedResponse=await retained;expect(retainedResponse.status()).toBe(201);const copy=await retainedResponse.json();
  await page.getByRole("button",{name:"Propose new rule",exact:true}).click();
  const key=`AE-BROWSER-${Date.now()}`;
  const config={rule_key:key,country:"AE",title:"SYNTHETIC browser workflow rule — not legislation",
    description:"Synthetic attested metadata to verify application controls only, not legal correctness",framework:"IFRS",
    period_basis:"period_start",effective_from:"2026-01-01",effective_to:"2026-12-31",
    citations:[{authority:"SYNTHETIC source attestation",legislation:"SYNTHETIC only",url:"https://mof.gov.ae/",paragraph:"TEST",
      retrieval_status:"RETRIEVED",document_sha256:copy.sha256,source_document_id:copy.id,retrieved_on:"2026-10-24"}],
    input_requirements:["entity_type"],output_requirements:["reviewed_conclusion"],applicability:[],exceptions_and_elections:[],
    method:"checklist",rate:null,validation_status:"VALIDATED",professional_review_status:"REVIEWED",last_reviewed:"2026-10-24",
    amendment_reason:"SYNTHETIC application workflow fixture only, not a regulatory content release",expected_sequence:0};
  await page.getByLabel("Versioned rule configuration").fill(JSON.stringify(config,null,2));
  const creation=page.waitForResponse(r=>r.url().endsWith("/regulatory/rules")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Save immutable proposal"}).click();const created=await creation;
  expect(created.status()).toBe(201);const rule=await created.json();
  await page.getByLabel("Decision rationale").fill("SYNTHETIC self-review must be rejected by independent review controls");
  const denied=page.waitForResponse(r=>r.url().includes(`/rules/${rule.id}/decisions`));
  await page.getByRole("button",{name:"Record independent approval",exact:true}).click();expect((await denied).status()).toBe(403);
  const second=await browser.newContext();const reviewer=await second.newPage();await login(reviewer,"qa.role01@auditos.example");
  await reviewer.goto(`/settings/regulatory-rules?rule=${rule.id}`);
  await reviewer.getByLabel("Decision rationale").fill("SYNTHETIC independent review of the source metadata fixture only");
  await reviewer.getByLabel("Validation fixture cases (JSON)").fill(JSON.stringify([{id:"SYNTHETIC",kind:"checklist",expected_reference:"Independent synthetic company applicability case",period_start:"2026-01-01",period_end:"2026-12-31",facts:{entity_type:"company"},expected_applicability:"APPLICABLE"}]));
  const reviewed=reviewer.waitForResponse(r=>r.url().includes(`/rules/${rule.id}/decisions`));
  await reviewer.getByRole("button",{name:"Record independent approval",exact:true}).click();expect((await reviewed).status()).toBe(201);
  await page.goto(`/settings/regulatory-rules?rule=${rule.id}`);
  await page.getByLabel("Decision rationale").fill("SYNTHETIC controlled publication after independent application review");
  const published=page.waitForResponse(r=>r.url().includes(`/rules/${rule.id}/decisions`));
  await page.getByRole("button",{name:"Publish approved version",exact:true}).click();expect((await published).status()).toBe(201);
  await expect(page.getByText("PUBLISHED",{exact:true}).first()).toBeVisible();
  await page.screenshot({path:"../docs/phase3/evidence/regulatory-library.png",fullPage:true});
  await page.goto("/compliance/country");await expect(page.getByRole("heading",{name:"AE Compliance Workspace",exact:true})).toBeVisible();
  await page.screenshot({path:"../docs/phase3/evidence/country-compliance.png",fullPage:true});await second.close();
});

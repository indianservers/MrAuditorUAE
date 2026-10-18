import {test,expect,type Page} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {readFileSync,mkdirSync,writeFileSync} from "node:fs";
import {createHmac} from "node:crypto";
const demo=JSON.parse(readFileSync("../docs/phase-7/demo-manifest.json","utf8"));
const credentials=JSON.parse(readFileSync("../.local-runtime/phase7/demo-login.local.json","utf8"));
const operator=JSON.parse(readFileSync("../.local-runtime/phase12-operator.local.json","utf8"));
const shots="../docs/phase-12/screenshots";
mkdirSync(shots,{recursive:true});

function otp(secret:string){
  const bits=[...secret].map(c=>"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(c).toString(2).padStart(5,"0")).join("");
  const key=Buffer.from(bits.match(/.{8}/g)!.map(x=>parseInt(x,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const digest=createHmac("sha1",key).update(counter).digest();
  return String((digest.readUInt32BE(digest[19]&15)&0x7fffffff)%1000000).padStart(6,"0");
}
async function login(page:Page,email=demo.users[1].email,privileged=false){
  await page.goto("/login");await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password",{exact:true}).fill(privileged?operator.password:credentials.password);
  if(privileged)await page.getByLabel("Authenticator code (if enabled)").fill(otp(operator.secret));
  await page.getByRole("button",{name:"Sign in",exact:true}).click();await page.waitForURL("**/dashboard");
}

test("platform operator MFA, eight metadata workspaces and audited subscription change",async({page})=>{
  await login(page,operator.email,true);
  for(const area of ["overview","tenants","subscriptions","usage","services","incidents","security","releases"]){
    await page.goto(`/platform/${area}`);await expect(page.getByRole("navigation",{name:"Platform workspaces"})).toBeVisible();
    await expect(page.locator("main [role=alert]")).toHaveCount(0);
    if(["overview","tenants","subscriptions","usage"].includes(area))await expect(page.getByRole("table")).toContainText("SYNTHETIC");
    else await expect(page.locator(".operations-result")).toBeVisible();
    await page.screenshot({path:`${shots}/platform-${area}.png`,fullPage:true});
  }
  const denial=await page.request.get("/api/backend/clients",{headers:{"X-Tenant-ID":demo.tenant_id}});
  expect(denial.status()).toBe(403);
  await page.goto("/platform/subscriptions");
  await page.getByRole("button",{name:`Configure ${operator.qa_tenant_name}`,exact:true}).click();
  await page.getByLabel("Valid until (local time)").fill("2027-10-18T12:00");
  await page.getByLabel("Grace until (local time)").fill("2027-11-18T12:00");
  await page.getByLabel("Reason",{exact:true}).fill("Synthetic Phase12 browser subscription verification");
  await page.getByRole("button",{name:"Apply subscription",exact:true}).click();
  await expect(page.getByRole("heading",{name:`Configure ${operator.qa_tenant_name}`,exact:true})).toHaveCount(0);
  await expect(page.getByRole("table")).toContainText("Starter · trial");
});

test("firm administrator cannot enter platform console",async({page})=>{
  await login(page);await page.goto("/platform/tenants");
  await expect(page.locator("main [role=alert]")).toContainText("Separately provisioned platform operator and MFA required");
});

test("WCAG automated checks and reflow across five enterprise viewports",async({page})=>{
  const results=[];
  for(const [width,height] of [[1920,1080],[1600,900],[1440,900],[1366,768],[390,844]]){
    await page.setViewportSize({width,height});await page.goto("/login");
    await expect(page.getByRole("heading",{name:"Sign in to your workspace"})).toBeVisible();
    const report=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]).analyze();
    results.push({route:"/login",width,height,violations:report.violations});
    expect(report.violations.filter(v=>v.impact==="critical"||v.impact==="serious")).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    await page.screenshot({path:`${shots}/login-${width}.png`,fullPage:true});
  }
  await login(page);await page.goto("/security");
  await expect(page.getByLabel("Current password")).toBeVisible();
  const report=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze();
  results.push({route:"/security",width:390,height:844,violations:report.violations});
  writeFileSync("../docs/phase-12/accessibility-results.json",JSON.stringify(results,null,2));
  expect(report.violations.filter(v=>v.impact==="critical"||v.impact==="serious")).toEqual([]);
  await page.getByLabel("Current password").focus();await expect(page.getByLabel("Current password")).toBeFocused();
  await page.keyboard.press("Tab");await expect(page.getByRole("button",{name:"Begin enrollment"})).toBeFocused();
});

import { recordReleaseEvidence } from "./release-evidence";
test.beforeEach(async ({page})=>{recordReleaseEvidence(page);});

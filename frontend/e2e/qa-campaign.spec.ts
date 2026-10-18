import { test, expect } from "@playwright/test";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHmac } from "node:crypto";
const dataset = JSON.parse(readFileSync("../docs/qa-campaign/dataset.json", "utf8"));
const credentials = JSON.parse(readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"));
const eid = dataset.companies[0].engagements[0].id;

test("public login and invitation routes reflow on mobile",async({page})=>{
  const results=[];
  for(const route of ["/login","/join"]){
    await page.setViewportSize({width:390,height:844});
    const response=await page.goto(route);expect(response?.status()).toBe(200);
    await expect(page.locator("main")).toBeVisible();
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);expect(overflow).toBe(false);
    results.push({route,status:response?.status(),horizontalOverflow:overflow,width:390});
  }
  writeFileSync("../docs/qa-campaign/public-route-results.json",JSON.stringify(results,null,2));
});

test("MFA platform operator reads persisted campaign results and cannot read client data",async({page})=>{
  const operator=JSON.parse(readFileSync("../.local-runtime/qa-campaign/operator.local.json","utf8"));
  const bits=[...operator.secret as string].map(c=>"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".indexOf(c).toString(2).padStart(5,"0")).join("");
  const key=Buffer.from(bits.match(/.{8}/g)!.map(b=>parseInt(b,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const digest=createHmac("sha1",key).update(counter).digest();
  const otp=String((digest.readUInt32BE(digest[19]&15)&0x7fffffff)%1000000).padStart(6,"0");
  await page.goto("/login");await page.getByLabel("Email address").fill(operator.email);await page.getByLabel("Password",{exact:true}).fill(credentials.QA_PASSWORD);await page.getByLabel("Authenticator code (if enabled)").fill(otp);await page.getByRole("button",{name:"Sign in",exact:true}).click();await page.waitForURL("**/dashboard");
  await page.goto("/platform/qa-center");
  await expect(page.getByRole("region",{name:"Persisted QA campaign results"})).toBeVisible();
  await expect(page.locator("article").first()).toContainText("1000000");
  await page.screenshot({path:"../docs/qa-campaign/screenshots/qa-center-operator.png",fullPage:true});
  const denied=await page.request.get("/api/backend/clients",{headers:{"X-Tenant-ID":dataset.tenant_id}});expect(denied.status()).toBe(403);
});

function discover() {
  const routes = new Set<string>(["/", "/login", "/join", "/security", "/board", "/client-portal", "/grc", "/tp", "/ifrs", "/ai-lab", "/pillar-two", `/engagements/${eid}`]);
  const workbench = readFileSync("src/features/workbench.tsx", "utf8");
  for (const match of workbench.matchAll(/case\s+"(\/[^" ]*)"/g)) routes.add(match[1]);
  for (const name of readdirSync("src/features").filter(n => n.endsWith(".tsx"))) {
    const source = readFileSync(join("src/features", name), "utf8");
    for (const m of source.matchAll(/export const (\w+)Areas\s*=\s*\[([\s\S]*?)\]\s*as const/g)) {
      const prefix: Record<string,string> = {audit:`/engagements/${eid}`,ifrs:`/ifrs/${eid}`,tax:`/tax/${eid}`,vat:`/vat/${eid}`,tp:`/tp/${eid}`,grc:`/grc/${eid}`,ml:"/ai-lab",dmtt:"/pillar-two",ai:"/ai"};
      if (!prefix[m[1]]) throw new Error(`Unmapped source area ${m[1]}`);
      for (const area of m[2].matchAll(/\["([a-z0-9-]+)"/g)) routes.add(`${prefix[m[1]]}/${area[1]}`);
    }
  }
  const platform = readFileSync("src/features/platform-console.tsx", "utf8").match(/const areas\s*=\s*\[([^;]*)\]/)![1];
  for (const area of platform.matchAll(/"([a-z0-9-]+)"/g)) routes.add(`/platform/${area[1]}`);
  for (const area of ["users","roles","teams","firms","ai","audit-log","templates"]) routes.add(`/admin/${area}`);
  return [...routes].sort();
}

test("every source-discovered workspace renders and records actual controls, errors and network results", async ({page}) => {
  const routes = discover();
  writeFileSync("../docs/qa-campaign/frontend-route-inventory.json", JSON.stringify(routes,null,2));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  await page.getByLabel("Password",{exact:true}).fill(credentials.QA_PASSWORD);
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await page.waitForURL("**/dashboard");
  const results: unknown[] = [];
  let errors:string[] = [], failed:string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("response", r => {if(r.status()>=500)failed.push(`${r.status()} ${new URL(r.url()).pathname}`);});
  for (const route of routes) {
    if (["/login","/join"].includes(route)) continue;
    errors=[];failed=[];
    const started=Date.now();
    const response=await page.goto(route);
    await page.locator("main").first().waitFor({state:"visible"});
    await page.waitForTimeout(400);
    const controls=await page.getByRole("button").evaluateAll(nodes=>nodes.map(n=>({label:n.textContent?.trim(),disabled:(n as HTMLButtonElement).disabled})));
    const alerts=await page.getByRole("alert").allTextContents();
    const content=(await page.locator("main").first().textContent())||"";
    const classification=content.includes("Page not found")?"NOT_IMPLEMENTED":content.includes("Access restricted")?"PERMISSION_RESTRICTED":content.includes("not configured")||content.includes("Not configured")?"PARTIALLY_FUNCTIONAL":"RENDERED_ACTIONS_NOT_FULLY_VERIFIED";
    const result={route,status:response?.status(),classification,seconds:(Date.now()-started)/1000,errors:[...errors],failed:[...failed],alerts,controls,horizontalOverflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),coverage:"render and inventory; mutation actions covered separately"};
    results.push(result);
    if(route==="/dashboard"||route==="/clients"||route==="/platform/qa-center") await page.screenshot({path:`../docs/qa-campaign/screenshots/${route.replaceAll("/","-")}.png`,fullPage:true});
  }
  writeFileSync("../docs/qa-campaign/frontend-route-results.json",JSON.stringify(results,null,2));
  expect(results.filter(r=>(r as {errors:string[]}).errors.length)).toEqual([]);
  expect(results.filter(r=>(r as {failed:string[]}).failed.length)).toEqual([]);
});

test("client search, status filter, edit persistence and backend denial stay functional",async({page})=>{
  await page.goto("/login");await page.getByLabel("Email address").fill("qa.admin@auditos.example");await page.getByLabel("Password",{exact:true}).fill(credentials.QA_PASSWORD);await page.getByRole("button",{name:"Sign in",exact:true}).click();await page.waitForURL("**/dashboard");
  await page.goto("/clients");
  await page.getByLabel("Search clients").fill("QA-01");
  await page.getByLabel("Client status filter").selectOption("active");
  const cell=page.locator(".ag-cell strong").filter({hasText:"QA FICTIONAL 01 General Trading"});
  await expect(cell).toBeVisible();await cell.click();
  await page.getByRole("button",{name:"Edit client",exact:true}).click();
  const saved=page.waitForResponse(r=>r.url().includes("/api/backend/clients/")&&r.request().method()==="PATCH");
  await page.getByRole("button",{name:"Save client",exact:true}).click();
  expect((await saved).status()).toBe(200);
  await page.reload();await page.getByLabel("Search clients").fill("QA-01");await expect(cell).toBeVisible();
  await page.screenshot({path:"../docs/qa-campaign/screenshots/client-code-search-after.png",fullPage:true});
  const wrong=await page.request.get("/api/backend/clients",{headers:{"X-Tenant-ID":"00000000-0000-4000-8000-000000000001"}});expect(wrong.status()).toBe(403);
  await page.goto("/platform/qa-center");await expect(page.locator("main [role=alert]")).toContainText("Separately provisioned platform operator and MFA required");
});

import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/mr-auditor-business/fixture.json", "utf8"),
);
test("real synthetic records to assistant collection, shared lease calculation, source inspection and unposted draft", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/ai/uae-use-cases");
  await page.getByLabel("AI engagement").selectOption(fixture.engagement_id);
  await expect(page.getByRole("heading", { name: /Mr Auditor/ })).toBeVisible();
  await page
    .getByLabel("Business question", { exact: true })
    .selectOption("31");
  await expect(
    page.getByRole("heading", { name: "IFRS lease accounting" }),
  ).toBeVisible();
  const shots = "../docs/mr-auditor-business/evidence/screenshots";
  mkdirSync(shots, { recursive: true });
  await page.screenshot({
    path: shots + "/synthetic-100-case-inputs.png",
    fullPage: true,
  });
  await page
    .getByLabel("Ask Mr Auditor")
    .fill(
      "Review this synthetic office lease, show its source evidence, and prepare the liability schedule for professional review.",
    );
  await page
    .getByRole("button", { name: "Start source-linked analysis" })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Analysis · (COMPLETED|PARTIALLY_COMPLETED)/,
    }),
  ).toBeVisible({ timeout: 90000 });
  await page.getByLabel("Approved engine input").selectOption(fixture.lease_id);
  await page.getByRole("button", { name: "Run governed calculation" }).click();
  await expect(
    page.getByRole("heading", { name: "Retained engine result" }),
  ).toBeVisible();
  await expect(
    page.getByText("NOT_FILED_NOT_POSTED", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Inspect source" }).first().click();
  await expect(
    page.getByRole("complementary", { name: "Source evidence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "Open original evidence versions and review history",
    }),
  ).toBeVisible();
  await page
    .getByLabel("Workpaper preparation notes")
    .fill(
      "SYNTHETIC browser review: lease terms and calculated balances are linked to the approved source; independent approval is outstanding.",
    );
  await page
    .getByRole("button", { name: "Create source-linked draft workpaper" })
    .click();
  await expect(
    page.getByText("governed_draft_creation", { exact: true }),
  ).toBeVisible();
  const directory = "../docs/mr-auditor-business/evidence/screenshots";
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: directory + "/synthetic-100-connected-lease.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});


test("advanced VAT allocation and procurement schedules use approved inputs and retained exact results",async({page})=>{
 const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
 await page.goto("/login");await page.getByLabel("Email address").fill("admin@example.com");await page.getByLabel("Password",{exact:true}).fill("test-strong-password-123");await page.getByRole("button",{name:"Sign in",exact:true}).click();await page.waitForURL("**/dashboard");
 await page.goto("/ai/uae-use-cases");await page.getByLabel("AI engagement").selectOption(fixture.engagement_id);
 await page.getByLabel("Business question",{exact:true}).selectOption("52");
 await expect(page.getByRole("heading",{name:"Residual VAT allocation",exact:true})).toBeVisible();
 await page.getByRole("button",{name:"Start source-linked analysis"}).click();
 await expect(page.getByRole("heading",{name:/Analysis \u00b7 (COMPLETED|PARTIALLY_COMPLETED)/})).toBeVisible({timeout:90000});
 const scope=page.getByRole("region",{name:"Structured review schedule"});
 await scope.getByLabel("Period start",{exact:true}).fill("2026-01-01");await scope.getByLabel("Period end",{exact:true}).fill("2026-12-31");
 await scope.getByLabel("source id",{exact:true}).selectOption(fixture.policy_source_id);
 for(const [key,value] of Object.entries({"source locator":"SYNTHETIC method section 1","version":"SYN-2026","effective from":"2026-01-01","effective to":"2026-12-31","adoption assessment":"SYNTHETIC reviewed allocation method and source attribution"}))await scope.getByLabel(key,{exact:true}).fill(value);
 await scope.getByLabel("Unique reference",{exact:true}).fill("SYN-BROWSER-ALLOC");await scope.getByLabel("Row evidence",{exact:true}).selectOption(fixture.policy_source_id);
 for(const [key,value] of Object.entries({"direct recoverable":"100","direct blocked":"50","residual":"200","numerator":"3","denominator":"4","previously claimed":"240"}))await scope.getByLabel(key,{exact:true}).fill(value);
 await scope.getByLabel("Assumptions, one per line").fill("SYNTHETIC reviewed attribution; no automatic legal method selection");
 const saved=page.waitForResponse(r=>r.url().endsWith("/use-cases/52/actions")&&r.request().method()==="POST");await scope.getByRole("button",{name:"Save input paper for independent approval"}).click();
 const draft=await saved;expect(draft.status()).toBe(201);expect((await draft.json()).body.output.status).toBe("IN_PROGRESS");
 await scope.getByLabel("Approved case-specific input paper").selectOption(fixture.advanced_ids["52"]);
 const calculation=page.waitForResponse(r=>r.url().endsWith("/use-cases/52/actions")&&r.request().method()==="POST");await scope.getByRole("button",{name:"Run structured review",exact:true}).click();
 const response=await calculation;expect(response.status()).toBe(201);const result=(await response.json()).body.output.results;
 expect(result.rows[0].calculations.recoverable).toBe("250");expect(result.rows[0].calculations.period_adjustment).toBe("10");expect(result.publication).toBe("NOT_POSTED_NOT_SENT_NOT_SUBMITTED");
 await page.getByLabel("Business question",{exact:true}).selectOption("91");
 await scope.getByLabel("Approved case-specific input paper").selectOption(fixture.advanced_ids["91"]);
 const match=page.waitForResponse(r=>r.url().endsWith("/use-cases/91/actions")&&r.request().method()==="POST");await scope.getByRole("button",{name:"Run structured review",exact:true}).click();
 const matched=await match;expect(matched.status()).toBe(201);expect((await matched.json()).body.output.results.rows[0].exceptions).toContain("quantity_exception");
 await expect(page.getByRole("heading",{name:"Retained engine result"})).toBeVisible();
 await page.screenshot({path:"../docs/mr-auditor-business/evidence/screenshots/synthetic-advanced-procurement.png",fullPage:true});
 expect(errors).toEqual([]);
});

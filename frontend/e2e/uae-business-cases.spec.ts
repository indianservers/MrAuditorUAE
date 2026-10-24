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

test("advanced VAT allocation and procurement schedules use approved inputs and retained exact results", async ({
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
  await page
    .getByRole("combobox", { name: "Business question", exact: true })
    .selectOption("52");
  await expect(
    page.getByRole("heading", { name: "Residual VAT allocation", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Start source-linked analysis" })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Analysis \u00b7 (COMPLETED|PARTIALLY_COMPLETED)/,
    }),
  ).toBeVisible({ timeout: 90000 });
  const scope = page.getByRole("region", {
    name: "Structured review schedule",
  });
  await scope.getByLabel("Period start", { exact: true }).fill("2026-01-01");
  await scope.getByLabel("Period end", { exact: true }).fill("2026-12-31");
  await scope
    .getByRole("combobox", { name: "source id", exact: true })
    .selectOption(fixture.policy_source_id);
  for (const [key, value] of Object.entries({
    "source locator": "SYNTHETIC method section 1",
    version: "SYN-2026",
    "effective from": "2026-01-01",
    "effective to": "2026-12-31",
    "adoption assessment":
      "SYNTHETIC reviewed allocation method and source attribution",
  }))
    await scope.getByLabel(key, { exact: true }).fill(value);
  await scope
    .getByLabel("Unique reference", { exact: true })
    .fill("SYN-BROWSER-ALLOC");
  await scope
    .getByRole("combobox", { name: "Row evidence", exact: true })
    .selectOption(fixture.policy_source_id);
  for (const [key, value] of Object.entries({
    "direct recoverable": "100",
    "direct blocked": "50",
    residual: "200",
    numerator: "3",
    denominator: "4",
    "previously claimed": "240",
  }))
    await scope.getByLabel(key, { exact: true }).fill(value);
  await scope
    .getByLabel("Assumptions, one per line")
    .fill(
      "SYNTHETIC reviewed attribution; no automatic legal method selection",
    );
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/52/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Save input paper for independent approval" })
    .click();
  const draft = await saved;
  expect(draft.status()).toBe(201);
  expect((await draft.json()).body.output.status).toBe("IN_PROGRESS");
  await scope
    .getByLabel("Approved case-specific input paper")
    .selectOption(fixture.advanced_ids["52"]);
  const calculation = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/52/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Run structured review", exact: true })
    .click();
  const response = await calculation;
  expect(response.status()).toBe(201);
  const result = (await response.json()).body.output.results;
  expect(result.rows[0].calculations.recoverable).toBe("250.00");
  expect(result.rows[0].calculations.period_adjustment).toBe("10.00");
  expect(result.publication).toBe("NOT_POSTED_NOT_SENT_NOT_SUBMITTED");
  await page
    .getByRole("combobox", { name: "Business question", exact: true })
    .selectOption("91");
  await scope
    .getByLabel("Approved case-specific input paper")
    .selectOption(fixture.advanced_ids["91"]);
  const match = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/91/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Run structured review", exact: true })
    .click();
  const matched = await match;
  expect(matched.status()).toBe(201);
  expect(
    (await matched.json()).body.output.results.rows[0].exceptions,
  ).toContain("quantity_exception");
  await expect(
    page.getByRole("heading", { name: "Retained engine result" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/mr-auditor-business/evidence/screenshots/synthetic-advanced-procurement.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("150-case workspace prepares scoped financing drafts and reuses approved IFRS kernels", async ({
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
  await page
    .getByRole("combobox", { name: "Business question", exact: true })
    .selectOption("121");
  await page
    .getByRole("button", { name: "Start source-linked analysis" })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Analysis \u00b7 (COMPLETED|PARTIALLY_COMPLETED)/,
    }),
  ).toBeVisible({ timeout: 90000 });
  const scope = page.getByRole("region", {
    name: "Structured review schedule",
  });
  await scope
    .getByRole("combobox", { name: "Applicable framework", exact: true })
    .selectOption("AE_MAINLAND");
  await scope
    .getByLabel("Named jurisdiction or free zone", { exact: true })
    .fill("SYNTHETIC Dubai mainland");
  await scope.getByLabel("Period start", { exact: true }).fill("2026-01-01");
  await scope.getByLabel("Period end", { exact: true }).fill("2026-12-31");
  await scope
    .getByRole("combobox", { name: "source id", exact: true })
    .selectOption(fixture.policy_source_id);
  for (const [key, value] of Object.entries({
    "source locator": "SYNTHETIC approved financing policy",
    version: "SYN-EIR-1",
    "effective from": "2026-01-01",
    "effective to": "2026-12-31",
    "adoption assessment":
      "SYNTHETIC reviewed financial classification and one-period financing",
  }))
    await scope.getByLabel(key, { exact: true }).fill(value);
  await scope
    .getByLabel("Unique reference", { exact: true })
    .fill("SYN-BROWSER-EIR");
  await scope
    .getByRole("combobox", { name: "Row evidence", exact: true })
    .selectOption(fixture.policy_source_id);
  for (const [key, value] of Object.entries({
    "initial advance": "100",
    "transaction costs": "0",
    "rate lower": "0",
    "rate upper": "0.5",
    "solver tolerance": "0.00000001",
  }))
    await scope.getByLabel(key, { exact: true }).fill(value);
  await scope
    .getByRole("combobox", { name: "asset", exact: true })
    .selectOption("true");
  await scope
    .getByRole("combobox", { name: "classification approved", exact: true })
    .selectOption("true");
  await scope
    .getByLabel("cashflows", { exact: true })
    .fill('[{"period":1,"amount":"110.00"}]');
  await scope
    .getByLabel("Assumptions, one per line")
    .fill("SYNTHETIC annual period; no market data claim");
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/121/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Save input paper for independent approval" })
    .click();
  expect((await saved).status()).toBe(201);
  await expect(
    page.getByRole("complementary", {
      name: "Provisional draft recalculation",
    }),
  ).toBeVisible();
  await scope
    .getByLabel("Approved case-specific input paper")
    .selectOption(fixture.advanced_ids["121"]);
  const financial = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/121/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Run structured review", exact: true })
    .click();
  const result = await financial;
  expect(result.status()).toBe(201);
  const row = (await result.json()).body.output.results.rows[0];
  expect(Number(row.metrics.periodic_effective_rate)).toBeCloseTo(0.1, 8);
  expect(row.schedule[0].closing).toBe("0.00");
  await page
    .getByLabel("Workpaper preparation notes")
    .fill(
      "SYNTHETIC financing: source-linked EIR result, no posting or final opinion; independent review required.",
    );
  await page
    .getByRole("button", { name: "Create source-linked draft workpaper" })
    .click();
  await expect(
    page.getByText("governed_draft_creation", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Business question", exact: true })
    .selectOption("112");
  await scope
    .getByLabel("Approved case-specific input paper")
    .selectOption(fixture.advanced_ids["112"]);
  const bundle = page.waitForResponse(
    (r) =>
      r.url().endsWith("/use-cases/112/actions") &&
      r.request().method() === "POST",
  );
  await scope
    .getByRole("button", { name: "Run structured review", exact: true })
    .click();
  const allocated = await bundle;
  expect(allocated.status()).toBe(201);
  expect(
    (await allocated.json()).body.output.results.rows.map(
      (r: { calculations: { allocated_price: string } }) =>
        r.calculations.allocated_price,
    ),
  ).toEqual(["33.33", "33.33", "33.34"]);
  await page.screenshot({
    path: "../docs/mr-auditor-business/evidence/screenshots/synthetic-150-contract-finance.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("new lease allocation and break-even use approved deterministic inputs", async ({
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
  for (const id of [167, 188]) {
    await page
      .getByRole("combobox", { name: "Business question", exact: true })
      .selectOption(String(id));
    const scope = page.getByRole("region", {
      name: "Structured review schedule",
    });
    await scope
      .getByLabel("Approved case-specific input paper")
      .selectOption(fixture.advanced_ids[String(id)]);
    const pending = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/use-cases/${id}/actions`) &&
        r.request().method() === "POST",
    );
    await scope
      .getByRole("button", { name: "Run structured review", exact: true })
      .click();
    const response = await pending;
    expect(response.status()).toBe(201);
    const result = (await response.json()).body.output.results;
    if (id === 167)
      expect(
        result.rows.map(
          (r: { calculations: { allocated_consideration: string } }) =>
            r.calculations.allocated_consideration,
        ),
      ).toEqual(["33.33", "33.33", "33.34"]);
    else {
      expect(result.rows[0].metrics.break_even_units).toBe("25");
      expect(result.rows[0].metrics.target_profit_units).toBe("30");
    }
    expect(result.rows[0].local_ml_mode).toBe("unavailable");
    const retained=page.getByRole("heading",{name:"Retained engine result",exact:true}).locator("..");
    await expect(retained.getByRole("status")).toContainText("CURRENT");
    if(id===188){
      await retained.getByText("Inspect results",{exact:true}).click();
      await retained.getByText("Inspect rows",{exact:true}).click();
      await retained.getByText("Inspect metrics",{exact:true}).click();
      await expect(retained.getByText("break even units",{exact:true})).toBeVisible();
      await expect(retained.getByText("25",{exact:true})).toBeVisible();
      await expect(retained.getByText("30",{exact:true})).toBeVisible();
      await retained.screenshot({path:"../docs/mr-auditor-business/evidence/screenshots/synthetic-200-retained-scenario.png"});
    }
  }
  await page.screenshot({
    path: "../docs/mr-auditor-business/evidence/screenshots/synthetic-200-break-even.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/country-workflows/fixture.json", "utf8"),
);
const shots = "../docs/country-workflows/screenshots/native-sources";
mkdirSync(shots, { recursive: true });

test("reviewed UAE and India contributions become controlled expected bank remittances", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    for (const country of ["AE", "IN"] as const) {
      const input = fixture.contribution_settlements[country];
      const eid = input.engagement;
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Saved source or result")
        .selectOption(input.result);
      const bridge = page.getByRole("region", {
        name: "Expected contribution remittances",
        exact: true,
      });
      await expect(bridge).toBeVisible();
      await bridge
        .getByLabel("Expected remittance source title")
        .fill(`SYNTHETIC ${country} contribution remittances`);
      await bridge
        .getByLabel("Retained due-date evidence version")
        .fill(input.due_date_evidence);
      await bridge
        .getByLabel("Independent contribution group controls (JSON)")
        .fill(JSON.stringify(input.groups, null, 2));
      if (country === "AE")
        await bridge
          .getByLabel("Assessed pension scope (JSON)")
          .fill(JSON.stringify(input.pension_scope, null, 2));
      await bridge
        .getByLabel("Remittance scope and due-date assessment")
        .fill(
          "Independent synthetic registration, wage month, component controls and retained due-date reference; separate payer assessment",
        );
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-contribution-remittance-controls.png`,
        () => bridge.screenshot(),
      );
      const created = page.waitForResponse(
        (response) =>
          response
            .url()
            .includes(`/engagements/${eid}/contribution-obligation-source`) &&
          response.request().method() === "POST",
      );
      await bridge
        .getByRole("button", {
          name: "Prepare expected remittance source",
          exact: true,
        })
        .click();
      const response = await created;
      expect(response.status(), await response.text()).toBe(201);
      const child = await response.json();
      expect(child.body.control_totals[input.currency]).toBe(input.total);
      expect(child.body.rows).toHaveLength(country === "AE" ? 2 : 3);
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(child.id);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent remittance group controls, retained due-date source and payer scope reviewed",
        );
      const approval = reviewer.waitForResponse(
        (result) =>
          result.url().includes(`/events/${child.id}/review`) &&
          result.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approvedResponse = await approval;
      expect(approvedResponse.status(), await approvedResponse.text()).toBe(
        201,
      );
      const approved = await approvedResponse.json();
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("obligation-bank-allocations");
      const title = `SYNTHETIC ${country} contribution bank settlement ${Date.now()}`;
      await expect(
        page
          .getByLabel("reported source", { exact: true })
          .locator(`option[value="${approved.id}"]`),
      ).toHaveCount(0);
      await expect(
        page
          .getByLabel("expected source", { exact: true })
          .locator(`option[value="${approved.id}"]`),
      ).toHaveCount(1);
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-07-31"],
        ["First obligation month", "2026-06"],
        ["Last obligation month", "2026-06"],
        ["Bank settlement window starts", "2026-07-01"],
        ["Bank account identifier", "BANK-1"],
        ["Account currency", input.currency],
        [
          "Scope and source rationale",
          "Independent contribution expectations, authority return, bank and remittance allocation advice",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      await page.getByLabel("Bank payment sign").selectOption("debit-negative");
      for (const [role, identifier] of Object.entries({
        ...input.sources,
        expected: approved.id,
      }))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(String(identifier));
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const option = page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(title) });
      await expect(option).toHaveCount(1);
      await page
        .getByLabel("Saved source or result")
        .selectOption((await option.getAttribute("value"))!);
      const panel = page
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      await expect(
        panel.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await expect(
        panel.getByRole("cell", { name: "MATCHED", exact: true }),
      ).toHaveCount(country === "AE" ? 5 : 7);
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-contribution-bank-settlement.png`,
        () => panel.screenshot(),
      );
      if (country === "AE") {
        await panel
          .getByLabel("Show source provenance and all columns")
          .check();
        await expect(
          panel.getByRole("columnheader", {
            name: "pension scope",
            exact: true,
          }),
        ).toBeVisible();
      }
    }
  } finally {
    await context.close();
  }
});

test("published UAE pension profiles bind reviewed salary bases and retain rule provenance", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const input = fixture.published_pension;
  const eid = input.engagement;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto("/settings/regulatory-rules");
    await page
      .getByRole("button", { name: "Propose UAE pension profile", exact: true })
      .click();
    const template = JSON.parse(
      await page.getByLabel("Versioned rule configuration").inputValue(),
    );
    expect(template.method).toBe("pension_profile");
    expect(template.pension_parameters.rate).toBeNull();
    expect(template.pension_parameters.authority).toBe("");
    expect(template.validation_status).toBe("AWAITING_VALIDATION");
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source table type", { exact: true })
      .selectOption("pension-rules");
    const preparation = page.getByRole("region", {
      name: "Published UAE pension profiles",
      exact: true,
    });
    await preparation
      .getByLabel("Reviewed pension basis source")
      .selectOption(input.bases);
    for (const component of ["EMPLOYEE", "EMPLOYER", "GOVERNMENT"])
      await preparation
        .getByRole("checkbox", {
          name: new RegExp(`AE-SYNTHETIC-PENSION-${component}`),
        })
        .check();
    await preparation.getByLabel("Independent wage-basis row count").fill("3");
    await preparation
      .getByLabel("Published pension source title")
      .fill("SYNTHETIC published pension sources");
    await preparation
      .getByLabel("Pension profile applicability assessment")
      .fill(
        "Explicit synthetic authority, scheme, membership continuity and assessed contribution salary reviewed for June",
      );
    const created = page.waitForResponse(
      (response) =>
        response.url().includes(`/engagements/${eid}/pension-rule-source`) &&
        response.request().method() === "POST",
    );
    await preparation
      .getByRole("button", {
        name: "Prepare published pension rule source",
        exact: true,
      })
      .click();
    const response = await created;
    expect(response.status(), await response.text()).toBe(201);
    const source = await response.json();
    await saveScreenshot(`${shots}/uae-published-pension-source.png`, () =>
      preparation.screenshot(),
    );
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent retained-source, authority, scheme, membership and June coverage assessment",
      );
    const approval = reviewer.waitForResponse(
      (response) =>
        response.url().includes(`/events/${source.id}/review`) &&
        response.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approvedResponse = await approval;
    expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
    const approved = await approvedResponse.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-pension-review");
    const title = `SYNTHETIC published UAE pension ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale")
      .fill(
        "Reviewed contribution salary, authority observations and independently published pension profiles",
      );
    for (const [role, identifier] of [
      ["bases", input.bases],
      ["rules", approved.id],
      ["reported", input.reported],
    ])
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(identifier);
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    const result = (await option.getAttribute("value"))!;
    await page.getByLabel("Saved source or result").selectOption(result);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText(/Expected contributions: AED 2500.00/),
    ).toBeVisible();
    const table = panel.getByRole("table");
    await expect(
      table.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(3);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(`${shots}/uae-published-pension-calculation.png`, () =>
      panel.screenshot(),
    );
    await panel
      .getByLabel("Show rule provenance and source references")
      .check();
    await expect(
      table.getByRole("columnheader", {
        name: "published rule version id",
        exact: true,
      }),
    ).toBeVisible();
    const detail = await page.request.get(
      `/api/backend/intelligence/engagements/${eid}/events/${result}`,
      { headers: { "X-Tenant-ID": fixture.tenant } },
    );
    expect(detail.status()).toBe(200);
    const body = await detail.json();
    expect(
      new Set(
        body.body.rows.map(
          (row: { published_rule_version_id: string }) =>
            row.published_rule_version_id,
        ),
      ),
    ).toEqual(new Set(input.profiles));
  } finally {
    await context.close();
  }
});

test("UAE pension compares employee net employer and government support through the worker", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  const eid = fixture.uae_engagement;
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("uae-pension-review");
  const title = `SYNTHETIC UAE pension contribution review ${Date.now()}`;
  await page.getByLabel("Schedule title", { exact: true }).fill(title);
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("Scope and source rationale")
    .fill(
      "Explicit synthetic authority and continuing-member cohort; independently reviewed contribution salary and rules",
    );
  for (const [role, identifier] of Object.entries(fixture.pension_sources))
    await page
      .getByLabel(`${role} source`, { exact: true })
      .selectOption(String(identifier));
  const submitted = page.waitForResponse(
    (response) =>
      response.url().includes(`/engagements/${eid}/jobs`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const job = await response.json();
  let result = "";
  await expect
    .poll(
      async () => {
        const status = await page.request.get(
          `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
          { headers: { "X-Tenant-ID": fixture.tenant } },
        );
        expect(status.status()).toBe(200);
        const body = await status.json();
        if (body.status === "failed")
          throw new Error(JSON.stringify(body.error_details));
        result = body.result_id || "";
        return body.status;
      },
      { timeout: 45000 },
    )
    .toBe("completed");
  const selector = page.getByLabel("Saved source or result");
  await expect(selector.locator(`option[value="${result}"]`)).toHaveCount(1);
  await selector.selectOption(result);
  const panel = page
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await expect(
    panel.getByText(/Expected contributions: AED 2500.00/),
  ).toBeVisible();
  const table = panel.getByRole("table");
  await expect(
    table.getByRole("cell", { name: "MATCHED", exact: true }),
  ).toHaveCount(3);
  await expect(
    table.getByRole("cell", { name: "1500.00", exact: true }),
  ).toHaveCount(2);
  await expect(
    table.getByRole("columnheader", { name: "authority", exact: true }),
  ).toBeVisible();
  for (const notice of await page
    .getByRole("button", { name: "Dismiss notification", exact: true })
    .all())
    await notice.click();
  await saveScreenshot(`${shots}/uae-pension-contribution-review.png`, () =>
    panel.screenshot(),
  );
  await panel.getByLabel("Show rule provenance and source references").check();
  await expect(
    table.getByRole("columnheader", {
      name: "government support",
      exact: true,
    }),
  ).toBeVisible();
  const exported = await page.request.get(
    `/api/backend/intelligence/engagements/${eid}/events/${result}/export?format=xlsx`,
    { headers: { "X-Tenant-ID": fixture.tenant } },
  );
  expect(exported.status()).toBe(200);
  expect((await exported.body()).subarray(0, 2).toString()).toBe("PK");
  expect(errors).toEqual([]);
});

test("published India payroll profiles feed reviewed PF and EPS calculations", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const input = fixture.regulatory_conversions.IN;
  const eid = input.engagement;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source table type", { exact: true })
      .selectOption("payroll-rules");
    const preparation = page.getByRole("region", {
      name: "Published India payroll profiles",
      exact: true,
    });
    await preparation
      .getByLabel("Reviewed payroll basis source", { exact: true })
      .selectOption(input.payroll.bases);
    for (const component of ["EMPLOYEE", "EPS", "EMPLOYER"])
      await preparation
        .getByRole("checkbox", {
          name: new RegExp(`IN-SYNTHETIC-PF-${component}-BROWSER`),
        })
        .check();
    await preparation
      .getByLabel("Independent wage-basis row count", { exact: true })
      .fill("3");
    await preparation
      .getByLabel("Published payroll source title", { exact: true })
      .fill("SYNTHETIC published India payroll rules");
    await preparation
      .getByLabel("Payroll profile applicability assessment", { exact: true })
      .fill(
        "Synthetic membership, assessed component wage bases and whole-month jurisdiction assessed",
      );
    await saveScreenshot(
      `${shots}/india-published-payroll-preparation.png`,
      () => preparation.screenshot(),
    );
    const prepared = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/engagements/${eid}/payroll-rule-source`) &&
        response.request().method() === "POST",
    );
    await preparation
      .getByRole("button", {
        name: "Prepare published payroll rule source",
        exact: true,
      })
      .click();
    const response = await prepared;
    expect(response.status(), await response.text()).toBe(201);
    const source = await response.json();
    await reviewer.goto(`/intelligence/${eid}/workflow-source`);
    await reviewer
      .getByLabel("Saved source or result", { exact: true })
      .selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale", { exact: true })
      .fill(
        "Independent synthetic membership, profile parameters and source-copy integrity checked",
      );
    const approval = reviewer.waitForResponse(
      (response) =>
        response.url().endsWith(`/events/${source.id}/review`) &&
        response.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approvedResponse = await approval;
    expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
    const approved = await approvedResponse.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("india-payroll-rules");
    const title = `SYNTHETIC published India payroll ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    for (const [role, value] of [
      ["bases", input.payroll.bases],
      ["rules", approved.id],
      ["reported", input.payroll.reported],
    ])
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(value);
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Synthetic expected and reported contributions use independently published complete-month profiles",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await option.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    const table = panel.getByRole("table");
    for (const component of ["PF:EMPLOYEE", "PF:EPS", "PF:EMPLOYER"])
      await expect(
        table.getByRole("cell", { name: component, exact: true }),
      ).toHaveCount(1);
    await expect(
      table.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(3);
    await expect(
      table.getByRole("cell", { name: "1250", exact: true }),
    ).toHaveCount(2);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/india-published-payroll-calculation.png`,
      () => table.screenshot(),
    );
    await panel
      .getByLabel("Show rule provenance and source references")
      .check();
    await expect(
      table.getByRole("columnheader", {
        name: "published rule version id",
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await context.close();
  }
});

test("published UAE benefit profiles feed independently reviewed employee calculations", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const input = fixture.regulatory_conversions.AE;
  const eid = input.engagement;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source table type", { exact: true })
      .selectOption("benefit-rules");
    const preparation = page.getByRole("region", {
      name: "Published UAE benefit profiles",
      exact: true,
    });
    await preparation
      .getByLabel("Reviewed benefit employee source", { exact: true })
      .selectOption(input.benefits.employees);
    await preparation
      .getByRole("checkbox", { name: /AE-SYNTHETIC-FULL-BROWSER/ })
      .check();
    await preparation
      .getByRole("checkbox", { name: /AE-SYNTHETIC-PART-BROWSER/ })
      .check();
    await preparation
      .getByLabel("Independent employee row count", { exact: true })
      .fill("2");
    await preparation
      .getByLabel("Published benefit source title", { exact: true })
      .fill("SYNTHETIC published benefit rules");
    await preparation
      .getByLabel("Benefit profile applicability assessment", { exact: true })
      .fill(
        "Synthetic full-time and part-time cohort, salary comparators and service ends independently assessed",
      );
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(`${shots}/uae-published-benefit-preparation.png`, () =>
      preparation.screenshot(),
    );
    const prepared = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/engagements/${eid}/benefit-rule-source`) &&
        response.request().method() === "POST",
    );
    await preparation
      .getByRole("button", {
        name: "Prepare published benefit rule source",
        exact: true,
      })
      .click();
    const response = await prepared;
    expect(response.status(), await response.text()).toBe(201);
    const source = await response.json();
    await reviewer.goto(`/intelligence/${eid}/workflow-source`);
    await reviewer
      .getByLabel("Saved source or result", { exact: true })
      .selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale", { exact: true })
      .fill(
        "Independent synthetic published profiles, original source copies and employee selection verified",
      );
    const approval = reviewer.waitForResponse(
      (response) =>
        response.url().endsWith(`/events/${source.id}/review`) &&
        response.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approvedResponse = await approval;
    expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
    const approved = await approvedResponse.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-benefit-review");
    const title = `SYNTHETIC published employee benefits ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("employees source", { exact: true })
      .selectOption(input.benefits.employees);
    await page
      .getByLabel("rules source", { exact: true })
      .selectOption(approved.id);
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Synthetic employee-level salary and hours compared to the current published profiles",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await option.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    const table = panel.getByRole("table");
    await expect(
      table.getByRole("cell", { name: "2100.00", exact: true }),
    ).toHaveCount(1);
    await expect(
      table.getByRole("cell", { name: "1050.00", exact: true }),
    ).toHaveCount(1);
    await expect(
      table.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(2);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await expect
      .poll(() =>
        table.evaluate(
          (element) =>
            element.scrollWidth <= element.parentElement!.clientWidth,
        ),
      )
      .toBe(true);
    await saveScreenshot(`${shots}/uae-published-benefit-calculation.png`, () =>
      table.screenshot(),
    );
    await panel.getByLabel("Show source provenance and all columns").check();
    await expect(
      table.getByRole("columnheader", {
        name: "published rule version id",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      table.getByRole("cell", {
        name: input.benefits.part_profile,
        exact: true,
      }),
    ).toHaveCount(2);
  } finally {
    await context.close();
  }
});

test("UAE and India rules retain sources, publish independently and withdraw safely", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  async function workingCountry(actor: Page, country: string) {
    await actor.goto("/settings/countries");
    const picker = actor.getByLabel("Working country", { exact: true });
    await expect(picker).toBeEnabled();
    if ((await picker.inputValue()) !== country) {
      const changed = actor.waitForResponse(
        (response) =>
          response.url().endsWith("/jurisdictions/settings") &&
          response.request().method() === "PATCH",
      );
      await picker.selectOption(country);
      expect((await changed).status()).toBe(200);
    }
  }
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    for (const country of ["AE", "IN"] as const) {
      await workingCountry(page, country);
      await workingCountry(reviewer, country);
      await page.goto("/settings/regulatory-rules");
      await page
        .getByRole("button", { name: "Propose new rule", exact: true })
        .click();
      const body = {
        rule_key: `${country}-SYNTHETIC-SOURCE-${Date.now()}`,
        country,
        title: "SYNTHETIC retained-source workflow, not legislation",
        description:
          "Synthetic publication controls only; no legal rate or applicability qualification",
        framework: country === "AE" ? "IFRS" : "Ind AS",
        period_basis: "period_start",
        effective_from: "2026-01-01",
        effective_to: "2027-12-31",
        citations: [
          {
            authority: "SYNTHETIC reference",
            legislation: "SYNTHETIC copy only",
            url: "https://mof.gov.ae/",
            paragraph: "TEST",
          },
        ],
        input_requirements: ["entity_type"],
        output_requirements: ["reviewed_conclusion"],
        applicability: [],
        method: "checklist",
        validation_status: "VALIDATED",
        professional_review_status: "REVIEWED",
        last_reviewed: "2026-10-24",
        amendment_reason:
          "Synthetic mechanics only; no country legal-content release",
        expected_sequence: 0,
      };
      await page
        .getByLabel("Versioned rule configuration")
        .fill(JSON.stringify(body, null, 2));
      await page
        .getByText("Firm regulatory reference copies", { exact: true })
        .click();
      const sourcePicker = page.getByLabel("Retained regulatory source", {
        exact: true,
      });
      await expect(sourcePicker).toBeVisible();
      await expect(
        sourcePicker.locator(
          `option[value="${fixture.regulatory_conversions[country].rule_reference_copy}"]`,
        ),
      ).toHaveCount(1);
      await sourcePicker.selectOption(
        fixture.regulatory_conversions[country].rule_reference_copy,
      );
      await page
        .getByRole("button", {
          name: "Attach source to proposal citation",
          exact: true,
        })
        .click();
      const attached = JSON.parse(
        await page.getByLabel("Versioned rule configuration").inputValue(),
      );
      expect(attached.citations[0].source_document_id).toBe(
        fixture.regulatory_conversions[country].rule_reference_copy,
      );
      expect(attached.citations[0].document_sha256).toMatch(/^[a-f0-9]{64}$/);
      const createdResponse = page.waitForResponse(
        (response) =>
          response.url().endsWith("/regulatory/rules") &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Save immutable proposal", exact: true })
        .click();
      const created = await createdResponse;
      expect(created.status()).toBe(201);
      const rule = await created.json();
      await page
        .getByLabel("Decision rationale")
        .fill(
          "Synthetic preparer cannot independently approve their own rule or source.",
        );
      const denied = page.waitForResponse((response) =>
        response.url().endsWith(`/rules/${rule.id}/decisions`),
      );
      await page
        .getByRole("button", {
          name: "Record independent approval",
          exact: true,
        })
        .click();
      expect((await denied).status()).toBe(403);
      await reviewer.goto(`/settings/regulatory-rules?rule=${rule.id}`);
      await reviewer
        .getByLabel("Decision rationale")
        .fill(
          "Independent synthetic source-copy, citation binding and content mechanics checked.",
        );
      const validationCases = [
        {
          id: "SYNTHETIC-APPLICABILITY",
          kind: "checklist",
          expected_reference:
            "Independent synthetic company applicability fixture; not legally qualified data",
          period_start: "2026-01-01",
          period_end: "2026-12-31",
          facts: { entity_type: "company" },
          expected_applicability: "APPLICABLE",
        },
      ];
      await reviewer
        .getByLabel("Validation fixture cases (JSON)", { exact: true })
        .fill(JSON.stringify(validationCases));
      const checkedResponse = reviewer.waitForResponse(
        (response) =>
          response.url().endsWith(`/rules/${rule.id}/validate`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Check supplied fixtures", exact: true })
        .click();
      const checked = await checkedResponse;
      expect(checked.status(), await checked.text()).toBe(200);
      const validationReceipt = await checked.json();
      expect(validationReceipt.passed).toBe(true);
      await expect(
        reviewer
          .getByRole("region", { name: "Fixture check result", exact: true })
          .getByRole("status"),
      ).toContainText("All supplied fixtures passed");
      for (const notice of await reviewer
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-rule-fixture-validation.png`,
        () =>
          reviewer
            .getByRole("region", {
              name: "Independent rule fixtures",
              exact: true,
            })
            .screenshot(),
      );
      const approved = reviewer.waitForResponse((response) =>
        response.url().endsWith(`/rules/${rule.id}/decisions`),
      );
      await reviewer
        .getByRole("button", {
          name: "Record independent approval",
          exact: true,
        })
        .click();
      const approvalResponse = await approved;
      expect(approvalResponse.status()).toBe(201);
      expect(
        (await approvalResponse.json()).body.fixture_validation.receipt_sha256,
      ).toBe(validationReceipt.receipt_sha256);
      await page.goto(`/settings/regulatory-rules?rule=${rule.id}`);
      await page
        .getByLabel("Decision rationale")
        .fill(
          "Synthetic controlled publication following independent review of the retained reference copy.",
        );
      const published = page.waitForResponse((response) =>
        response.url().endsWith(`/rules/${rule.id}/decisions`),
      );
      await page
        .getByRole("button", { name: "Publish approved version", exact: true })
        .click();
      const result = await published;
      expect(result.status()).toBe(201);
      const publishedAction = await result.json();
      expect(publishedAction.body.fixture_validation.receipt_sha256).toBe(
        validationReceipt.receipt_sha256,
      );
      expect(publishedAction.body.verified_source_copies[0].id).toBe(
        attached.citations[0].source_document_id,
      );
      await expect(
        page.getByText("PUBLISHED", { exact: true }).first(),
      ).toBeVisible();
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      const panel = page
        .getByRole("heading", { name: `${body.rule_key} • v1`, exact: true })
        .locator("..");
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-retained-source-rule-publication.png`,
        () => panel.screenshot(),
      );
      const eid = fixture.regulatory_conversions[country].engagement;
      const assessed = await page.request.post(
        `/api/backend/regulatory/engagements/${eid}/assessments`,
        {
          headers: {
            "X-Tenant-ID": fixture.tenant,
            Origin: "http://127.0.0.1:3010",
          },
          data: {
            rule_ids: [rule.id],
            facts: { entity_type: "company" },
            rationale:
              "Synthetic current rule assessment before controlled withdrawal",
          },
        },
      );
      expect(assessed.status(), await assessed.text()).toBe(201);
      const saved = await assessed.json();
      await page
        .getByLabel("Decision rationale")
        .fill(
          "Synthetic withdrawal due to reviewed source concern; replacement requires independent approval.",
        );
      const withdrawnResponse = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/rules/${rule.id}/decisions`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Withdraw published version",
          exact: true,
        })
        .click();
      const withdrawn = await withdrawnResponse;
      expect(withdrawn.status(), await withdrawn.text()).toBe(201);
      expect((await withdrawn.json()).state).toBe("WITHDRAWN");
      await page.goto(`/settings/regulatory-rules?rule=${rule.id}`);
      await expect(panel.getByText("WITHDRAWN", { exact: true })).toBeVisible();
      await expect(
        panel
          .getByRole("region", {
            name: "Recorded rule withdrawal",
            exact: true,
          })
          .getByText(
            "Synthetic withdrawal due to reviewed source concern; replacement requires independent approval.",
            { exact: true },
          ),
      ).toBeVisible();
      await expect(panel.getByRole("link", { name: /STALE/ })).toBeVisible();
      await expect(
        panel.getByRole("button", {
          name: "Withdraw published version",
          exact: true,
        }),
      ).toHaveCount(0);
      const history = await page.request.get(
        `/api/backend/intelligence/engagements/${eid}/events/${saved.id}`,
        { headers: { "X-Tenant-ID": fixture.tenant } },
      );
      expect(history.status()).toBe(200);
      const original = await history.json();
      expect(original.freshness).toBe("STALE");
      expect(original.sha256).toBe(saved.sha256);
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-withdrawn-rule-history.png`,
        () => panel.screenshot(),
      );
    }
    await workingCountry(page, "AE");
    await workingCountry(reviewer, "AE");
  } finally {
    await context.close();
  }
});

test("reviewed obligations allocate pooled bank payments for UAE and India", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    for (const [country, eid, currency] of [
      ["AE", fixture.uae_engagement, "AED"],
      ["IN", fixture.india_engagement, "INR"],
    ] as const) {
      const title = `SYNTHETIC ${country} pooled obligation bank review ${Date.now()}`;
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("obligation-bank-allocations");
      await expect(page.getByLabel("Bank payment sign")).toHaveValue("");
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["First obligation month", "2026-05"],
        ["Last obligation month", "2026-06"],
        ["Bank settlement window starts", "2026-06-01"],
        ["Bank account identifier", "BANK-1"],
        ["Account currency", currency],
        [
          "Scope and source rationale",
          "Reviewed fictional pooled payment scope with separately retained expected, reported and bank evidence",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      await page.getByLabel("Bank payment sign").selectOption("debit-negative");
      for (const [role, id] of Object.entries(
        fixture.obligation_allocations[country],
      ))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(String(id));
      const queued = page.waitForResponse(
        (response) =>
          response.url().includes(`/engagements/${eid}/jobs`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      expect((await queued).status()).toBe(202);
      const option = page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(title) });
      await expect(option).toHaveCount(1);
      await page
        .getByLabel("Saved source or result")
        .selectOption((await option.getAttribute("value"))!);
      const panel = page
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      await expect(
        panel.getByRole("region", { name: "Obligation allocation controls" }),
      ).toContainText("allocated amount180");
      const late = panel.getByRole("row").filter({
        has: page.getByRole("cell", { name: "LATE_PAYMENT", exact: true }),
      });
      await expect(late).toHaveCount(1);
      await panel
        .getByLabel("Review / exception rationale")
        .fill(
          "Synthetic late residual payment of 30 retained and documented; no legal due date is inferred.",
        );
      const disposition = page.waitForResponse(
        (response) =>
          response.url().endsWith("/review") &&
          response.request().method() === "POST",
      );
      await late
        .getByRole("button", { name: "Document exception", exact: true })
        .click();
      const response = await disposition;
      expect(response.status()).toBe(201);
      const prepared = await response.json();
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(prepared.id);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent source, pooled allocation, residual controls and documented late payment checked.",
        );
      const approval = reviewer.waitForResponse(
        (response) =>
          response.url().endsWith(`/events/${prepared.id}/review`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approved = await approval;
      expect(approved.status()).toBe(201);
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      const reviewedPanel = reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      for (const notice of await reviewer
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      const reviewedTable = reviewedPanel.getByRole("table");
      await expect
        .poll(() =>
          reviewedTable.evaluate(
            (table) => table.scrollWidth <= table.parentElement!.clientWidth,
          ),
        )
        .toBe(true);
      await reviewedTable.scrollIntoViewIfNeeded();
      await reviewedTable.evaluate((table) => {
        table.parentElement!.scrollLeft = 0;
      });
      await expect(
        reviewedTable.getByRole("columnheader", { name: "kind", exact: true }),
      ).toBeInViewport({ ratio: 1 });
      await expect(
        reviewedTable.getByRole("cell", { name: "LATE_PAYMENT", exact: true }),
      ).toBeVisible();
      await expect(reviewedTable.getByRole("row")).toHaveCount(7);
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-obligation-bank-allocations.png`,
        () => reviewedTable.screenshot(),
      );
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-obligation-allocation-controls.png`,
        () =>
          reviewedPanel
            .getByRole("region", { name: "Obligation allocation controls" })
            .screenshot(),
      );
    }
  } finally {
    await context.close();
  }
});

test("reviewed currency conversions feed scoped UAE and India rule assessments", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    async function approve(eid: string, id: string) {
      await reviewer.goto(`/intelligence/${eid}/lead?event=${id}`);
      await reviewer
        .getByLabel("Auditor rationale / review comments")
        .fill(
          "Independent synthetic source amounts, retained direct quote, assessed rounding and currency lineage checked.",
        );
      const response = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", {
          name: "Record independent approval",
          exact: true,
        })
        .click();
      const reviewed = await response;
      expect(reviewed.status(), await reviewed.text()).toBe(201);
      const result = await reviewed.json();
      expect(result.body.review_status).toBe("REVIEWED");
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      return result;
    }
    async function workingCountry(country: string) {
      await page.goto("/settings/countries");
      const picker = page.getByLabel("Working country", { exact: true });
      await expect(picker).toBeEnabled();
      if ((await picker.inputValue()) !== country) {
        const changed = page.waitForResponse(
          (r) =>
            r.url().endsWith("/jurisdictions/settings") &&
            r.request().method() === "PATCH",
        );
        await picker.selectOption(country);
        const response = await changed;
        expect(response.status(), await response.text()).toBe(200);
        await expect(picker).toHaveValue(country);
      }
    }
    for (const country of ["AE", "IN"] as const) {
      await workingCountry(country);
      const input = fixture.regulatory_conversions[country];
      const eid = input.engagement;
      const listed = await page.request.get(
        "/api/backend/engagements?limit=100",
        { headers: { "X-Tenant-ID": fixture.tenant } },
      );
      expect(listed.status(), await listed.text()).toBe(200);
      const engagementList = await listed.json();
      expect(
        engagementList.items.map((item: { id: string }) => item.id),
      ).toContain(eid);
      await page.goto("/compliance/country");
      const engagementPicker = page.getByLabel("Compliance engagement", {
        exact: true,
      });
      await expect(engagementPicker).toBeVisible();
      await expect(
        engagementPicker.locator(`option[value="${eid}"]`),
      ).toHaveCount(1);
      await engagementPicker.selectOption(eid);
      await expect(
        page.getByRole("heading", {
          name: `${country} Compliance Workspace`,
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByLabel("Reviewed source schedule (required for arithmetic)")
        .selectOption(input.source);
      await page
        .getByText("Prepare explicit source currency conversion", {
          exact: true,
        })
        .click();
      await page
        .getByLabel("Reviewed exchange rate source")
        .selectOption(input.rates);
      await page.getByLabel("Exchange rate row").selectOption("SYN-FX");
      for (const [label, value] of [
        [
          "Currency conversion title",
          `SYNTHETIC ${country} reviewed base conversion ${Date.now()}`,
        ],
        ["Conversion decimal places", "2"],
        ["Independent converted amount", "400.80"],
        [
          "Conversion basis and rounding assessment",
          "Synthetic retained direct quote and explicit rounding assessed; no actual legal rate claimed",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      await page.getByLabel("Conversion rounding").selectOption("half-up");
      const prepared = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/engagements/${eid}/conversions`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Prepare currency conversion for review",
          exact: true,
        })
        .click();
      const response = await prepared;
      expect(response.status(), await response.text()).toBe(201);
      const conversion = await response.json();
      expect(conversion.body.converted_amount).toBe("400.80");
      const approved = await approve(eid, conversion.id);
      for (const notice of await reviewer
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await expect(
        reviewer.getByRole("cell", { name: "400.80", exact: true }),
      ).toBeVisible();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-reviewed-currency-conversion.png`,
        () =>
          reviewer
            .getByRole("heading", { name: "rows", exact: true })
            .locator("..")
            .screenshot(),
      );
      await page.goto("/compliance/country");
      await expect(
        page
          .getByLabel("Compliance engagement")
          .locator(`option[value="${eid}"]`),
      ).toHaveCount(1);
      await page.getByLabel("Compliance engagement").selectOption(eid);
      await page
        .getByLabel("Published rule versions")
        .selectOption([input.rule]);
      await page
        .getByLabel("Reviewed source schedule (required for arithmetic)")
        .selectOption(input.source);
      await page
        .getByLabel("Reviewed currency conversion (optional)")
        .selectOption(approved.id);
      await page
        .getByLabel("Additional applicability facts (JSON)")
        .fill('{"tax_base":"400.80"}');
      await page
        .getByLabel("Professional applicability / tax-base selection rationale")
        .fill(
          "Synthetic published arithmetic rule applied to the separately reviewed converted amount; no actual tax liability asserted.",
        );
      const submitted = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/engagements/${eid}/assessments`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Evaluate current rules and retain receipt",
          exact: true,
        })
        .click();
      const assessmentResponse = await submitted;
      expect(assessmentResponse.status(), await assessmentResponse.text()).toBe(
        201,
      );
      const assessment = await assessmentResponse.json();
      expect(assessment.body.facts.functional_currency).toBe(
        input.source_currency,
      );
      expect(assessment.body.facts.tax_base_currency).toBe("USD");
      expect(Number(assessment.body.rows[0].calculation.unrounded_amount)).toBe(
        50.1,
      );
      await approve(eid, assessment.id);
      for (const notice of await reviewer
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await expect(
        reviewer.getByRole("cell", { name: /50\.100/ }).first(),
      ).toBeVisible();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-converted-rule-assessment.png`,
        () =>
          reviewer
            .getByRole("heading", { name: "rows", exact: true })
            .locator("..")
            .screenshot(),
      );
    }
    await workingCountry("AE");
  } finally {
    await context.close();
  }
});

test("reviewed BRS exceptions feed subsequent bank clearance for UAE and India", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    async function approve(eid: string, id: string) {
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer.getByLabel("Saved source or result").selectOption(id);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent original BRS lineage, selected amount and subsequent bank clearance allocation checked.",
        );
      const response = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const reviewed = await response;
      expect(reviewed.status(), await reviewed.text()).toBe(201);
      const approved = await reviewed.json();
      expect(approved.body.review_status).toBe("REVIEWED");
      await expect(reviewer.getByLabel("Saved source or result")).toHaveValue(
        approved.id,
      );
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      return approved.id as string;
    }
    for (const [country, eid, currency] of [
      ["AE", fixture.uae_engagement, "AED"],
      ["IN", fixture.india_engagement, "INR"],
    ] as const) {
      const input = fixture.bank_clearance[country];
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page.getByLabel("Saved source or result").selectOption(input.brs);
      await page
        .getByText(
          "Prepare selected outstanding items for subsequent clearance",
          { exact: true },
        )
        .click();
      await page.getByRole("checkbox", { name: /books:O1/ }).check();
      for (const [label, value] of [
        [
          "Outstanding source title",
          `SYNTHETIC ${country} BRS outstanding ${Date.now()}`,
        ],
        ["Independent outstanding row count", "1"],
        ["Independent outstanding signed total", "-100"],
        [
          "Outstanding population assessment",
          "Original reviewed cheque and original book date selected for independently evidenced subsequent bank clearance",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const created = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${input.brs}/bank-outstanding-source`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Prepare outstanding source",
          exact: true,
        })
        .click();
      const response = await created;
      expect(response.status(), await response.text()).toBe(201);
      const bridge = await response.json();
      expect(bridge.body.rows[0].source_book_row_id).toBe("O1");
      const approvedBridge = await approve(eid, bridge.id);
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("bank-subsequent-clearance");
      const title = `SYNTHETIC ${country} subsequent bank clearance ${Date.now()}`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["Review through date", "2026-07-31"],
        ["Bank account identifier", "BANK-1"],
        ["Account currency", currency],
        ["outstanding source", approvedBridge],
        ["statement source", input.statement],
        ["allocations source", input.allocations],
        [
          "Scope and source rationale",
          "Reviewed reporting-date BRS cheque explicitly allocated to retained later statement movement without altering the original balance",
        ],
      ]) {
        const field = page.getByLabel(label, { exact: true });
        if (label.endsWith(" source")) await field.selectOption(value);
        else await field.fill(value);
      }
      const queued = page.waitForResponse(
        (r) =>
          r.url().includes(`/engagements/${eid}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const submitted = await queued;
      expect(submitted.status()).toBe(202);
      const job = await submitted.json();
      let resultId = "";
      await expect
        .poll(
          async () => {
            const status = await page.request.get(
              `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
              { headers: { "X-Tenant-ID": fixture.tenant } },
            );
            const body = await status.json();
            if (body.status === "failed")
              throw new Error(JSON.stringify(body.error_details));
            resultId = body.result_id || "";
            return body.status;
          },
          { timeout: 45000 },
        )
        .toBe("completed");
      await expect(
        page
          .getByLabel("Saved source or result")
          .locator(`option[value="${resultId}"]`),
      ).toHaveCount(1);
      await page.getByLabel("Saved source or result").selectOption(resultId);
      await expect(
        page.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await approve(eid, resultId);
      const heading = reviewer.getByRole("heading", {
        name: title,
        exact: true,
      });
      await expect(heading).toBeVisible();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-subsequent-bank-clearance.png`,
        () => heading.locator("..").screenshot(),
      );
    }
  } finally {
    await context.close();
  }
});

test("reviewed import detail feeds selected VAT201 books boxes and independent filed evidence", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  page.setDefaultTimeout(15000);
  const reviewerContext = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await reviewerContext.newPage();
  reviewer.setDefaultTimeout(15000);
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    const eid = fixture.uae_engagement;
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Saved source or result")
      .selectOption(fixture.import_box_parent);
    await page
      .getByText("Prepare selected import boxes for VAT201 comparison", {
        exact: true,
      })
      .click();
    await page
      .getByLabel("Import box source title", { exact: true })
      .fill(`SYNTHETIC import VAT book boxes ${Date.now()}`);
    await page.getByLabel("Assessed import source role").selectOption("books");
    for (const [label, value] of [
      ["Box 6 expected detail rows", "1"],
      ["Box 6 taxable amount (AED)", "1000"],
      ["Box 6 tax (AED)", "50"],
      ["Box 7 expected detail rows", "1"],
      ["Box 7 taxable amount (AED)", "-100"],
      ["Box 7 tax (AED)", "-5"],
      [
        "Import box scope assessment",
        "Independently assessed book declaration and correction populations for selected Boxes 6 and 7; separate filed evidence retained.",
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    const created = page.waitForResponse(
      (r) =>
        r
          .url()
          .endsWith(
            `/events/${fixture.import_box_parent}/import-vat-box-source`,
          ) && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Prepare import box source", exact: true })
      .click();
    const sourceResponse = await created;
    expect(sourceResponse.status(), await sourceResponse.text()).toBe(201);
    const source = await sourceResponse.json();
    await reviewer.goto(`/intelligence/${eid}/workflow-source`);
    await reviewer.getByLabel("Saved source or result").selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent control counts, signed import values, selected box scope and original source lineage checked.",
      );
    const sourceReview = reviewer.waitForResponse(
      (r) =>
        r.url().endsWith(`/events/${source.id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const reviewed = await sourceReview;
    expect(reviewed.status(), await reviewed.text()).toBe(201);
    const bridge = await reviewed.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-vat-return");
    const title = `SYNTHETIC reviewed import boxes versus filed VAT201 ${Date.now()}`;
    for (const [label, value] of [
      ["Schedule title", title],
      ["Reconciliation date", "2026-06-30"],
      ["Required VAT201 boxes, comma separated", "6,7"],
      [
        "Scope and source rationale",
        "Selected assessed import boxes compared with independently retained filed VAT201 evidence; no whole-return or recovery conclusion.",
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    await page
      .getByLabel("Compare only the required VAT201 boxes", { exact: true })
      .check();
    await page
      .getByLabel("Selected VAT201 box scope assessment", { exact: true })
      .fill(
        "Only import boxes 6 and 7 are assessed; all twelve other retained filed boxes remain outside this comparison and are preserved for review.",
      );
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(bridge.id);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(fixture.import_filed_source);
    const submitted = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submitted;
    expect(response.status(), await response.text()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(result);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Selected Box 6 and Box 7 values and separate filed evidence agreed; scope restricted to import boxes.",
      );
    const finalReview = reviewer.waitForResponse(
      (r) =>
        r.url().endsWith(`/events/${result}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    expect((await finalReview).status()).toBe(201);
    const panel = reviewer
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(panel.getByText("REVIEWED", { exact: true })).toBeVisible();
    const scope = panel.getByRole("region", {
      name: "Selected VAT201 comparison scope",
    });
    await expect(scope).toContainText(
      "Whole-return completeness is not determined",
    );
    await expect(scope).toContainText("return: 12 excluded rows");
    const dismiss = reviewer.getByRole("button", {
      name: "Dismiss notification",
      exact: true,
    });
    if (await dismiss.isVisible()) await dismiss.click();
    await saveScreenshot(`${shots}/uae-import-boxes-filed-comparison.png`, () =>
      panel.screenshot(),
    );
    await scope
      .getByText("Review 12 excluded VAT box rows", { exact: true })
      .click();
    await expect(
      scope.getByRole("cell", { name: "FILED-1", exact: true }),
    ).toBeVisible();
    await saveScreenshot(`${shots}/uae-vat-selected-scope-exclusions.png`, () =>
      scope.screenshot(),
    );
    await scope
      .getByText("Review 12 excluded VAT box rows", { exact: true })
      .click();
    const download = reviewer.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  } finally {
    await reviewerContext.close();
  }
});

test("UAE import VAT keeps declarations, adjustments and unresolved versions separate", async ({
  page,
}) => {
  page.setDefaultTimeout(15000);
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await expect(
    page
      .getByLabel("Workflow", { exact: true })
      .locator('option[value="uae-import-vat"]'),
  ).toHaveCount(0);
  const eid = fixture.uae_engagement;
  for (const ambiguous of [false, true]) {
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-import-vat");
    await loadRetainedHistory(page);
    const title = `SYNTHETIC UAE import VAT ${ambiguous ? "unresolved versions" : "independent comparison"} ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale")
      .fill(
        "Independently assessed customs, portal and book details; declarations and corrections compared without automatic return or recovery conclusions.",
      );
    for (const role of ["customs", "portal", "books"])
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(
          fixture.import_vat_sources[
            role === "customs" && ambiguous ? "customs-ambiguous" : role
          ],
        );
    const submitted = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submitted;
    expect(response.status(), await response.text()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    const totals = page.getByRole("table", {
      name: "Import VAT selected population totals",
    });
    await expect(
      totals.getByRole("cell", { name: "declaration / 6", exact: true }),
    ).toHaveCount(3);
    await expect(
      totals.getByRole("cell", { name: "adjustment / 7", exact: true }),
    ).toHaveCount(3);
    if (ambiguous) {
      await expect(
        page.getByRole("alert").filter({ hasText: "Approval blocked" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Independent approval", exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByRole("cell", {
          name: '["CUSTOMS_CURRENT_VERSION_UNRESOLVED"]',
          exact: true,
        }),
      ).toBeVisible();
    } else {
      await expect(
        page.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await expect(
        totals.getByRole("cell", { name: "50", exact: true }),
      ).toHaveCount(3);
      await expect(
        totals.getByRole("cell", { name: "-5", exact: true }),
      ).toHaveCount(3);
      const download = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
    }
    const dismiss = page.getByRole("button", {
      name: "Dismiss notification",
      exact: true,
    });
    if (await dismiss.isVisible()) await dismiss.click();
    await saveScreenshot(
      `${shots}/uae-import-vat-${ambiguous ? "unresolved-versions" : "declarations-adjustments"}.png`,
      () =>
        page
          .getByRole("heading", { name: title, exact: true })
          .locator("..")
          .screenshot(),
    );
    const rowRegion = page
      .getByRole("table")
      .filter({
        has: page.getByRole("columnheader", {
          name: "declaration",
          exact: true,
        }),
      })
      .locator("..");
    await rowRegion.scrollIntoViewIfNeeded();
    await saveScreenshot(
      `${shots}/uae-import-vat-${ambiguous ? "unresolved" : "matched"}-rows.png`,
      () => rowRegion.screenshot(),
    );
    if (
      await rowRegion.evaluate(
        (element) => element.scrollWidth > element.clientWidth,
      )
    ) {
      await rowRegion.evaluate((element) => {
        element.scrollLeft = element.scrollWidth;
      });
      await saveScreenshot(
        `${shots}/uae-import-vat-${ambiguous ? "unresolved" : "matched"}-row-decisions.png`,
        () => rowRegion.screenshot(),
      );
    }
  }
});

test("older approved sources remain selectable beyond 100 events", async ({
  page,
}) => {
  page.setDefaultTimeout(15000);
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(
    `/intelligence/${fixture.history_engagement}/country-workflow`,
  );
  await expect(
    page
      .getByLabel("books source", { exact: true })
      .locator(`option[value="${fixture.history_source}"]`),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Load older sources and results",
      exact: true,
    })
    .click();
  await expect(
    page
      .getByLabel("books source", { exact: true })
      .locator(`option[value="${fixture.history_source}"]`),
  ).toHaveCount(1);
  await page
    .getByLabel("books source", { exact: true })
    .selectOption(fixture.history_source);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.history_source);
  await expect(page.getByText("REVIEWED", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Load older sources and results",
      exact: true,
    }),
  ).toHaveCount(0);
  await saveScreenshot(`${shots}/older-approved-source-selection.png`, () =>
    page.screenshot({ fullPage: true }),
  );
});

test("UAE and India PDF grids preserve amounts and page provenance through the real worker", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(15000);
  const reviewerContexts = await Promise.all([
    browser.newContext({ baseURL: "http://127.0.0.1:3010" }),
    browser.newContext({ baseURL: "http://127.0.0.1:3010" }),
  ]);
  const reviewers = await Promise.all(
    reviewerContexts.map((context) => context.newPage()),
  );
  reviewers.forEach((reviewer) => reviewer.setDefaultTimeout(15000));
  async function approve(actor: Page, eid: string, button: string) {
    const response = actor.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/events/`) &&
        r.url().endsWith("/review") &&
        r.request().method() === "POST",
    );
    await actor.getByRole("button", { name: button, exact: true }).click();
    const reviewed = await response;
    expect(reviewed.status(), await reviewed.text()).toBe(201);
    return (await reviewed.json()).id as string;
  }
  async function queueWorkflow(eid: string) {
    const response = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const submitted = await response;
    expect(submitted.status(), await submitted.text()).toBe(202);
    const job = await submitted.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    return result;
  }
  try {
    for (const [index, email] of [
      fixture.pdf_table_reviewer_email,
      fixture.pdf_final_reviewer_email,
    ].entries()) {
      const reviewer = reviewers[index];
      await reviewer.goto("/login");
      await reviewer.getByLabel("Email address").fill(email);
      await reviewer
        .getByLabel("Password", { exact: true })
        .fill("synthetic-password-123");
      await reviewer
        .getByRole("button", { name: "Sign in", exact: true })
        .click();
      await reviewer.waitForURL("**/dashboard");
    }
    await page.goto("/login");
    await page.getByLabel("Email address").fill("admin@example.com");
    await page
      .getByLabel("Password", { exact: true })
      .fill("test-strong-password-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard");
    for (const [country, eid] of [
      ["AE", fixture.uae_engagement],
      ["IN", fixture.india_engagement],
    ]) {
      const layout = fixture.pdf_bank_layouts[country];
      await page.goto(`/intelligence/${eid}/source-table`);
      await page
        .getByLabel("Evidence version")
        .selectOption(fixture.pdf_bank_evidence[country]);
      await page.getByLabel("Map a PDF bank text grid").check();
      await page
        .getByLabel("PDF account header", { exact: true })
        .fill(layout.account);
      await page.getByLabel("PDF statement currency").fill(layout.currency);
      await page
        .getByLabel("PDF amount convention")
        .selectOption(layout.amount_basis);
      for (const [field, bounds] of Object.entries(layout.columns) as [
        string,
        Record<string, number>,
      ][]) {
        for (const [edge, value] of Object.entries(bounds))
          await page
            .getByLabel(`PDF ${field} column ${edge} (%)`, { exact: true })
            .fill(String(value));
      }
      for (const field of ["page", "top", "row_height", "row_count"])
        await page
          .getByLabel(`PDF grid 1 ${field.replaceAll("_", " ")}`, {
            exact: true,
          })
          .fill(String(layout.pages[0][field]));
      for (const header of ["account_header", "currency_header"])
        for (const [edge, value] of Object.entries(layout.pages[0][header]))
          await page
            .getByLabel(
              `PDF grid 1 ${header.replaceAll("_", " ")} ${edge} (%)`,
              {
                exact: true,
              },
            )
            .fill(String(value));
      await page
        .getByLabel("PDF scope and excluded-column assessment")
        .fill(layout.scope_assessment);
      await page
        .getByRole("button", { name: "Show retained PDF preview", exact: true })
        .click();
      await expect(
        page.getByAltText("Raster preview of the retained PDF page"),
      ).toBeVisible();
      await expect
        .poll(() =>
          page
            .getByAltText("Raster preview of the retained PDF page")
            .evaluate((image) => (image as HTMLImageElement).naturalWidth),
        )
        .toBeGreaterThan(0);
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-pdf-grid-mapping.png`,
        () =>
          page
            .getByRole("region", { name: "PDF text-grid mapping" })
            .screenshot(),
      );
      const submitted = page.waitForResponse(
        (r) =>
          r.url().includes(`/engagements/${eid}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue supporting tables", exact: true })
        .click();
      const response = await submitted;
      expect(response.status(), await response.text()).toBe(202);
      const job = await response.json();
      let result = "";
      await expect
        .poll(
          async () => {
            const status = await page.request.get(
              `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
              { headers: { "X-Tenant-ID": fixture.tenant } },
            );
            expect(status.status()).toBe(200);
            const body = await status.json();
            if (body.status === "failed")
              throw new Error(JSON.stringify(body.error_details));
            result = body.result_id || "";
            return body.status;
          },
          { timeout: 45000 },
        )
        .toBe("completed");
      await expect(
        page.getByLabel("Result version").locator(`option[value="${result}"]`),
      ).toHaveCount(1);
      await page.getByLabel("Result version").selectOption(result);
      await expect(
        page.getByRole("cell", { name: "100.25", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("cell", { name: "-5", exact: true }),
      ).toBeVisible();
      await page.getByLabel("Show all supporting-table provenance").check();
      await expect(
        page.getByRole("columnheader", {
          name: "source_pdf_bbox",
          exact: true,
        }),
      ).toBeVisible();
      await reviewers[0].goto(
        `/intelligence/${eid}/source-table?event=${result}`,
      );
      await reviewers[0].getByLabel("Result version").selectOption(result);
      await expect(
        reviewers[0].getByRole("cell", { name: "100.25", exact: true }),
      ).toBeVisible();
      await reviewers[0]
        .getByLabel("Auditor rationale / review comments")
        .fill(
          "Independently checked synthetic PDF row population, verified headers, sign convention and page provenance against original evidence.",
        );
      const approvedTable = await approve(
        reviewers[0],
        eid,
        "Record independent approval",
      );
      await page.goto(`/intelligence/${eid}/workflow-source`);
      await page.getByLabel("Source origin").selectOption("supporting");
      await page
        .getByLabel("Reviewed supporting bank table")
        .selectOption(approvedTable);
      await page
        .getByLabel("Schedule title", { exact: true })
        .fill(`SYNTHETIC ${country} PDF bridge ${Date.now()}`);
      await page.getByLabel("Bank account identifier").fill("BANK-1");
      await page
        .getByLabel("Supporting bank account scope assessment")
        .fill(
          "Independent selected PDF population checked against retained original account and currency headers.",
        );
      await page.getByLabel("Expected data rows").fill("2");
      await page
        .getByLabel("Independent totals by currency")
        .fill(`${layout.currency}=95.25`);
      const bridge = await queueWorkflow(eid);
      await reviewers[1].goto(`/intelligence/${eid}/workflow-source`);
      await reviewers[1]
        .getByLabel("Saved source or result")
        .selectOption(bridge);
      await reviewers[1]
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent control totals and original PDF lineage checked before approval.",
        );
      const approvedBridge = await approve(
        reviewers[1],
        eid,
        "Independent approval",
      );
      await page.goto(`/intelligence/${eid}/country-workflow`);
      const title = `SYNTHETIC ${country} PDF bank reconciliation ${Date.now()}`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["Bank account identifier", "BANK-1"],
        ["Account currency", layout.currency],
        ["book opening", "0"],
        ["book closing", "95.25"],
        ["statement opening", "0"],
        ["statement closing", "95.25"],
        [
          "Scope and source rationale",
          "Independent cashbook compared to reviewed retained PDF statement with independent opening and closing controls.",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      await page
        .getByLabel("books source", { exact: true })
        .selectOption(fixture.pdf_bank_books[country]);
      await page
        .getByLabel("statement source", { exact: true })
        .selectOption(approvedBridge);
      const reconciliation = await queueWorkflow(eid);
      await expect(
        page.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await reviewers[1].goto(`/intelligence/${eid}/country-workflow`);
      await reviewers[1]
        .getByLabel("Saved source or result")
        .selectOption(reconciliation);
      await reviewers[1]
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent cashbook and statement comparison, balances and zero exceptions checked.",
        );
      await approve(reviewers[1], eid, "Independent approval");
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-pdf-bank-reconciliation.png`,
        () =>
          page
            .getByRole("heading", { name: title, exact: true })
            .locator("..")
            .screenshot(),
      );
    }
  } finally {
    await Promise.all(reviewerContexts.map((context) => context.close()));
  }
});

test("UAE and India credit applications preserve residuals through the real worker", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  for (const [country, eid, currency] of [
    ["AE", fixture.uae_engagement, "AED"],
    ["IN", fixture.india_engagement, "INR"],
  ]) {
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await loadRetainedHistory(page);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("credit-note-applications");
    const title = `SYNTHETIC ${country} credit application ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale")
      .fill(
        "Reviewed explicit credit applications against independent GL controls; no tax treatment inferred",
      );
    for (const [role, id] of Object.entries(
      fixture.credit_application_sources[country],
    ))
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(String(id));
    await page
      .getByRole("checkbox", {
        name: /Balances are before the listed credit applications/,
      })
      .check();
    const submitted = page.waitForResponse(
      (response) =>
        response.url().includes(`/engagements/${eid}/jobs`) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          expect(status.status()).toBe(200);
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByRole("cell", { name: "UNAPPLIED_CREDIT", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "75", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "-15", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: currency, exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText("1 exceptions", { exact: true })).toBeVisible();
    await panel.scrollIntoViewIfNeeded();
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-credit-applications-worker.png`,
      () => panel.screenshot(),
    );
  }
  expect(errors).toEqual([]);
});

test("India withholding separates legal roles and excludes superseded observations through the worker", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  for (const workflow of [
    "india-withholding-liability",
    "india-withholding-credit",
    "india-withholding",
  ])
    await expect(
      page
        .getByLabel("Workflow", { exact: true })
        .locator(`option[value="${workflow}"]`),
    ).toHaveCount(0);
  const eid = fixture.india_engagement;
  for (const scope of ["deductor", "collectee", "collectee-cap"]) {
    const legalRole = scope === "deductor" ? "deductor" : "collectee";
    const workflow =
      legalRole === "deductor"
        ? "india-withholding-liability"
        : "india-withholding-credit";
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page.getByLabel("Workflow", { exact: true }).selectOption(workflow);
    await page
      .getByLabel("Organization legal withholding role")
      .selectOption(legalRole);
    const title = `SYNTHETIC ${scope} withholding ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale")
      .fill(
        "Independently assessed legal role and current source selection; no statutory rate or credit entitlement inferred",
      );
    for (const [role, identifier] of Object.entries(
      fixture.withholding_sources[scope],
    ))
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(String(identifier));
    const submitted = page.waitForResponse(
      (response) =>
        response.url().includes(`/engagements/${eid}/jobs`) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          expect(status.status()).toBe(200);
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByRole("cell", { name: legalRole, exact: true }).first(),
    ).toBeVisible();
    await expect(
      panel
        .getByRole("cell", {
          name:
            scope === "collectee-cap"
              ? "ASSESSMENT_NOT_SUPPORTED"
              : legalRole === "deductor"
                ? "VARIANCE"
                : "MATCHED",
          exact: true,
        })
        .first(),
    ).toBeVisible();
    if (scope === "collectee-cap") {
      await expect(
        panel
          .getByText("certificate shared amount limit exceeded", {
            exact: true,
          })
          .first(),
      ).toBeVisible();
      await expect(
        panel.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
    }
    if (legalRole === "deductor") {
      await expect(
        panel.getByRole("cell", { name: /reported: 90/ }),
      ).toBeVisible();
      await expect(
        panel.getByRole("cell", { name: /reported: -10/ }),
      ).toBeVisible();
    }
    await panel.scrollIntoViewIfNeeded();
    await saveScreenshot(`${shots}/india-${scope}-withholding-worker.png`, () =>
      panel.screenshot(),
    );
    await panel.getByLabel("Show source provenance and all columns").check();
    await expect(
      panel.getByRole("cell", { name: "NOT_DETERMINED", exact: true }).first(),
    ).toBeVisible();
    await expect(panel.getByRole("cell", { name: /superseded/ })).toBeVisible();
    const download = page.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    await expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  }
  expect(errors).toEqual([]);
});

async function loadRetainedHistory(page: Page) {
  const load = page.getByRole("button", {
    name: "Load older source choices",
    exact: true,
  });
  const saved = page.getByLabel("Saved source or result");
  await expect(saved).toBeVisible();
  // These shared fixture engagements deliberately contain more than 100 events.
  // Wait for both initial history requests before inspecting pagination state.
  await expect(load).toBeVisible();
  for (let pageNumber = 0; pageNumber < 50; pageNumber++) {
    if (!(await load.count())) return;
    const previousCount = await saved.locator("option").count();
    await load.click();
    await expect
      .poll(
        async () =>
          (await saved.locator("option").count()) > previousCount ||
          !(await load.count()),
      )
      .toBe(true);
  }
  throw new Error("Retained history exceeds the browser fixture page bound");
}

function implementationHash() {
  execFileSync(
    resolve("../backend/.venv/Scripts/python.exe"),
    [resolve("../scripts/check_utf8_sources.py")],
    { cwd: resolve(".."), encoding: "utf8" },
  );
  return execFileSync(
    resolve("../backend/.venv/Scripts/python.exe"),
    [
      resolve("../scripts/country_workflows_run.py"),
      ".venv/Scripts/python.exe",
      "-c",
      "from app.core.operations_contracts import country_workflow_hash; print(country_workflow_hash())",
    ],
    { cwd: resolve(".."), encoding: "utf8" },
  ).trim();
}
test.beforeAll(() =>
  expect(
    implementationHash(),
    "Prepare fresh browser fixtures for the current backend implementation",
  ).toBe(fixture.implementation_sha256),
);
test.afterAll(() =>
  expect(
    implementationHash(),
    "Backend changed during browser verification; results require a fresh fixture run",
  ).toBe(fixture.implementation_sha256),
);

async function saveScreenshot(path: string, capture: () => Promise<Buffer>) {
  const content = await capture();
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      writeFileSync(path, content);
      return;
    } catch (error) {
      if (
        !["UNKNOWN", "EBUSY", "EPERM"].includes(
          (error as NodeJS.ErrnoException).code || "",
        )
      )
        throw error;
      await new Promise((resolve) => setTimeout(resolve, 150 * (attempt + 1)));
    }
  }
  const alternate = path.replace(/\.png$/, `-${Date.now()}.png`);
  writeFileSync(alternate, content);
  await test
    .info()
    .attach("Screenshot retained at alternate path after Windows file lock", {
      path: alternate,
      contentType: "image/png",
    });
}

test("UAE source controls, BRS exceptions, exports and India isolation", async ({
  page,
}) => {
  test.setTimeout(300000);
  const runSuffix = Date.now().toString();
  const queuedBRSTitle = `SYNTHETIC queued browser BRS ${runSuffix}`;
  const payrollTitle = `SYNTHETIC queued reviewed payroll calculation ${runSuffix}`;
  let gstr2bSource = "";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  await loadRetainedHistory(page);
  await expect(
    page.getByRole("heading", { name: "Reconcile and assess evidence" }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "India GST document reconciliation" }),
  ).toHaveCount(0);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.uae_result);
  await expect(
    page.getByText("SYNTHETIC account reconciliation", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("UNPRESENTED_PAYMENT_CANDIDATE", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", {
      name: "UNCREDITED_DEPOSIT_CANDIDATE",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "UNBOOKED_BANK_ITEM", exact: true }),
  ).toBeVisible();
  await saveScreenshot(`${shots}/uae-bank-review.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export XLSX", exact: true }).click();
  await expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  await page
    .getByRole("link", { name: "Prepare sources", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Prepare controlled source tables" }),
  ).toBeVisible();
  await page.getByText("CSV field contract", { exact: true }).click();
  await expect(
    page.getByText("amount · required", { exact: true }),
  ).toBeVisible();
  await saveScreenshot(`${shots}/controlled-source-import.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await loadRetainedHistory(page);
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "UAE VAT document reconciliation" }),
  ).toHaveCount(0);
  await expect(
    page
      .getByLabel("Workflow")
      .getByRole("option", { name: "India GST document reconciliation" }),
  ).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.india_result);
  await expect(
    page.getByRole("cell", { name: "VARIANCE", exact: true }),
  ).toBeVisible();
  await page
    .getByText("Country-specific scope guidance", { exact: true })
    .click();
  await expect(
    page.getByText("Form 26 under 2025 Act / 2026 Rules", { exact: true }),
  ).toBeVisible();
  await saveScreenshot(`${shots}/india-gst-review.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  await loadRetainedHistory(page);
  await page
    .getByLabel("Saved source or result")
    .selectOption(fixture.uae_vat_result);
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC UAE VAT201 box bridge",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "1:DXB", exact: true }),
  ).toBeVisible();
  await saveScreenshot(`${shots}/uae-vat201-bridge.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  for (const [label, value] of [
    ["Schedule title", queuedBRSTitle],
    ["Reconciliation date", "2026-06-30"],
    ["Bank account identifier", "BANK-1"],
    ["book opening", "0"],
    ["book closing", "100"],
    ["statement opening", "0"],
    ["statement closing", "95"],
    [
      "Scope and source rationale",
      "Synthetic browser-to-Redis-to-worker execution using retained sources",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByLabel("books source", { exact: true })
    .selectOption(fixture.uae_book_source);
  await page
    .getByLabel("statement source", { exact: true })
    .selectOption(fixture.uae_statement_source);
  const queued = page.waitForResponse(
    (r) =>
      r.url().includes(`/engagements/${fixture.uae_engagement}/jobs`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await queued).status()).toBe(202);
  await expect(
    page.getByRole("button", { name: "Open result", exact: true }).first(),
  ).toBeVisible();
  await expect
    .poll(async () =>
      page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(queuedBRSTitle) })
        .count(),
    )
    .toBe(1);
  await page
    .getByRole("button", { name: "Open result", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", {
      name: queuedBRSTitle,
      exact: true,
    }),
  ).toBeVisible();
  await saveScreenshot(`${shots}/real-worker-result.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  expect(errors).toEqual([]);
  for (const source of [
    {
      engagement: fixture.uae_engagement,
      format: "camt053",
      evidence: fixture.camt_evidence,
      count: "2",
      total: "AED=95",
      title: `SYNTHETIC native browser CAMT ${runSuffix}`,
    },
    {
      engagement: fixture.uae_engagement,
      format: "swift-mt940",
      evidence: fixture.mt940_evidence,
      count: "2",
      total: "AED=95",
      title: `SYNTHETIC paged browser MT940 UAE ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "swift-mt940",
      evidence: fixture.india_mt940_evidence,
      count: "2",
      total: "INR=95",
      title: `SYNTHETIC paged browser MT940 India ${runSuffix}`,
    },
    {
      engagement: fixture.uae_engagement,
      format: "uae-wps-sif",
      evidence: fixture.wps_evidence,
      count: "2",
      total: "AED=1500",
      title: `SYNTHETIC native browser WPS ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-inv01-json",
      evidence: fixture.india_invoice_evidence,
      count: "5",
      total: "INR=18",
      title: `SYNTHETIC native browser INV01 ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-epfo-ecr",
      evidence: fixture.india_ecr_evidence,
      count: "7",
      total: "INR=6100",
      title: `SYNTHETIC native browser ECR ${runSuffix}`,
    },
    {
      engagement: fixture.india_engagement,
      format: "india-gstr2b-json",
      evidence: fixture.india_gstr2b_evidence,
      count: "4",
      total: "INR=18",
      title: `SYNTHETIC native browser GSTR2B ${runSuffix}`,
    },
  ]) {
    await page.goto(`/intelligence/${source.engagement}/workflow-source`);
    await loadRetainedHistory(page);
    await page.getByLabel("Source file format").selectOption(source.format);
    await page.getByLabel("Schedule title", { exact: true }).fill(source.title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(source.evidence);
    await page.getByLabel("Expected data rows").fill(source.count);
    await page.getByLabel("Independent totals by currency").fill(source.total);
    if (source.format === "swift-mt940") {
      await page
        .getByLabel("First message reference (optional cross-check)")
        .fill("SYN-PAGE-1");
    }
    if (source.format === "india-epfo-ecr") {
      await page
        .getByLabel("EPFO establishment registration")
        .fill("SYNTHETIC-EPFO-001");
      await page.getByLabel("ECR wage month").fill("2026-06");
      await page.getByLabel("Independent ECR member count").fill("2");
    }
    if (source.format === "india-gstr2b-json") {
      await page.getByLabel("Recipient GSTIN").fill("27ABCDE5678G1Z8");
      await page.getByLabel("GSTR-2B return month").fill("2026-06");
      await page.getByLabel("Independent GSTR-2B document count").fill("1");
    }
    if (source.format === "india-inv01-json") {
      await page.getByLabel("Entity GSTIN").fill("27ABCDE5678G1Z8");
      await page.getByLabel("Invoice direction").selectOption("purchase");
      await page.getByLabel("Reporting month").fill("2026-06");
      await expect(
        page
          .getByLabel("Source file format")
          .getByRole("option", { name: /UAE WPS/ }),
      ).toHaveCount(0);
    } else if (source.engagement === fixture.uae_engagement) {
      await expect(
        page
          .getByLabel("Source file format")
          .getByRole("option", { name: /India INV-01/ }),
      ).toHaveCount(0);
    }
    const queuedNative = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${source.engagement}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    expect((await queuedNative).status()).toBe(202);
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(source.title) });
    await expect(option).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await option.getAttribute("value"))!);
    await expect(
      page.getByRole("heading", { name: source.title, exact: true }),
    ).toBeVisible();
    await page
      .getByText("Original source controls and calculation basis", {
        exact: true,
      })
      .click();
    if (source.format === "uae-wps-sif")
      await expect(
        page.getByText("NOT_EVIDENCED_BY_INSTRUCTION_FILE", { exact: true }),
      ).toBeVisible();
    if (source.format === "camt053") {
      const pages = page.getByRole("table", {
        name: "CAMT statement page controls",
        exact: true,
      });
      await expect(pages.getByRole("row")).toHaveCount(4);
      await expect(pages.getByRole("row").nth(2)).toContainText("100.00");
      await expect(pages.getByRole("row").nth(3)).toContainText("95.00");
      await saveScreenshot(`${shots}/camt053-statement-page-controls.png`, () =>
        pages.screenshot(),
      );
    }
    if (source.format === "swift-mt940") {
      const messages = page.getByRole("table", {
        name: "MT940 message controls",
        exact: true,
      });
      await expect(messages.getByRole("row")).toHaveCount(4);
      await expect(messages.getByRole("row").nth(2)).toContainText(
        "SYN-PAGE-2",
      );
      await saveScreenshot(
        `${shots}/swift-mt940-${source.engagement === fixture.uae_engagement ? "ae" : "in"}-message-controls.png`,
        () => messages.screenshot(),
      );
    }
    if (source.format === "india-epfo-ecr")
      await expect(
        page.getByText("NOT_EVIDENCED_BY_RETURN_TEXT", { exact: true }).first(),
      ).toBeVisible();
    if (source.format === "india-inv01-json")
      await expect(
        page.getByText(
          "FIVE_TAX_COMPONENTS_PER_DOCUMENT_INCLUDING_ZERO_COMPONENTS",
          { exact: true },
        ),
      ).toBeVisible();
    if (source.format === "india-gstr2b-json") {
      gstr2bSource = (await option.getAttribute("value"))!;
      await expect(
        page.getByText("FOUR_TAX_COMPONENT_ROWS_PER_SOURCE_DOCUMENT", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByText(
          "SUM_OF_DOCUMENT_TAX_FIELDS_INCLUDING_REVERSALS_NOT_ITC_ENTITLEMENT",
          { exact: true },
        ),
      ).toBeVisible();
    }
    if (source.format === "swift-mt940") {
      await expect(
        page.getByText("mt940-sequenced-messages/1", { exact: true }),
      ).toBeVisible();
    }
    await saveScreenshot(
      `${shots}/${source.format}${source.format === "swift-mt940" ? (source.engagement === fixture.uae_engagement ? "-ae" : "-in") : ""}-native-review.png`,
      () => page.screenshot({ fullPage: true }),
    );
  }
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await loadRetainedHistory(page);
  await page.getByLabel("Workflow", { exact: true }).selectOption("india-gst");
  const gstTitle = `SYNTHETIC queued native GST comparison ${runSuffix}`;
  await page.getByLabel("Schedule title", { exact: true }).fill(gstTitle);
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("books source", { exact: true })
    .selectOption(fixture.india_gstr2b_books);
  await page
    .getByLabel("return source", { exact: true })
    .selectOption(gstr2bSource);
  await page
    .getByLabel("Scope and source rationale", { exact: true })
    .fill(
      "Independent book register compared against native GSTR-2B source components",
    );
  const gstQueued = page.waitForResponse(
    (response) =>
      response
        .url()
        .includes(`/engagements/${fixture.india_engagement}/jobs`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await gstQueued).status()).toBe(202);
  const gstOption = page
    .getByLabel("Saved source or result")
    .getByRole("option", { name: new RegExp(gstTitle) });
  await expect(gstOption).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption((await gstOption.getAttribute("value"))!);
  await expect(
    page.getByRole("heading", { name: gstTitle, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
  await saveScreenshot(`${shots}/india-native-gstr2b-reconciliation.png`, () =>
    page
      .getByRole("heading", { name: gstTitle, exact: true })
      .locator("..")
      .screenshot(),
  );
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
  await loadRetainedHistory(page);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("india-payroll-rules");
  await page.getByLabel("Schedule title", { exact: true }).fill(payrollTitle);
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("bases source", { exact: true })
    .selectOption(fixture.india_payroll_bases);
  await page
    .getByLabel("rules source", { exact: true })
    .selectOption(fixture.india_payroll_rules);
  await page
    .getByLabel("reported source", { exact: true })
    .selectOption(fixture.india_payroll_reported);
  await page
    .getByLabel("Scope and source rationale", { exact: true })
    .fill(
      "Independent source-bound rules and assessed wage bases compared to ECR",
    );
  const payrollQueued = page.waitForResponse(
    (r) =>
      r.url().includes(`/engagements/${fixture.india_engagement}/jobs`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  expect((await payrollQueued).status()).toBe(202);
  const payrollOption = page
    .getByLabel("Saved source or result")
    .getByRole("option", {
      name: new RegExp(payrollTitle),
    });
  await expect(payrollOption).toHaveCount(1);
  await page
    .getByLabel("Saved source or result")
    .selectOption((await payrollOption.getAttribute("value"))!);
  await expect(
    page.getByRole("heading", {
      name: payrollTitle,
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
  await saveScreenshot(`${shots}/india-payroll-contribution-summary.png`, () =>
    page
      .getByRole("heading", { name: payrollTitle, exact: true })
      .locator("..")
      .screenshot(),
  );
  await page.getByLabel("Show rule provenance and source references").check();
  await expect(
    page.getByRole("cell", { name: "employer-minus-eps", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", {
      name: "NOT_PERFORMED_BY_CONTRIBUTION_REVIEW",
      exact: true,
    }),
  ).toHaveCount(3);
  await saveScreenshot(`${shots}/india-payroll-rule-review.png`, () =>
    page.screenshot({ fullPage: true }),
  );
  expect(errors).toEqual([]);
});

test("original CSV and reviewed XLSX tables reach bank and payable reconciliations", async ({
  page,
}) => {
  const suffix = Date.now().toString();
  const eid = fixture.uae_engagement;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  async function fill(values: [string, string][]) {
    for (const [label, value] of values)
      await page.getByLabel(label, { exact: true }).fill(value);
  }
  async function captureResult(title: string, filename: string) {
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await panel.scrollIntoViewIfNeeded();
    await saveScreenshot(`${shots}/${filename}`, () => panel.screenshot());
  }
  async function queue(
    button = "Queue calculation",
    picker = "Saved source or result",
  ) {
    const submitted = page.waitForResponse(
      (response) =>
        response.url().includes(`/engagements/${eid}/jobs`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: button, exact: true }).click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const status = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          expect(status.status()).toBe(200);
          const body = await status.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page.getByLabel(picker).locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel(picker).selectOption(result);
    return result;
  }
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");

  await page.goto(`/intelligence/${eid}/source-table`);
  await page
    .getByLabel("Evidence version")
    .selectOption(fixture.xlsx_bank_evidence);
  await page
    .getByLabel("Worksheet name (required for multi-sheet XLSX)")
    .fill("Selected");
  await queue("Queue supporting tables", "Result version");
  await page
    .getByText("Supporting table layout and worksheet controls", {
      exact: true,
    })
    .click();
  await expect(
    page.getByText("ORIGINAL_XML_DECIMALS_NOT_FLOAT_ROUNDTRIP", {
      exact: true,
    }),
  ).toBeVisible();
  await captureResult(
    "Results and preserved history",
    "xlsx-table-worker-review.png",
  );

  await page.goto(`/intelligence/${eid}/workflow-source`);
  await loadRetainedHistory(page);
  const mappedTitle = `SYNTHETIC mapped bank browser ${suffix}`;
  await page.getByLabel("Map original CSV columns").check();
  await page.getByLabel("CSV separator").selectOption(";");
  await page
    .getByLabel("Transaction amount columns")
    .selectOption("debit-positive");
  await fill([
    ["Schedule title", mappedTitle],
    ["CSV column for id", "رقم"],
    ["CSV column for account", "Account"],
    ["CSV column for date", "Date"],
    ["CSV column for currency", "CCY"],
    ["Original debit column", "Debit"],
    ["Original credit column", "Credit"],
    ["Excluded CSV columns, one exact heading per line", "Description"],
    [
      "Column mapping and exclusion assessment",
      "Reviewed synthetic source headings and debit-minus-credit basis; memo retained in original evidence",
    ],
    ["Expected data rows", "2"],
    ["Independent totals by currency", "AED=95.25"],
  ]);
  await page
    .getByLabel("Clean retained evidence")
    .selectOption(fixture.mapped_bank_evidence);
  const mapped = await queue();
  await expect(
    page.getByRole("heading", { name: mappedTitle, exact: true }),
  ).toBeVisible();
  await page
    .getByText("Original CSV column mapping and exclusions", { exact: true })
    .click();
  await expect(
    page.getByText("Excluded columns: Description", { exact: true }),
  ).toBeVisible();
  await captureResult(mappedTitle, "mapped-debit-credit-worker-review.png");

  await page.goto(`/intelligence/${eid}/workflow-source`);
  await loadRetainedHistory(page);
  const bankTitle = `SYNTHETIC reviewed XLSX bank browser ${suffix}`;
  await page.getByLabel("Source origin").selectOption("supporting");
  await page
    .getByLabel("Reviewed supporting bank table")
    .selectOption(fixture.reviewed_xlsx_bank);
  await fill([
    ["Schedule title", bankTitle],
    ["Bank account identifier", "BANK-1"],
    [
      "Supporting bank account scope assessment",
      "Reviewed complete Selected worksheet bank population and original account evidence",
    ],
    ["Expected data rows", "2"],
    ["Independent totals by currency", "AED=95.25"],
  ]);
  const bank = await queue();
  await expect(
    page.getByRole("heading", { name: bankTitle, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Open reviewed supporting table",
      exact: true,
    }),
  ).toBeVisible();
  await captureResult(bankTitle, "reviewed-xlsx-bank-source.png");
  for (const [kind, statement] of [
    ["mapped", mapped],
    ["xlsx", bank],
  ]) {
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await loadRetainedHistory(page);
    const title = `SYNTHETIC ${kind} bank reconciliation ${suffix}`;
    await fill([
      ["Schedule title", title],
      ["Reconciliation date", "2026-06-30"],
      ["Bank account identifier", "BANK-1"],
      ["book opening", "0"],
      ["book closing", "95.25"],
      ["statement opening", "0"],
      ["statement closing", "95.25"],
      [
        "Scope and source rationale",
        "Independent cashbook compared to retained original source through the real worker",
      ],
    ]);
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(fixture.extended_book_source);
    await page
      .getByLabel("statement source", { exact: true })
      .selectOption(statement);
    await queue();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
    await captureResult(title, `${kind}-bank-reconciliation-worker.png`);
  }

  await page.goto(`/intelligence/${eid}/workflow-source`);
  await loadRetainedHistory(page);
  const itemsTitle = `SYNTHETIC reviewed XLSX payables ${suffix}`;
  await page.getByLabel("Source origin").selectOption("supporting-items");
  await page
    .getByLabel("Reviewed supporting open-item table")
    .selectOption(fixture.reviewed_xlsx_open_items);
  await page.getByLabel("Open-item subledger side").selectOption("payable");
  await page.getByLabel("Open-item source sign").selectOption("reverse-sign");
  await fill([
    ["Schedule title", itemsTitle],
    ["Control account identifier", "AP-1"],
    ["Open-item balance date", "2026-06-30"],
    [
      "Supporting open-item scope assessment",
      "Reviewed complete Selected worksheet payable population and credit-negative source convention",
    ],
    ["Expected data rows", "2"],
    ["Independent totals by currency", "AED=80"],
  ]);
  const items = await queue();
  await expect(
    page.getByRole("heading", { name: itemsTitle, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "credit-note", exact: true }),
  ).toBeVisible();
  await captureResult(itemsTitle, "reviewed-xlsx-payable-sign-source.png");
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await loadRetainedHistory(page);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("subledger-control");
  const controlTitle = `SYNTHETIC bridged payable control ${suffix}`;
  await fill([
    ["Schedule title", controlTitle],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "Independent payable control account compared to reviewed original XLSX open items",
    ],
  ]);
  await page.getByLabel("items source", { exact: true }).selectOption(items);
  await page
    .getByLabel("controls source", { exact: true })
    .selectOption(fixture.payable_controls);
  await queue();
  await expect(
    page.getByRole("heading", { name: controlTitle, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("0 exceptions", { exact: true })).toBeVisible();
  await captureResult(controlTitle, "reviewed-xlsx-payable-control-worker.png");
  expect(errors).toEqual([]);
});

test("numbered GSTR-2B originals require review before purchase-register matching", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const eid = fixture.india_engagement;
  const input = fixture.gstr2b_bundle_input;
  const title = `SYNTHETIC numbered GSTR-2B ${Date.now()}`;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_table_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source file format")
      .selectOption("india-gstr2b-json");
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(input.evidence_version_id);
    await page.getByLabel("Recipient GSTIN").fill("27ABCDE5678G1Z8");
    await page.getByLabel("GSTR-2B return month").fill("2026-06");
    await page.getByLabel("Independent GSTR-2B document count").fill("2");
    await page.getByLabel("Independent totals by currency").fill("INR=27");
    await page.getByLabel("Assemble numbered GSTR-2B files").check();
    await page.getByLabel("Independent GSTR-2B file count").fill("2");
    await page
      .getByLabel("Original response parts and independent controls (JSON)")
      .fill(JSON.stringify(input.gstr2b_parts, null, 2));
    await page
      .getByLabel("GSTR-2B retrieval batch assessment")
      .fill(input.gstr2b_retrieval_assessment);
    await saveScreenshot(
      `${shots}/india-gstr2b-numbered-file-controls.png`,
      () =>
        page
          .getByRole("group", { name: "Numbered GSTR-2B response files" })
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    const id = (await option.getAttribute("value"))!;
    const detail = await page.request.get(
      `/api/backend/intelligence/engagements/${eid}/events/${id}`,
      { headers: { "X-Tenant-ID": fixture.tenant } },
    );
    expect(detail.status()).toBe(200);
    const prepared = await detail.json();
    expect(prepared.body.rows).toHaveLength(8);
    expect(
      new Set(
        prepared.body.rows.map(
          (row: { source_part_evidence_version_id: string }) =>
            row.source_part_evidence_version_id,
        ),
      ),
    ).toEqual(
      new Set(
        input.gstr2b_parts.map(
          (part: { evidence_version_id: string }) => part.evidence_version_id,
        ),
      ),
    );
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent original manifest, numbered request references and separate per-file controls reviewed for this synthetic batch",
      );
    const approval = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approvedResponse = await approval;
    expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
    const approved = await approvedResponse.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("india-gst");
    await expect(
      page
        .getByLabel("books source", { exact: true })
        .locator(`option[value="${approved.id}"]`),
    ).toHaveCount(0);
    await page
      .getByLabel("Schedule title", { exact: true })
      .fill(title + " comparison");
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(fixture.gstr2b_bundle_books);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(approved.id);
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Independent purchase register compared with the reviewed complete numbered response set",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const result = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title + " comparison") });
    await expect(result).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await result.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title + " comparison", exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(8);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/india-gstr2b-numbered-file-comparison.png`,
      () => panel.screenshot(),
    );
  } finally {
    await context.close();
  }
});

test("UAE reviewed import boxes compose with other VAT201 books before filed comparison", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const eid = fixture.uae_engagement;
  const title = `SYNTHETIC composed VAT201 ${Date.now()}`;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_table_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByText("Compose reviewed VAT201 book schedules", { exact: true })
      .click();
    await page.getByLabel("Composed VAT201 source title").fill(title);
    await page
      .getByLabel("Reviewed VAT201 component schedules")
      .selectOption(fixture.vat_composition_sources);
    for (const [label, value] of [
      ["Independent composed taxable amount", "2400"],
      ["Independent composed tax total", "230"],
      ["Independent composed adjustment total", "0"],
      [
        "VAT201 composition scope assessment",
        "Independent import book boxes 6 and 7 plus twelve other explicit book boxes; all fourteen boxes assessed without overlap",
      ],
    ])
      await page.getByLabel(label).fill(value);
    await saveScreenshot(`${shots}/uae-vat201-composition-controls.png`, () =>
      page
        .getByText("Compose reviewed VAT201 book schedules", { exact: true })
        .locator("..")
        .screenshot(),
    );
    const creating = page.waitForResponse(
      (r) =>
        r.url().includes("/vat201-composition-source") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", {
        name: "Prepare composed VAT201 books",
        exact: true,
      })
      .click();
    const response = await creating;
    expect(response.status(), await response.text()).toBe(201);
    const created = await response.json();
    expect(created.body.rows).toHaveLength(14);
    expect(
      new Set(
        created.body.rows.map(
          (row: { source_component_event_id: string }) =>
            row.source_component_event_id,
        ),
      ),
    ).toEqual(new Set(fixture.vat_composition_sources));
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer
      .getByLabel("Saved source or result")
      .selectOption(created.id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent reviewed parent schedules, complete explicit disjoint boxes and whole-schedule controls checked",
      );
    const approval = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${created.id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approvedResponse = await approval;
    expect(approvedResponse.status(), await approvedResponse.text()).toBe(201);
    const approved = await approvedResponse.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-vat-return");
    await expect(
      page
        .getByLabel("return source", { exact: true })
        .locator(`option[value="${approved.id}"]`),
    ).toHaveCount(0);
    await page
      .getByLabel("Schedule title", { exact: true })
      .fill(title + " comparison");
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(approved.id);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(fixture.import_filed_source);
    await page
      .getByLabel("Required VAT201 boxes, comma separated", { exact: true })
      .fill("1,2,3,4,5,6,7,8,9,10,11,12,13,14");
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Complete explicit composed book boxes compared with separate retained filed evidence; no legal completeness inference",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title + " comparison") });
    await expect(option).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await option.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title + " comparison", exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(14);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await expect(
      panel.getByRole("columnheader", { name: "tax difference", exact: true }),
    ).toBeVisible();
    const provenance = panel.getByLabel(
      "Show source versions and review details",
    );
    await provenance.check();
    await expect(
      panel.getByRole("columnheader", { name: "book source ids", exact: true }),
    ).toBeVisible();
    await provenance.uncheck();
    await saveScreenshot(
      `${shots}/uae-vat201-composed-books-comparison.png`,
      () => panel.screenshot(),
    );
  } finally {
    await context.close();
  }
});

test("UAE WPS EVP preparation preserves variable-pay controls without duplicating salary", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const eid = fixture.uae_engagement;
  const input = fixture.wps_evp_input;
  const title = `SYNTHETIC WPS EVP ${Date.now()}`;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_table_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page.getByLabel("Source file format").selectOption("uae-wps-sif-evp");
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(input.evidence_version_id);
    await page.getByLabel("Expected data rows").fill("2");
    await page.getByLabel("Independent totals by currency").fill("AED=1500");
    await page
      .getByLabel("Employer registration cross-check (optional)")
      .fill("1234567890123");
    await page.getByLabel("Independent EVP record count").fill("1");
    await page
      .getByLabel("Independent EVP component totals (AED, JSON)")
      .fill(JSON.stringify(input.wps_variable_pay_totals, null, 2));
    await saveScreenshot(`${shots}/uae-wps-evp-source-controls.png`, () =>
      page
        .getByRole("group", { name: "WPS variable-pay component controls" })
        .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    const id = (await option.getAttribute("value"))!;
    await page.getByLabel("Saved source or result").selectOption(id);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByRole("columnheader", { name: "variable income", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "1100.00", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "400.00", exact: true }).first(),
    ).toBeVisible();
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(`${shots}/uae-wps-evp-salary-summary.png`, () =>
      panel.screenshot(),
    );
    await panel
      .getByText("Original source controls and calculation basis", {
        exact: true,
      })
      .click();
    const controls = panel.getByRole("table", {
      name: "WPS variable-pay component controls",
      exact: true,
    });
    await expect(controls.getByRole("row")).toHaveCount(8);
    await expect(controls.getByRole("row").nth(1)).toContainText(
      "housing allowance",
    );
    await expect(
      controls.getByRole("row").filter({ hasText: "housing allowance" }),
    ).toContainText("40.00");
    await expect(
      panel.getByText("NOT_EVIDENCED_BY_INSTRUCTION_FILE", { exact: true }),
    ).toBeVisible();
    await saveScreenshot(`${shots}/uae-wps-evp-component-controls.png`, () =>
      controls.screenshot(),
    );
    const detail = await page.request.get(
      `/api/backend/intelligence/engagements/${eid}/events/${id}`,
      { headers: { "X-Tenant-ID": fixture.tenant } },
    );
    expect(detail.status()).toBe(200);
    const source = await detail.json();
    expect(source.body.rows).toHaveLength(2);
    expect(source.body.control_totals.AED).toBe("1500.00");
    expect(
      source.body.rows.map((row: { source_row: number }) => row.source_row),
    ).toEqual([1, 3]);
    expect(
      source.body.rows.every(
        (row: { payment_date: unknown }) => row.payment_date === null,
      ),
    ).toBe(true);
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent original EDR/EVP employee binding, declared component controls and SCR salary reviewed; no payment execution inference",
      );
    const approving = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approval = await approving;
    expect(approval.status(), await approval.text()).toBe(201);
    const approved = await approval.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("payroll-settlement");
    await expect(
      page
        .getByLabel("channel source", { exact: true })
        .locator(`option[value="${approved.id}"]`),
    ).toHaveCount(1);
    for (const role of ["payroll", "bank"])
      await expect(
        page
          .getByLabel(`${role} source`, { exact: true })
          .locator(`option[value="${approved.id}"]`),
      ).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test("UAE then India controlled inventory bridges earlier and later lot counts", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_table_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    for (const country of ["AE", "IN"] as const) {
      const input = fixture.inventory_controls[country];
      const eid = input.engagement;
      const sourceTitle = `SYNTHETIC ${country} inventory movements ${Date.now()}`;
      await page.goto(`/intelligence/${eid}/workflow-source`);
      await page
        .getByLabel("Source table type")
        .selectOption("stock-movements");
      await page
        .getByLabel("Schedule title", { exact: true })
        .fill(sourceTitle);
      await page
        .getByLabel("Clean retained evidence")
        .selectOption(input.movement_evidence);
      await page.getByLabel("Expected data rows").fill("3");
      await page
        .getByLabel("Declare independent inventory quantity controls")
        .check();
      await page
        .getByLabel("Independent inventory partitions (JSON)")
        .fill(JSON.stringify(input.movement_controls, null, 2));
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-inventory-source-quantity-controls.png`,
        () =>
          page
            .getByRole("group", {
              name: "Inventory partition quantity controls",
            })
            .screenshot(),
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const option = page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(sourceTitle) });
      await expect(option).toHaveCount(1);
      const id = (await option.getAttribute("value"))!;
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(id, { timeout: 15000 });
      await reviewer
        .getByText(/^Inventory quantity controls .* 2 partitions$/)
        .click({ timeout: 15000 });
      const controls = reviewer.getByRole("table", {
        name: "Inventory quantity controls",
        exact: true,
      });
      await expect(controls.getByRole("row")).toHaveCount(3);
      await expect(
        controls.getByRole("cell", { name: "-1", exact: true }),
      ).toBeVisible();
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent original movement population, lot controls, signed quantities and line references reviewed",
        );
      const approval = reviewer.waitForResponse(
        (r) =>
          r.url().includes(`/events/${id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const response = await approval;
      expect(response.status(), await response.text()).toBe(201);
      const approved = await response.json();
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("inventory-count-bridge");
      await page
        .getByLabel("Use controlled counts before or after reporting")
        .check();
      const title = `SYNTHETIC ${country} controlled inventory bridge ${Date.now()}`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["Inventory reporting currency", input.currency],
        ["Inventory evidence review through", "2026-07-03"],
        [
          "Inventory day-end cutoff assessment",
          "Independent lot populations assessed at exclusive earlier day-end through inclusive later day-end; condition is not established by the quantity bridge",
        ],
        ["books source", input.source_ids.books],
        ["counts source", input.source_ids.counts],
        ["movements source", approved.id],
        [
          "Scope and source rationale",
          "Independent reporting-date books and original earlier/later lot counts with every signed movement retained",
        ],
      ])
        if (label.endsWith(" source"))
          await page.getByLabel(label, { exact: true }).selectOption(value);
        else await page.getByLabel(label, { exact: true }).fill(value);
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-inventory-bridge-scope.png`,
        () =>
          page
            .getByRole("group", {
              name: "Controlled inventory count-date bridge",
            })
            .screenshot(),
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const result = page
        .getByLabel("Saved source or result")
        .getByRole("option", { name: new RegExp(title) });
      await expect(result).toHaveCount(1);
      const resultId = (await result.getAttribute("value"))!;
      await page.getByLabel("Saved source or result").selectOption(resultId);
      const panel = page
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      await expect(
        panel.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await expect(
        panel.getByRole("cell", { name: "MATCHED", exact: true }),
      ).toHaveCount(2);
      await panel
        .getByText(/^Inventory count-date bridges .* 2 partitions$/)
        .click({ timeout: 15000 });
      const bridges = panel.getByRole("table", {
        name: "Inventory count-date bridges",
        exact: true,
      });
      await expect(bridges.getByRole("row")).toHaveCount(3);
      await expect(
        bridges.getByRole("row").filter({ hasText: "ROLL_BACK" }),
      ).toContainText("20");
      await expect(
        bridges.getByRole("row").filter({ hasText: "ROLL_FORWARD" }),
      ).toContainText("10");
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-inventory-count-date-bridges.png`,
        () => bridges.screenshot(),
      );
      const detail = await page.request.get(
        `/api/backend/intelligence/engagements/${eid}/events/${resultId}`,
        { headers: { "X-Tenant-ID": fixture.tenant } },
      );
      expect(detail.status()).toBe(200);
      const body = (await detail.json()).body;
      expect(body.count_bridges.map((row: { lot: string }) => row.lot)).toEqual(
        ["A", "B"],
      );
      expect(
        body.count_bridges.map(
          (row: { reporting_date_quantity: string }) =>
            row.reporting_date_quantity,
        ),
      ).toEqual(["10", "20"]);
      expect(
        body.rows.map((row: { currency: string }) => row.currency),
      ).toEqual([input.currency, input.currency]);
    }
  } finally {
    await context.close();
  }
});

test("India eight-field arrears retain month context and cannot replace regular monthly dues", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  const eid = fixture.india_engagement;
  const input = fixture.ecr_arrear_input;
  const title = `SYNTHETIC arrear ECR ${Date.now()}`;
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_table_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source file format")
      .selectOption("india-epfo-arrear-ecr-v2");
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(input.evidence_version_id);
    await page
      .getByLabel("EPFO establishment registration")
      .fill(input.employer_registration);
    await page.getByLabel("ECR wage month").fill("2026-06");
    await page.getByLabel("Independent ECR member count").fill("2");
    await page.getByLabel("Expected data rows").fill("6");
    await page.getByLabel("Independent totals by currency").fill("INR=360");
    await page
      .getByLabel("Retained arrear month/disbursement context")
      .selectOption(input.arrear_context_evidence_version_id);
    await page.getByLabel("Salary arrear disbursement date").fill("2026-07-10");
    await page
      .getByLabel("Independent arrear wage and contribution totals (INR, JSON)")
      .fill(JSON.stringify(input.ecr_arrear_controls, null, 2));
    await page
      .getByLabel("Arrear wage-month attribution assessment")
      .fill(input.arrear_scope_assessment);
    await saveScreenshot(`${shots}/india-ecr-arrear-source-controls.png`, () =>
      page
        .getByRole("group", {
          name: "Arrear ECR context and independent controls",
        })
        .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const option = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(title) });
    await expect(option).toHaveCount(1);
    const id = (await option.getAttribute("value"))!;
    await page.getByLabel("Saved source or result").selectOption(id);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByRole("cell", { name: "37", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "83", exact: true }),
    ).toBeVisible();
    await panel
      .getByText("Original source controls and calculation basis", {
        exact: true,
      })
      .click();
    const controls = panel.getByRole("table", {
      name: "Arrear ECR independent controls",
      exact: true,
    });
    await expect(controls.getByRole("row")).toHaveCount(7);
    await expect(
      controls.getByRole("row").filter({ hasText: "employer pf" }),
    ).toContainText("97");
    await saveScreenshot(
      `${shots}/india-ecr-arrear-component-controls.png`,
      () => controls.screenshot(),
    );
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent retained context, wage-month attribution, salary disbursement and separate employer EPF/pension fields assessed",
      );
    const approving = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approval = await approving;
    expect(approval.status(), await approval.text()).toBe(201);
    const approved = await approval.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("statutory-dues");
    await page
      .getByLabel("Compare arrears only, separately from regular monthly dues")
      .check();
    await page.getByLabel("Arrear comparison currency").fill("INR");
    const resultTitle = title + " comparison";
    await page.getByLabel("Schedule title", { exact: true }).fill(resultTitle);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-07-31");
    for (const [role, identifier] of Object.entries({
      ...fixture.ecr_arrear_sources,
      return: approved.id,
    }))
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(String(identifier));
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Only independently tagged arrear expectation, return and contribution payment populations; regular monthly activity remains separate",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const result = page
      .getByLabel("Saved source or result")
      .getByRole("option", { name: new RegExp(resultTitle) });
    await expect(result).toHaveCount(1);
    await page
      .getByLabel("Saved source or result")
      .selectOption((await result.getAttribute("value"))!);
    const comparison = page
      .getByRole("heading", { name: resultTitle, exact: true })
      .locator("..");
    await expect(
      comparison.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      comparison.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(6);
    await expect(comparison.getByRole("note")).toContainText("Arrears only");
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(`${shots}/india-ecr-arrear-only-comparison.png`, () =>
      comparison.screenshot(),
    );
    await page.goto(`/intelligence/${fixture.uae_engagement}/workflow-source`);
    await expect(
      page
        .getByLabel("Source file format")
        .locator('option[value="india-epfo-arrear-ecr-v2"]'),
    ).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test("reviewed bank residuals carry to the next window for UAE then India", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    for (const country of ["AE", "IN"] as const) {
      const input = fixture.bank_carryforward[country];
      const eid = input.engagement;
      const title = `SYNTHETIC ${country} carried bank residuals ${Date.now()}`;
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Saved source or result")
        .selectOption(input.parent);
      const summary = page.getByText(
        "Carry reviewed bank residuals into the next clearance window",
        { exact: true },
      );
      await summary.click();
      const controls = summary.locator("..");
      await controls.getByLabel("Carry-forward source title").fill(title);
      await controls.getByLabel("Independent residual row count").fill("1");
      await controls
        .getByLabel("Independent positive residual total")
        .fill("0");
      await controls
        .getByLabel("Independent negative residual total")
        .fill("-60");
      await controls
        .getByLabel("Carry-forward window and reversal assessment")
        .fill(
          "Independent retained statement-window completeness, continuing cheque validity and unresolved reversal context assessed",
        );
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-carryforward-controls.png`,
        () => controls.screenshot(),
      );
      const preparing = page.waitForResponse(
        (r) =>
          r
            .url()
            .includes(`/events/${input.parent}/bank-carryforward-source`) &&
          r.request().method() === "POST",
      );
      await controls
        .getByRole("button", {
          name: "Prepare carried bank residuals",
          exact: true,
        })
        .click();
      const response = await preparing;
      expect(response.status(), await response.text()).toBe(201);
      const source = await response.json();
      await expect(
        page.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      const sourcePanel = page
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      await expect(
        sourcePanel.getByRole("cell", { name: "2026-06-20", exact: true }),
      ).toBeVisible();
      await expect(
        sourcePanel.getByRole("cell", { name: "2026-07-31", exact: true }),
      ).toBeVisible();
      await expect(
        sourcePanel.getByRole("cell", { name: "-60", exact: true }),
      ).toBeVisible();
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-carried-original-date.png`,
        () => sourcePanel.screenshot(),
      );
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(source.id);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent complete residual count and signed direction controls checked; original item date and retained July clearance window preserved",
        );
      const approving = reviewer.waitForResponse(
        (r) =>
          r.url().includes(`/events/${source.id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approval = await approving;
      expect(approval.status(), await approval.text()).toBe(201);
      const approved = await approval.json();
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("bank-subsequent-clearance");
      const resultTitle = title + " August comparison";
      await page
        .getByLabel("Schedule title", { exact: true })
        .fill(resultTitle);
      await page
        .getByLabel("Reconciliation date", { exact: true })
        .fill("2026-07-31");
      await page
        .getByLabel("Review through date", { exact: true })
        .fill("2026-08-31");
      await page
        .getByLabel("Bank account identifier", { exact: true })
        .fill("BANK-1");
      await page
        .getByLabel("Account currency", { exact: true })
        .fill(country === "AE" ? "AED" : "INR");
      for (const [role, id] of Object.entries({
        outstanding: approved.id,
        statement: input.statement,
        allocations: input.allocations,
      }))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(id as string);
      await page
        .getByLabel("Scope and source rationale", { exact: true })
        .fill(
          "Independent August bank evidence clears only the carried remaining cheque amount; original item age remains June-based",
        );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const saved = page
        .getByLabel("Saved source or result")
        .locator("option")
        .filter({ hasText: resultTitle });
      await expect(saved).toHaveCount(1, { timeout: 120000 });
      await page
        .getByLabel("Saved source or result")
        .selectOption((await saved.getAttribute("value"))!);
      const resultPanel = page
        .getByRole("heading", { name: resultTitle, exact: true })
        .locator("..");
      await expect(
        resultPanel.getByText("0 exceptions", { exact: true }),
      ).toBeVisible();
      await expect(
        resultPanel.getByRole("cell", { name: "MATCHED", exact: true }),
      ).toHaveCount(2);
      for (const notice of await page
        .getByRole("button", { name: "Dismiss notification", exact: true })
        .all())
        await notice.click();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-carried-next-window.png`,
        () => resultPanel.screenshot(),
      );
    }
  } finally {
    await context.close();
  }
});

test("payroll accounts reconcile gross net deductions and employer contributions for UAE then India", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  for (const country of ["AE", "IN"] as const) {
    const input = fixture.payroll_ledger[country];
    const eid = input.engagement;
    const title = `SYNTHETIC ${country} payroll GL ${Date.now()}`;
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("payroll-ledger-rollforward");
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reporting period start", { exact: true })
      .fill("2026-06-01");
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Independent payroll gross/net/deduction/employer allocations and debit-positive expense / credit-positive liability basis assessed against opening and closing GL evidence",
      );
    for (const [role, id] of Object.entries(input.sources))
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(id as string);
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-payroll-ledger-accounting-window.png`,
      () =>
        page
          .getByLabel("Reporting period start", { exact: true })
          .locator("..")
          .locator("..")
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const saved = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: title });
    await expect(saved).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Saved source or result")
      .selectOption((await saved.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(5);
    await expect(
      panel.getByRole("row").filter({ hasText: "NET-PAY" }),
    ).toContainText("200");
    await expect(
      panel.getByRole("cell", { name: "1000", exact: true }),
    ).toHaveCount(4);
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-payroll-ledger-account-balances.png`,
      () => panel.locator("table").last().screenshot(),
    );
    await panel.getByLabel("Payroll accounting view").selectOption("postings");
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(6);
    await expect(
      panel.getByRole("cell", { name: "SALARY:GROSS", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "EMPLOYEE_DEDUCTION", exact: true }),
    ).toBeVisible();
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-payroll-ledger-direction-comparisons.png`,
      () => panel.locator("table").last().screenshot(),
    );
    await panel
      .locator("summary")
      .filter({ hasText: "Payroll posting source links" })
      .click();
    const links = panel.getByRole("table", {
      name: "Payroll posting source links",
      exact: true,
    });
    await expect(links.getByRole("row")).toHaveCount(13);
    await expect(
      links.getByRole("cell", { name: "GL-5", exact: true }),
    ).toBeVisible();
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-payroll-ledger-source-links.png`,
      () => links.screenshot(),
    );
  }
});

test("UAE VAT201 retains seven emirates and exposes offsetting geographic differences", async ({
  page,
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1500 },
  });
  const reviewer = await context.newPage();
  await page.setViewportSize({ width: 1600, height: 1500 });
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    const eid = fixture.uae_engagement;
    const title = `SYNTHETIC UAE emirate books ${Date.now()}`;
    await page.goto(`/intelligence/${eid}/workflow-source`);
    const summary = page.getByText("Compose reviewed VAT201 book schedules", {
      exact: true,
    });
    await summary.click();
    const compose = summary.locator("..");
    await compose
      .getByLabel("VAT201 composition layout")
      .selectOption("emirate-20");
    await compose.getByLabel("Composed VAT201 source title").fill(title);
    await compose
      .getByLabel("Reviewed VAT201 component schedules")
      .selectOption(fixture.emirate_vat.components);
    await compose
      .getByLabel("Independent composed taxable amount")
      .fill("2400");
    await compose.getByLabel("Independent composed tax total").fill("230");
    await compose.getByLabel("Independent composed adjustment total").fill("0");
    await compose
      .getByLabel("VAT201 composition scope assessment")
      .fill(
        "Independent geographic allocation support for all seven emirates and explicit zero rows; thirteen other disjoint boxes retained; no legal allocation inferred from an address",
      );
    await saveScreenshot(
      `${shots}/uae-vat201-emirate-composition-controls.png`,
      () => compose.screenshot(),
    );
    const preparing = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/vat201-composition-source`) &&
        r.request().method() === "POST",
    );
    await compose
      .getByRole("button", {
        name: "Prepare composed VAT201 books",
        exact: true,
      })
      .click();
    const response = await preparing;
    expect(response.status(), await response.text()).toBe(201);
    const source = await response.json();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent geographic support and zero-valued emirates reviewed alongside disjoint source controls; summary values do not determine legal allocation or e-commerce applicability",
      );
    const approving = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${source.id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const approval = await approving;
    expect(approval.status(), await approval.text()).toBe(201);
    const approved = await approval.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-vat-return");
    await page
      .getByLabel("VAT201 comparison layout")
      .selectOption("emirate-20");
    await expect(
      page.getByLabel("Required VAT201 boxes, comma separated"),
    ).toBeDisabled();
    await expect(
      page.getByLabel("Compare only the required VAT201 boxes"),
    ).toBeDisabled();
    const resultTitle = title + " geographic differences";
    await page.getByLabel("Schedule title", { exact: true }).fill(resultTitle);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(approved.id);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(fixture.emirate_vat.filed);
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "All twenty explicit rows compared by emirate against independent retained filed evidence; aggregate Box 1 agrees but two geographic allocations differ",
      );
    await saveScreenshot(
      `${shots}/uae-vat201-emirate-comparison-scope.png`,
      () =>
        page
          .getByLabel("VAT201 comparison layout")
          .locator("..")
          .locator("..")
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const saved = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: resultTitle });
    await expect(saved).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Saved source or result")
      .selectOption((await saved.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: resultTitle, exact: true })
      .locator("..");
    await expect(
      panel.getByText("2 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "VARIANCE", exact: true }),
    ).toHaveCount(2);
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(18);
    await expect(
      panel.getByRole("cell", { name: "Abu Dhabi", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "Dubai", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "Fujairah", exact: true }),
    ).toBeVisible();
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/uae-vat201-emirate-offsetting-differences.png`,
      () => panel.locator("table").last().screenshot(),
    );
    await page.goto(
      `/intelligence/${fixture.india_engagement}/workflow-source`,
    );
    await expect(
      page.getByText("Compose reviewed VAT201 book schedules", { exact: true }),
    ).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test("India purchase and sales invoices compare with registers without becoming filed returns", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-strong-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  const eid = fixture.india_engagement;
  for (const direction of ["purchase", "sale"] as const) {
    const input = fixture.invoice_register[direction];
    const opposite =
      fixture.invoice_register[direction === "purchase" ? "sale" : "purchase"];
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("india-invoice-register");
    await page
      .getByLabel("Invoice comparison direction")
      .selectOption(direction);
    await expect(
      page
        .getByLabel("books source", { exact: true })
        .locator(`option[value="${input.invoices}"]`),
    ).toHaveCount(0);
    await expect(
      page
        .getByLabel("invoices source", { exact: true })
        .locator(`option[value="${opposite.invoices}"]`),
    ).toHaveCount(0);
    const title = `SYNTHETIC ${direction} invoice register ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(input.books);
    await page
      .getByLabel("invoices source", { exact: true })
      .selectOption(input.invoices);
    await page
      .getByLabel("Scope and source rationale", { exact: true })
      .fill(
        "Independent register compared with original invoice facts for the explicit direction; neither file establishes GST return filing or IRP authenticity",
      );
    await saveScreenshot(
      `${shots}/india-${direction}-invoice-register-scope.png`,
      () =>
        page
          .getByLabel("Invoice comparison direction")
          .locator("..")
          .locator("..")
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const saved = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: title });
    await expect(saved).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Saved source or result")
      .selectOption((await saved.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(5);
    await expect(
      panel.getByRole("columnheader", { name: "invoices tax", exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("columnheader", { name: "return tax", exact: true }),
    ).toHaveCount(0);
    await expect(panel.getByRole("note")).toContainText(
      "does not establish GST return filing",
    );
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/india-${direction}-invoice-register-comparison.png`,
      () => panel.screenshot(),
    );
  }
  await page.getByLabel("Workflow", { exact: true }).selectOption("india-gst");
  for (const direction of ["purchase", "sale"] as const)
    await expect(
      page
        .getByLabel("return source", { exact: true })
        .locator(
          `option[value="${fixture.invoice_register[direction].invoices}"]`,
        ),
    ).toHaveCount(0);
  await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
  await expect(
    page
      .getByLabel("Workflow", { exact: true })
      .locator('option[value="india-invoice-register"]'),
  ).toHaveCount(0);
});

test("India GSTR-1 summary import preserves hierarchy and offsetting differences through review and export", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    const eid = fixture.india_engagement,
      input = fixture.gst_summary;
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source file format")
      .selectOption("india-gstr1-summary-json");
    const sourceTitle = `SYNTHETIC retained GSTR1 summary ${Date.now()}`;
    for (const [label, value] of [
      ["Schedule title", sourceTitle],
      ["Entity GSTIN", input.gstin],
      ["GSTR-1 summary month", "2026-06"],
      ["Expected data rows", String(input.expected_rows)],
      [
        "Independent GST summary metric controls (JSON)",
        JSON.stringify(input.controls, null, 2),
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(input.original);
    await expect(page.getByLabel("Independent totals by currency")).toHaveCount(
      0,
    );
    await saveScreenshot(
      `${shots}/india-gstr1-summary-import-controls.png`,
      () =>
        page
          .getByLabel("Independent GST summary metric controls (JSON)")
          .locator("..")
          .locator("..")
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const saved = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: sourceTitle });
    await expect(saved).toHaveCount(1, { timeout: 120000 });
    const unreviewed = (await saved.getAttribute("value"))!;
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer
      .getByLabel("Saved source or result")
      .selectOption(unreviewed);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independently assessed original hierarchy, explicit count/INR controls and retained summary scope; filing not established",
      );
    const approval = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${unreviewed}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const response = await approval;
    expect(response.status(), await response.text()).toBe(201);
    const approved = await response.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("india-gstr1-summary");
    await expect(
      page
        .getByLabel("books source", { exact: true })
        .locator(`option[value="${approved.id}"]`),
    ).toHaveCount(0);
    await expect(
      page
        .getByLabel("return source", { exact: true })
        .locator(`option[value="${unreviewed}"]`),
    ).toHaveCount(0);
    const title = `SYNTHETIC GSTR1 hierarchy comparison ${Date.now()}`;
    for (const [label, value] of [
      ["Schedule title", title],
      ["Reconciliation date", "2026-06-30"],
      [
        "Scope and source rationale",
        "Independent book schedule against original summary metrics; parent and counterparty totals cannot net",
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(input.books);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(approved.id);
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const result = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: title });
    await expect(result).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Saved source or result")
      .selectOption((await result.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("2 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "VARIANCE", exact: true }),
    ).toHaveCount(2);
    await expect(
      panel.getByRole("cell", { name: "COUNT", exact: true }).first(),
    ).toBeVisible();
    await expect(panel.getByRole("note")).toContainText(
      "matching does not establish filing",
    );
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await panel
      .getByRole("cell", { name: "B2B_4A", exact: true })
      .first()
      .scrollIntoViewIfNeeded();
    await saveScreenshot(
      `${shots}/india-gstr1-summary-hierarchy-comparison.png`,
      () => page.screenshot(),
    );
    await panel
      .getByRole("cell", { name: "ttl_nilsup_amt", exact: true })
      .scrollIntoViewIfNeeded();
    await saveScreenshot(
      `${shots}/india-gstr1-summary-document-counts.png`,
      () => page.screenshot(),
    );
    const download = page.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
    await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
    await expect(
      page
        .getByLabel("Workflow", { exact: true })
        .locator('option[value="india-gstr1-summary"]'),
    ).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test("India outward GSTR-1 documents retain request context and match reviewed sales without implying filing", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    const eid = fixture.india_engagement,
      input = fixture.gstr1_documents;
    await page.goto(`/intelligence/${eid}/workflow-source`);
    await page
      .getByLabel("Source file format")
      .selectOption("india-gstr1-documents-json");
    const sourceTitle = `SYNTHETIC outward GSTR1 source ${Date.now()}`;
    for (const [label, value] of [
      ["Schedule title", sourceTitle],
      ["Supplier GSTIN", input.gstin],
      ["GSTR-1 document reporting month", "2026-06"],
      ["Independent GSTR-1 document count", "1"],
      ["Expected data rows", "4"],
      ["Independent totals by currency", "INR=18"],
      [
        "Independent GSTR-1 section controls (JSON)",
        JSON.stringify(input.controls, null, 2),
      ],
      [
        "GSTR-1 retrieval scope assessment",
        "Independent request GSTIN, period, B2B-only retained population and filters/pagination assessed; no filing status inferred",
      ],
    ])
      await page.getByLabel(label).fill(value);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(input.original);
    await page
      .getByLabel("Retained GSTR-1 request context", { exact: true })
      .selectOption(input.context);
    await saveScreenshot(
      `${shots}/india-gstr1-outward-import-controls.png`,
      () =>
        page
          .getByRole("group", {
            name: "Outward invoice/note request scope and independent controls",
          })
          .screenshot(),
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const saved = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: sourceTitle });
    await expect(saved).toHaveCount(1, { timeout: 120000 });
    const unreviewed = (await saved.getAttribute("value"))!;
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer
      .getByLabel("Saved source or result")
      .selectOption(unreviewed);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent original response, separate request context and section head/base/count controls assessed; retained population only",
      );
    const approval = reviewer.waitForResponse(
      (r) =>
        r.url().includes(`/events/${unreviewed}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const response = await approval;
    expect(response.status(), await response.text()).toBe(201);
    const approved = await response.json();
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("india-gstr1-documents");
    await expect(
      page
        .getByLabel("books source", { exact: true })
        .locator(`option[value="${approved.id}"]`),
    ).toHaveCount(0);
    await page
      .getByLabel("books source", { exact: true })
      .selectOption(input.books);
    await page
      .getByLabel("return source", { exact: true })
      .selectOption(approved.id);
    const title = `SYNTHETIC outward GSTR1 reconciliation ${Date.now()}`;
    await page.getByLabel("Schedule title", { exact: true }).fill(title);
    await page
      .getByLabel("Reconciliation date", { exact: true })
      .fill("2026-06-30");
    await page
      .getByLabel("Scope and source rationale")
      .fill(
        "Independently reviewed original sales register and retained outward B2B section response; no full-return or filing claim",
      );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const result = page
      .getByLabel("Saved source or result")
      .locator("option")
      .filter({ hasText: title });
    await expect(result).toHaveCount(1, { timeout: 120000 });
    await page
      .getByLabel("Saved source or result")
      .selectOption((await result.getAttribute("value"))!);
    const panel = page
      .getByRole("heading", { name: title, exact: true })
      .locator("..");
    await expect(
      panel.getByText("0 exceptions", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("cell", { name: "MATCHED", exact: true }),
    ).toHaveCount(4);
    await expect(panel.getByRole("note")).toContainText(
      "matching does not establish filing",
    );
    for (const notice of await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .all())
      await notice.click();
    await saveScreenshot(
      `${shots}/india-gstr1-outward-sales-comparison.png`,
      () => panel.screenshot(),
    );
    await panel
      .getByText("Assessed outward source scope", { exact: true })
      .click();
    await expect(
      panel.getByText(/NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON/),
    ).toBeVisible();
    await saveScreenshot(
      `${shots}/india-gstr1-outward-retained-scope.png`,
      () =>
        panel
          .locator("details")
          .filter({
            has: page.getByText("Assessed outward source scope", {
              exact: true,
            }),
          })
          .screenshot(),
    );
    const download = page.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
    await page.goto(`/intelligence/${fixture.uae_engagement}/country-workflow`);
    await expect(
      page
        .getByLabel("Workflow", { exact: true })
        .locator('option[value="india-gstr1-documents"]'),
    ).toHaveCount(0);
  } finally {
    await context.close();
  }
});

for (const country of ["AE", "IN"] as const) {
  test(`${country} bank booking/value dates remain separate across paging and independent approval`, async ({
    page,
  }) => {
    const input = fixture.bank_dates[country];
    await page.goto("/login");
    await page
      .getByLabel("Email address")
      .fill(fixture.pdf_final_reviewer_email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("synthetic-password-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard");
    await page.goto(`/intelligence/${input.engagement}/country-workflow`);
    await page
      .getByLabel("Saved source or result")
      .selectOption(input.fallback);
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "101 bank rows use a value-date fallback" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Independent approval", exact: true }),
    ).toBeDisabled();
    const datePanel = page.locator("details").filter({
      has: page.locator("summary", {
        hasText: "Bank transaction dates · 202 entries",
      }),
    });
    await datePanel.locator("summary").click();
    await expect(
      datePanel.getByRole("table", { name: "Bank transaction dates" }),
    ).toBeVisible();
    await datePanel.getByRole("button", { name: "Next bank dates" }).click();
    await expect(
      datePanel.getByText("Rows 101-200 of 202", { exact: true }),
    ).toBeVisible();
    await datePanel.getByRole("button", { name: "Next bank dates" }).click();
    await expect(
      datePanel.getByText("Rows 201-202 of 202", { exact: true }),
    ).toBeVisible();
    await expect(datePanel.getByRole("row")).toHaveCount(3);
    await expect(
      datePanel.getByText("VALUE_DATE_FALLBACK", { exact: true }),
    ).toHaveCount(2);
    await expect(
      datePanel.getByRole("button", { name: "Next bank dates" }),
    ).toBeDisabled();
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-bank-date-fallback-page.png`,
      () => datePanel.screenshot(),
    );
    await page
      .getByLabel("Saved source or result")
      .selectOption(input.explicit);
    await page
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent synthetic bank booking dates, separate value dates and full population controls checked",
      );
    const approval = page.waitForResponse(
      (response) =>
        response.url().includes(`/events/${input.explicit}/review`) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const response = await approval;
    expect(response.status(), await response.text()).toBe(201);
    const approved = await response.json();
    expect(approved.body.review_status).toBe("REVIEWED");
    expect(approved.body.booking_date_review_count).toBe(0);
    await page.getByLabel("Saved source or result").selectOption(approved.id);
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "bank rows use a value-date fallback" }),
    ).toHaveCount(0);
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-bank-dates-approved.png`,
      () => page.screenshot(),
    );
  });
}

test("bank matched schedules show a clear empty caption for UAE and India", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.pdf_final_reviewer_email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  for (const country of ["AE", "IN"] as const) {
    const input = fixture.bank_dates[country];
    await page.goto(`/intelligence/${input.engagement}/country-workflow`);
    const select = page.getByLabel("Saved source or result");
    const option = select.locator("option").filter({
      hasText: `SYNTHETIC ${country} explicit bank dates · v2 · CURRENT`,
    });
    await expect(option).toHaveCount(1);
    await select.selectOption((await option.getAttribute("value")) as string);
    await expect(
      page.getByText(
        "No schedule rows on this page; XLSX contains the full result",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Disposition", exact: true }),
    ).toHaveCount(0);
    await saveScreenshot(
      `${shots}/${country.toLowerCase()}-bank-dates-approved.png`,
      () =>
        page
          .getByRole("heading", {
            name: `SYNTHETIC ${country} explicit bank dates`,
            exact: true,
          })
          .locator("..")
          .screenshot(),
    );
  }
});

for (const country of ["AE", "IN"] as const) {
  test(`${country} bank account identity evidence uses country format rules and independent review`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(180000);
    const input = fixture.bank_account_evidence[country],
      eid = input.engagement;
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:3010",
      viewport: { width: 1600, height: 1100 },
    });
    const reviewer = await context.newPage();
    try {
      for (const [actor, email, password] of [
        [page, "admin@example.com", "test-strong-password-123"],
        [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
      ] as const) {
        await actor.goto("/login");
        await actor.getByLabel("Email address").fill(email);
        await actor.getByLabel("Password", { exact: true }).fill(password);
        await actor
          .getByRole("button", { name: "Sign in", exact: true })
          .click();
        await actor.waitForURL("**/dashboard");
      }
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("bank-account-evidence");
      for (const [label, value] of [
        ["Schedule title", `SYNTHETIC ${country} bank identity ${Date.now()}`],
        ["Reconciliation date", "2026-06-30"],
        ["Bank account identifier", input.parameters.account],
        ["Account currency", input.parameters.currency],
        ["Engagement legal entity name", input.parameters.bank_owner_name],
        [
          "Owner identifier scheme",
          input.parameters.bank_owner_identifier_scheme,
        ],
        ["Owner identifier", input.parameters.bank_owner_identifier],
        [
          "Scope and source rationale",
          "Independent retained register, ledger and bank document observations with scoped owner identifiers",
        ],
      ] as const)
        await page.getByLabel(label, { exact: true }).fill(value);
      for (const role of ["register", "ledger", "bank"] as const)
        await page
          .getByLabel(role + " source", { exact: true })
          .selectOption(input.sources[role]);
      async function queue() {
        const submitted = page.waitForResponse(
          (response) =>
            response.url().includes(`/engagements/${eid}/jobs`) &&
            response.request().method() === "POST",
        );
        await page
          .getByRole("button", { name: "Queue calculation", exact: true })
          .click();
        const response = await submitted;
        expect(response.status(), await response.text()).toBe(202);
        const job = await response.json();
        let resultId = "";
        await expect
          .poll(
            async () => {
              const response = await page.request.get(
                `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
                { headers: { "X-Tenant-ID": fixture.tenant } },
              );
              expect(response.status()).toBe(200);
              const state = await response.json();
              if (state.status === "failed")
                throw new Error(JSON.stringify(state.error_details));
              resultId = state.result_id || "";
              return state.status;
            },
            { timeout: 45000 },
          )
          .toBe("completed");
        await expect(
          page
            .getByLabel("Saved source or result")
            .locator(`option[value="${resultId}"]`),
        ).toHaveCount(1);
        await page.getByLabel("Saved source or result").selectOption(resultId);
        return resultId;
      }
      const resultId = await queue();
      const comparison = page.getByRole("region", {
        name: "Bank account evidence comparison",
        exact: true,
      });
      await expect(
        comparison.getByRole("table", {
          name: "Bank account identity observations",
        }),
      ).toBeVisible();
      await expect(comparison.getByText("00123", { exact: true })).toHaveCount(
        3,
      );
      if (country === "IN")
        await expect(
          comparison.getByText("000123456789", { exact: true }),
        ).toHaveCount(3);
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-account-evidence.png`,
        () => comparison.screenshot(),
      );
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(resultId);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent synthetic bank identity evidence and owner scope checked; no bank authentication asserted",
        );
      const approval = reviewer.waitForResponse(
        (response) =>
          response.url().includes(`/events/${resultId}/review`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approved = await approval;
      expect(approved.status(), await approved.text()).toBe(201);
      const item = await approved.json();
      expect(item.body.review_status).toBe("REVIEWED");
      expect(item.body.bank_authentication_status).toBe(
        "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
      );
      const download = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
      await page
        .getByLabel("bank source", { exact: true })
        .selectOption(input.mismatched_bank);
      await page
        .getByLabel("Schedule title", { exact: true })
        .fill(`SYNTHETIC ${country} unmatched bank owner ${Date.now()}`);
      await queue();
      await expect(
        page.getByRole("button", { name: "Independent approval", exact: true }),
      ).toBeDisabled();
      await expect(
        comparison.getByText("owner identifier unresolved", { exact: true }),
      ).toBeVisible();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-owner-mismatch.png`,
        () => comparison.screenshot(),
      );
    } finally {
      await context.close();
    }
  });
}

for (const country of ["AE", "IN"] as const) {
  test(`${country} reviewed account evidence links native bank numbers to ledger scope and becomes stale on revocation`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(180000);
    const input = fixture.bank_account_binding[country],
      eid = input.engagement;
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:3010",
      viewport: { width: 1600, height: 1100 },
    });
    const reviewer = await context.newPage();
    try {
      for (const [actor, email, password] of [
        [page, "admin@example.com", "test-strong-password-123"],
        [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
      ] as const) {
        await actor.goto("/login");
        await actor.getByLabel("Email address").fill(email);
        await actor.getByLabel("Password", { exact: true }).fill(password);
        await actor
          .getByRole("button", { name: "Sign in", exact: true })
          .click();
        await actor.waitForURL("**/dashboard");
      }
      await page.goto(`/intelligence/${eid}/country-workflow`);
      const title = `SYNTHETIC ${country} reviewed account alias ${Date.now()}`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["Bank account identifier", input.account],
        ["Account currency", input.currency],
        ["book opening", "0"],
        ["book closing", "95"],
        ["statement opening", "0"],
        ["statement closing", "95"],
        [
          "Scope and source rationale",
          "Independent synthetic signed ledger and native bank controls",
        ],
        [
          "Linked account scope assessment",
          "Reviewed ledger code to original bank account and full June validity window",
        ],
      ] as const) {
        if (label === "Linked account scope assessment")
          await page
            .getByLabel("Reviewed bank account evidence (optional)")
            .selectOption(input.review);
        await page.getByLabel(label, { exact: true }).fill(value);
      }
      for (const role of ["books", "statement"] as const)
        await page
          .getByLabel(role + " source", { exact: true })
          .selectOption(input.sources[role]);
      const submitted = page.waitForResponse(
        (response) =>
          response.url().includes(`/engagements/${eid}/jobs`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const response = await submitted;
      expect(response.status(), await response.text()).toBe(202);
      const job = await response.json();
      let resultId = "";
      await expect
        .poll(
          async () => {
            const response = await page.request.get(
              `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
              { headers: { "X-Tenant-ID": fixture.tenant } },
            );
            expect(response.status()).toBe(200);
            const state = await response.json();
            if (state.status === "failed")
              throw new Error(JSON.stringify(state.error_details));
            resultId = state.result_id || "";
            return state.status;
          },
          { timeout: 45000 },
        )
        .toBe("completed");
      await expect(
        page
          .getByLabel("Saved source or result")
          .locator(`option[value="${resultId}"]`),
      ).toHaveCount(1);
      await page.getByLabel("Saved source or result").selectOption(resultId);
      const link = page.getByRole("region", {
        name: "Linked bank account evidence",
        exact: true,
      });
      await expect(
        link.getByText(input.original_account, { exact: true }),
      ).toBeVisible();
      await expect(
        link.getByText("Applied using the reviewed account number", {
          exact: true,
        }),
      ).toBeVisible();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-account-linked-scope.png`,
        () => link.screenshot(),
      );
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(resultId);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Independent synthetic account mapping, receipt, source controls and full window checked; no bank authentication asserted",
        );
      const approved = reviewer.waitForResponse(
        (response) =>
          response.url().includes(`/events/${resultId}/review`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approval = await approved;
      expect(approval.status(), await approval.text()).toBe(201);
      const item = await approval.json();
      expect(item.body.bank_account_evidence.review_receipt.id).toBe(
        input.review,
      );
      const download = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
      await link
        .getByRole("button", {
          name: "Open linked account review",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("region", {
          name: "Bank account evidence comparison",
          exact: true,
        }),
      ).toBeVisible();
      await reviewer.goto(`/intelligence/${eid}/workflow-source`);
      await reviewer
        .getByLabel("Saved source or result")
        .selectOption(input.account_bank_source);
      await reviewer
        .getByLabel("Review / exception rationale")
        .fill(
          "Synthetic source assertion withdrawn to verify recursive account-link freshness",
        );
      const rejected = reviewer.waitForResponse(
        (response) =>
          response
            .url()
            .includes(`/events/${input.account_bank_source}/review`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Reject", exact: true })
        .click();
      const rejection = await rejected;
      expect(rejection.status(), await rejection.text()).toBe(201);
      await reviewer.goto(`/intelligence/${eid}/country-workflow`);
      await reviewer.getByLabel("Saved source or result").selectOption(item.id);
      const panel = reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..");
      await expect(panel.getByText("STALE", { exact: true })).toBeVisible();
      await expect(
        panel.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await saveScreenshot(
        `${shots}/${country.toLowerCase()}-bank-account-linked-stale.png`,
        () => panel.screenshot(),
      );
    } finally {
      await context.close();
    }
  });
}
test("UAE evidenced nil imports produce reviewed zero VAT201 boxes", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3010",
  });
  const reviewer = await context.newPage();
  try {
    for (const [actor, email, password] of [
      [page, "admin@example.com", "test-strong-password-123"],
      [reviewer, fixture.pdf_final_reviewer_email, "synthetic-password-123"],
    ] as const) {
      await actor.goto("/login");
      await actor.getByLabel("Email address").fill(email);
      await actor.getByLabel("Password", { exact: true }).fill(password);
      await actor.getByRole("button", { name: "Sign in", exact: true }).click();
      await actor.waitForURL("**/dashboard");
    }
    const eid = fixture.uae_engagement;
    await page.goto(`/intelligence/${eid}/country-workflow`);
    await page
      .getByLabel("Workflow", { exact: true })
      .selectOption("uae-import-vat");
    for (const [label, value] of [
      ["Schedule title", `SYNTHETIC nil imports ${Date.now()}`],
      ["Reconciliation date", "2026-06-30"],
      [
        "Scope and source rationale",
        "Three independently reviewed empty sources and separate retained nil assessment",
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    for (const role of ["customs", "portal", "books"])
      await page
        .getByLabel(`${role} source`, { exact: true })
        .selectOption(fixture.import_nil.sources[role]);
    await page.getByLabel("Declare an evidenced nil import population").check();
    for (const [label, value] of [
      ["Nil import TRN", "100000000000001"],
      ["Nil import period start", "2026-04-01"],
      ["Nil import period end", "2026-06-30"],
      [
        "Nil import assessment",
        "Separate retained synthetic assessment establishes nil declarations and nil adjustments for this TRN and period",
      ],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
    await page.getByLabel("Box 6 declarations are nil").check();
    await page.getByLabel("Box 7 adjustments are nil").check();
    await page
      .getByLabel("Nil import supporting evidence")
      .selectOption(fixture.import_nil.context);
    await saveScreenshot(`${shots}/uae-import-nil-scope-form.png`, () =>
      page
        .getByRole("group", {
          name: "Explicit nil import populations",
          exact: true,
        })
        .screenshot(),
    );
    const submitted = page.waitForResponse(
      (r) =>
        r.url().includes(`/engagements/${eid}/jobs`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await submitted;
    expect(response.status(), await response.text()).toBe(202);
    const job = await response.json();
    let result = "";
    await expect
      .poll(
        async () => {
          const response = await page.request.get(
            `/api/backend/intelligence/engagements/${eid}/jobs/${job.id}`,
            { headers: { "X-Tenant-ID": fixture.tenant } },
          );
          const body = await response.json();
          if (body.status === "failed")
            throw new Error(JSON.stringify(body.error_details));
          result = body.result_id || "";
          return body.status;
        },
        { timeout: 45000 },
      )
      .toBe("completed");
    await expect(
      page
        .getByLabel("Saved source or result")
        .locator(`option[value="${result}"]`),
    ).toHaveCount(1);
    await page.getByLabel("Saved source or result").selectOption(result);
    await expect(
      page.getByRole("region", {
        name: "Evidenced nil import scope",
        exact: true,
      }),
    ).toContainText("VERIFIED_RETAINED_CONTEXT");
    const totals = page.getByRole("table", {
      name: "Import VAT selected population totals",
    });
    await expect(
      totals.getByRole("cell", { name: "Explicit evidenced nil", exact: true }),
    ).toHaveCount(6);
    await saveScreenshot(`${shots}/uae-import-nil-selected-totals.png`, () =>
      totals.locator("..").screenshot(),
    );
    await reviewer.goto(`/intelligence/${eid}/country-workflow`);
    await reviewer.getByLabel("Saved source or result").selectOption(result);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent scope, clean retained context and three reviewed nil sources checked",
      );
    const reviewedResponse = reviewer.waitForResponse(
      (r) =>
        r.url().endsWith(`/events/${result}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const reviewed = await reviewedResponse;
    expect(reviewed.status(), await reviewed.text()).toBe(201);
    const parent = await reviewed.json();
    await page.reload();
    await page.getByLabel("Saved source or result").selectOption(parent.id);
    await page
      .getByText("Prepare selected import boxes for VAT201 comparison", {
        exact: true,
      })
      .click();
    await page
      .getByLabel("Import box source title", { exact: true })
      .fill("SYNTHETIC evidenced nil import VAT201 books");
    await page.getByLabel("Assessed import source role").selectOption("books");
    for (const box of ["6", "7"])
      for (const suffix of [
        "expected detail rows",
        "taxable amount (AED)",
        "tax (AED)",
      ])
        await page
          .getByLabel(`Box ${box} ${suffix}`, { exact: true })
          .fill("0");
    await page
      .getByLabel("Import box scope assessment")
      .fill(
        "Independent zero counts, taxable bases and tax controls assessed for both nil populations",
      );
    const createdResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/events/${parent.id}/import-vat-box-source`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Prepare import box source", exact: true })
      .click();
    const created = await createdResponse;
    expect(created.status(), await created.text()).toBe(201);
    const source = await created.json();
    expect(source.body.review_status).toBe("UNVERIFIED");
    expect(source.body.rows).toHaveLength(2);
    expect(
      source.body.rows.every(
        (row: { tax: string; population_basis: string }) =>
          row.tax === "0" && row.population_basis === "EXPLICIT_EVIDENCED_NIL",
      ),
    ).toBe(true);
    await reviewer.goto(`/intelligence/${eid}/workflow-source`);
    await reviewer.getByLabel("Saved source or result").selectOption(source.id);
    await reviewer
      .getByLabel("Review / exception rationale")
      .fill(
        "Independent zero controls and explicit nil scope provenance checked",
      );
    const approvedResponse = reviewer.waitForResponse(
      (r) =>
        r.url().endsWith(`/events/${source.id}/review`) &&
        r.request().method() === "POST",
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    expect((await approvedResponse).status()).toBe(201);
    const download = reviewer.waitForEvent("download");
    await reviewer
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
  } finally {
    await context.close();
  }
});

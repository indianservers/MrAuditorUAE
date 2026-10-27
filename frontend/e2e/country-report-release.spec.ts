import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";

const identities = JSON.parse(
  readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
);
const screenshots = "test-results/country-reports";

async function login(page: Page, email: string) {
  const password = process.env.AUDITOS_SMOKE_PASSWORD;
  if (!password)
    throw new Error("Explicit isolated smoke credentials required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

async function post(
  request: APIRequestContext,
  path: string,
  data: unknown,
  status = 201,
) {
  const response = await request.post(`/api/backend/${path}`, {
    headers: {
      "X-Tenant-ID": identities.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    },
    data,
  });
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

async function country(page: Page, code: string) {
  await page.goto("/settings/countries");
  await page.getByLabel("Working country", { exact: true }).selectOption(code);
  await expect(page.getByLabel("Working country", { exact: true })).toHaveValue(
    code,
  );
}

for (const code of ["AE", "IN"] as const) {
  test(`synthetic ${code} report coverage, separate reviewer and generated draft`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(150000);
    expect(identities.synthetic_only).toBe(true);
    mkdirSync(screenshots, { recursive: true });
    const preparerEmail = process.env.AUDITOS_SMOKE_EMAIL;
    const reviewerEmail = process.env.AUDITOS_SMOKE_REVIEWER_EMAIL;
    if (!preparerEmail || !reviewerEmail)
      throw new Error("Two explicit isolated identities required");
    await login(page, preparerEmail);
    page.setDefaultTimeout(20000);
    const reviewerContext = await browser.newContext({
      baseURL: process.env.AUDITOS_E2E_ORIGIN,
      viewport: { width: 1440, height: 1000 },
    });
    const reviewer = await reviewerContext.newPage();
    reviewer.setDefaultTimeout(20000);
    await login(reviewer, reviewerEmail);
    const client = await post(page.request, "clients", {
      code: `REPORT-${code}-${Date.now()}`,
      name: `SYNTHETIC ${code} report client`,
    });
    const entity = await post(page.request, "entities", {
      client_id: client.id,
      name: `SYNTHETIC ${code} reporting entity`,
      country: code,
      jurisdiction: code === "AE" ? "United Arab Emirates" : "India",
      functional_currency: code === "AE" ? "AED" : "INR",
      presentation_currency: code === "AE" ? "AED" : "INR",
    });
    const end = code === "AE" ? "2026-12-31" : "2027-03-31";
    const period = await post(page.request, "financial-periods", {
      entity_id: entity.id,
      start_date: code === "AE" ? "2026-01-01" : "2026-04-01",
      end_date: end,
    });
    const engagement = await post(page.request, "engagements", {
      entity_id: entity.id,
      period_id: period.id,
      name: `SYNTHETIC ${code} report smoke`,
      engagement_type: "External Audit",
    });
    await post(
      page.request,
      `engagements/${engagement.id}/audit/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    const context = await post(
      page.request,
      `jurisdictions/engagements/${engagement.id}/context`,
      {
        country: code,
        framework: code === "AE" ? "IFRS" : "Ind AS",
        entity_type: "company",
        as_of: end,
        base_version: 0,
        reason: "SYNTHETIC independent reporting-context assessment",
      },
    );
    await post(
      reviewer.request,
      `jurisdictions/engagements/${engagement.id}/context/decision`,
      {
        request_id: context.id,
        approve: true,
        comments:
          "SYNTHETIC independent context decision; not client qualification",
      },
    );
    await country(page, code);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/reports/statutory");
    const access = await page.request.get("/api/backend/workspace/access", {
      headers: { "X-Tenant-ID": identities.tenant_id },
    });
    expect(access.status()).toBe(200);
    expect((await access.json()).permissions).toContain("audit.read");
    try {
      await expect(
        page.getByRole("heading", {
          name: "Statutory Report Designer",
          exact: true,
        }),
        errors.join("\n"),
      ).toBeVisible({ timeout: 20000 });
    } finally {
      await page.screenshot({
        path: `${screenshots}/${code}-designer-route.png`,
        fullPage: true,
      });
    }

    await page
      .getByRole("combobox", { name: "Engagement", exact: true })
      .selectOption(engagement.id);
    await page
      .getByLabel("Report title", { exact: true })
      .fill(`SYNTHETIC ${code} declared report`);
    await page
      .getByRole("combobox", { name: "Report category", exact: true })
      .selectOption(code === "AE" ? "uae-ifrs" : "india-statutory");
    await page
      .getByLabel("Template / review rationale")
      .fill(
        "SYNTHETIC authored communication scope; not complete statutory content",
      );
    await page
      .getByLabel("Block title", { exact: true })
      .fill(`SYNTHETIC ${code} narrative`);
    await page
      .getByLabel("User-authored narrative / commentary")
      .fill(
        "SYNTHETIC communication only. No statutory opinion, legal completeness or filing is established.",
      );
    await page
      .getByRole("button", { name: "Add content block", exact: true })
      .click();
    let saved = page.waitForResponse(
      (r) =>
        r.url().endsWith("/report-templates") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Save template version", exact: true })
      .click();
    expect((await saved).status()).toBe(201);
    await expect(
      page.getByRole("button", {
        name: "Record independent template approval",
      }),
    ).toBeDisabled();
    await page
      .getByRole("heading", { name: "Review and controlled generation" })
      .locator("..")
      .screenshot({ path: `${screenshots}/${code}-coverage-gap.png` });
    await page
      .getByRole("button", { name: "Load retained blocks into new revision" })
      .click();
    await page
      .getByRole("button", { name: "Add declared requirement" })
      .click();
    await page
      .getByLabel("Requirement reference 1", { exact: true })
      .fill(`${code}-narrative`);
    await page
      .getByLabel("Requirement title 1", { exact: true })
      .fill(`SYNTHETIC ${code} communication`);
    await page
      .getByRole("combobox", { name: "Requirement disposition 1", exact: true })
      .selectOption("REQUIRED");
    await page
      .getByLabel("Evidence/calculation source required for item 1", {
        exact: true,
      })
      .uncheck();
    await page
      .getByLabel("Applicability and source basis 1", { exact: true })
      .fill(
        "SYNTHETIC authored communication explicitly assessed without a required evidence source",
      );
    await page
      .getByRole("group", {
        name: `Coverage for SYNTHETIC ${code} narrative`,
        exact: true,
      })
      .getByLabel(`SYNTHETIC ${code} communication`, { exact: true })
      .check();
    await page
      .getByLabel("Requirement scope completeness assessment")
      .selectOption("assessed");
    await page
      .getByLabel("Requirement scope basis", { exact: true })
      .fill(
        "SYNTHETIC declared communication scope only; not complete statutory requirements",
      );
    saved = page.waitForResponse(
      (r) =>
        r.url().endsWith("/report-templates") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Save template version", exact: true })
      .click();
    const prepared = await saved;
    expect(prepared.status()).toBe(201);
    const template = await prepared.json();
    await expect(
      page.getByRole("button", {
        name: "Record independent template approval",
      }),
    ).toBeEnabled();
    const refused = page.waitForResponse((r) =>
      r.url().endsWith(`/events/${template.id}/review`),
    );
    await page
      .getByRole("button", { name: "Record independent template approval" })
      .click();
    expect((await refused).status()).toBe(403);
    await country(reviewer, code);
    await reviewer.goto("/reports/statutory");
    await reviewer
      .getByRole("combobox", { name: "Engagement", exact: true })
      .selectOption(engagement.id);
    await reviewer
      .getByRole("combobox", { name: "Saved template version", exact: true })
      .selectOption(template.id);
    const coverage = reviewer.getByRole("region", {
      name: "Retained requirement coverage",
      exact: true,
    });
    await expect(
      coverage.getByRole("cell", { name: "COVERED", exact: true }),
    ).toBeVisible();
    await coverage.locator("summary").click();
    await expect(coverage.getByText(/No statutory opinion/)).toBeVisible();
    await coverage.screenshot({
      path: `${screenshots}/${code}-reviewed-coverage.png`,
    });
    await reviewer
      .getByLabel("Template / review rationale")
      .fill("SYNTHETIC independent scope and authored content review");
    const approved = reviewer.waitForResponse((r) =>
      r.url().endsWith(`/events/${template.id}/review`),
    );
    await reviewer
      .getByRole("button", { name: "Record independent template approval" })
      .click();
    const approval = await approved;
    expect(approval.status()).toBe(201);
    const reviewed = await approval.json();
    await page.reload();
    await page
      .getByRole("combobox", { name: "Engagement", exact: true })
      .selectOption(engagement.id);
    await page
      .getByRole("combobox", { name: "Saved template version", exact: true })
      .selectOption(reviewed.id);
    await page
      .getByLabel("Template / review rationale")
      .fill(
        "SYNTHETIC draft generation from independently reviewed declared scope",
      );
    const generated = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/engagements/${engagement.id}/reports`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate from current reviewed sources" })
      .click();
    const generation = await generated;
    expect(generation.status()).toBe(201);
    const report = await generation.json();
    expect(report.body.document_status).toBe("DRAFT — NOT SIGNED OR FILED");
    expect(
      report.body.requirements_coverage.statutory_completeness_qualified,
    ).toBe(false);
    await expect(
      page.getByRole("link", {
        name: "Review generated report and export DOCX / XLSX / PDF",
      }),
    ).toHaveAttribute("href", new RegExp(report.id));
    const download = await page.request.get(
      `/api/backend/intelligence/engagements/${engagement.id}/events/${report.id}/export?format=xlsx`,
      { headers: { "X-Tenant-ID": identities.tenant_id } },
    );
    expect(download.status()).toBe(200);
    expect((await download.body()).subarray(0, 2).toString()).toBe("PK");
    await reviewerContext.close();
  });
}

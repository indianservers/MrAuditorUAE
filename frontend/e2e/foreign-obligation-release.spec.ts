import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

const screenshots = "test-results/country-reports";
type Paper = {
  id: string;
  version: number;
  status: string;
  body: Record<string, unknown>;
};
async function login(page: Page, email: string) {
  const password = process.env.AUDITOS_SMOKE_PASSWORD;
  if (!password || !email)
    throw new Error("Explicit isolated synthetic identities required");
  await page.goto("/login");
  await page
    .getByRole("textbox", { name: "Email address", exact: true })
    .fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/settings/countries");
  await page
    .getByRole("combobox", { name: "Working country", exact: true })
    .selectOption("AE");
}

test("synthetic UAE entity Indian obligation UI scope revision, independent filing approval and stale history", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  expect(identities.preparer_user_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(identities.reviewer_user_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(identities.reviewer_user_id).not.toBe(identities.preparer_user_id);
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 2200, height: 2600 },
  });
  const reviewer = await context.newPage();
  page.setDefaultTimeout(20000);
  reviewer.setDefaultTimeout(20000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  reviewer.on("pageerror", (error) => errors.push(error.message));
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    await login(reviewer, process.env.AUDITOS_SMOKE_REVIEWER_EMAIL!);
    const headers = {
      "X-Tenant-ID": identities.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    };
    async function get(request: APIRequestContext, path: string) {
      const response = await request.get(`/api/backend/${path}`, { headers });
      expect(response.status(), await response.text()).toBe(200);
      return response.json();
    }
    async function post(
      request: APIRequestContext,
      path: string,
      data: unknown,
      status = 201,
    ) {
      const response = await request.post(`/api/backend/${path}`, {
        headers,
        data,
      });
      expect(response.status(), await response.text()).toBe(status);
      return response.json();
    }
    const client = await post(page.request, "clients", {
      code: `FOREIGN-${Date.now()}`,
      name: "SYNTHETIC foreign-obligation client",
    });
    const entity = await post(page.request, "entities", {
      client_id: client.id,
      name: "SYNTHETIC UAE foreign-obligation entity",
      country: "AE",
      jurisdiction: "UAE",
      functional_currency: "AED",
      presentation_currency: "AED",
    });
    const period = await post(page.request, "financial-periods", {
      entity_id: entity.id,
      start_date: "2026-01-01",
      end_date: "2026-12-31",
    });
    const engagement = await post(page.request, "engagements", {
      entity_id: entity.id,
      period_id: period.id,
      name: "SYNTHETIC UAE with assessed Indian obligation",
      engagement_type: "External Audit",
    });
    const eid = engagement.id;
    const audit = `engagements/${eid}/audit`;
    const base = `grc/engagements/${eid}`;
    await post(
      page.request,
      `${audit}/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    async function action(
      request: APIRequestContext,
      prefix: string,
      paper: Paper,
      value: string,
    ): Promise<Paper> {
      return post(
        request,
        `${prefix}/records/${paper.id}/actions`,
        {
          version: paper.version,
          action: value,
          comments:
            "SYNTHETIC independent retained-evidence decision; no legal/client qualification",
        },
        200,
      );
    }
    const { evidence } = makeWorkflowHarness(page, eid, identities.tenant_id);
    const originals: Record<string, Paper> = {};
    for (const role of ["rule", "facts", "readiness"]) {
      const file = await evidence(
        `SYNTHETIC-foreign-${role}.txt`,
        Buffer.from(
          `SYNTHETIC ${role}; fictional seven-day rule; no external filing or legal qualification`,
        ),
      );
      let paper: Paper = await get(
        page.request,
        `${audit}/records/${file.record}`,
      );
      paper = await action(page.request, audit, paper, "submit");
      originals[role] = await action(reviewer.request, audit, paper, "approve");
    }
    const reference = "SYN-FOREIGN-IN-PERIOD";
    let paper: Paper = await post(page.request, `${base}/records/obligation`, {
      reference,
      title: "SYNTHETIC Indian obligation of a UAE entity",
      body: {
        owner_id: identities.preparer_user_id,
        entity_id: entity.id,
        module: "vat",
        source_url: "https://synthetic.invalid/fictional-period-rule",
        jurisdiction: "IN",
        effective_from: "2025-04-01",
        required_evidence:
          "SYNTHETIC independent rule, entity facts and readiness records",
        compliance_assessment: "pending",
        jurisdiction_scope: {
          entity_country: "AE",
          obligation_country: "IN",
          relationship: "foreign",
          applicability: "potential",
          registration_reference: "SYN-REG-001",
          assessment:
            "SYNTHETIC assessed foreign scope; not legal registration qualification",
        },
        obligation_period_start: "2025-04-01",
        obligation_period_end: "2026-03-31",
        rule_evidence_id: originals.rule.id,
        fact_evidence_ids: [originals.facts.id],
        entity_facts: { registration: "SYNTHETIC assessed registration" },
        readiness_evidence_ids: [originals.readiness.id],
        reviewer_id: identities.reviewer_user_id,
        deadline_kind: "firm_internal",
        deadline_rule: {
          identifier: "SYNTHETIC-seven-day-rule",
          version: 1,
          effective_from: "2025-01-01",
          effective_to: "2026-12-31",
          trigger: "2026-03-31",
          date_basis: "period_end",
          days_after: 7,
          timezone: "Asia/Kolkata",
        },
      },
    });
    expect(paper.body.deadline).toBe("2026-04-07");
    async function open(actor: Page) {
      await actor.goto(`/grc/${eid}/obligations`);
      await actor
        .getByRole("gridcell", { name: reference, exact: true })
        .click();
      const panel = actor.getByRole("region", {
        name: "Filing readiness",
        exact: true,
      });
      await expect(
        panel.getByText(/Declared entity country: AE/),
      ).toContainText("Obligation country: IN");
      await expect(
        panel.getByText(/Obligation period: 2025-04-01 to 2026-03-31/),
      ).toBeVisible();
      return panel;
    }
    async function uiStage(actor: Page, value: string): Promise<Paper> {
      const panel = actor.getByRole("region", {
        name: "Filing readiness",
        exact: true,
      });
      await panel
        .getByRole("combobox", { name: "Next filing stage", exact: true })
        .selectOption(value);
      const response = actor.waitForResponse(
        (r) =>
          r.url().endsWith(`/obligations/${paper.id}/filing-stage`) &&
          r.request().method() === "POST",
      );
      await expect(
        panel.getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        }),
      ).toBeEnabled();
      await panel
        .getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        })
        .click();
      const result = await response;
      expect(result.status(), await result.text()).toBe(200);
      const saved: Paper = await result.json();
      expect(saved.body.filing_stage).toBe(value);
      await expect(panel).toContainText(`version ${saved.version}`);
      return saved;
    }
    let panel = await open(page);
    paper = await uiStage(page, "preparing");
    paper = await uiStage(page, "under_review");
    await expect(
      panel.getByRole("button", {
        name: "Record evidenced filing stage",
        exact: true,
      }),
    ).toBeDisabled();
    await expect(panel.getByText(/Assess country applicability/)).toBeVisible();
    await page.setViewportSize({ width: 2200, height: 2600 });
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `${screenshots}/AE-IN-foreign-obligation-pending.png`,
    });
    await page.getByRole("button", { name: "Edit draft", exact: true }).click();
    const editor = page.locator("form.grc-editor");
    await expect(
      editor.getByLabel("Obligation period start", { exact: true }),
    ).toHaveValue("2025-04-01");
    await expect(
      editor.getByLabel("Obligation period end", { exact: true }),
    ).toHaveValue("2026-03-31");
    await editor
      .getByRole("group", { name: "Jurisdiction scope", exact: true })
      .getByRole("combobox", { name: "Applicability", exact: true })
      .selectOption("assessed_applicable");
    const updated = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/records/${paper.id}`) &&
        r.request().method() === "PATCH",
    );
    await editor
      .getByRole("button", { name: "Save draft", exact: true })
      .click();
    const update = await updated;
    expect(update.status(), await update.text()).toBe(200);
    paper = await update.json();
    expect(
      (paper.body.jurisdiction_scope as Record<string, unknown>).applicability,
    ).toBe("assessed_applicable");
    expect(paper.body.obligation_period_end).toBe("2026-03-31");
    const detail = page.locator("aside.grc-detail");
    await expect(detail.locator(".grc-status")).toContainText(
      `v${paper.version}`,
    );
    await detail
      .getByLabel("Review rationale", { exact: true })
      .fill(
        "SYNTHETIC explicitly assessed scope and retained foreign period; no professional legal qualification",
      );
    const submitted = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/records/${paper.id}/actions`) &&
        r.request().method() === "POST",
    );
    await detail
      .getByRole("button", { name: "Submit for review", exact: true })
      .click();
    const submit = await submitted;
    expect(submit.status(), await submit.text()).toBe(200);
    paper = await submit.json();
    expect(paper.status).toBe("REVIEW_REQUIRED");
    const ownReview = await page.request.post(
      `/api/backend/${base}/records/${paper.id}/actions`,
      {
        headers,
        data: {
          version: paper.version,
          action: "approve",
          comments: "SYNTHETIC self-review must fail",
        },
      },
    );
    expect(ownReview.status()).toBe(403);
    panel = await open(reviewer);
    const reviewDetail = reviewer.locator("aside.grc-detail");
    await reviewDetail
      .getByLabel("Review rationale", { exact: true })
      .fill(
        "SYNTHETIC independent source and scope assessment; no real-client or legal qualification",
      );
    await expect(
      reviewDetail.getByRole("button", {
        name: "Approve independently",
        exact: true,
      }),
    ).toBeEnabled();
    const approved = reviewer.waitForResponse(
      (r) =>
        r.url().endsWith(`/records/${paper.id}/actions`) &&
        r.request().method() === "POST",
    );
    await reviewDetail
      .getByRole("button", { name: "Approve independently", exact: true })
      .click();
    const approval = await approved;
    expect(approval.status(), await approval.text()).toBe(200);
    paper = await approval.json();
    expect(paper.status).toBe("APPROVED");
    await expect(reviewDetail.locator(".grc-status")).toContainText(
      `v${paper.version}`,
    );
    paper = await uiStage(reviewer, "approved_for_submission");
    await expect(panel.getByText(/Source freshness: CURRENT/)).toBeVisible();
    await panel.scrollIntoViewIfNeeded();
    await reviewer.screenshot({
      path: `${screenshots}/AE-IN-foreign-obligation-reviewed-period.png`,
    });
    const retained = paper;
    await action(reviewer.request, audit, originals.facts, "reopen");
    const after: Paper = await get(
      reviewer.request,
      `${audit}/records/${paper.id}`,
    );
    expect(after.body).toEqual(retained.body);
    expect(after.version).toBe(retained.version);
    const calendar = await get(
      reviewer.request,
      `${base}/compliance-calendar?record_id=${paper.id}`,
    );
    expect(calendar.items).toHaveLength(1);
    expect(calendar.items[0].freshness).toBe("STALE");
    expect(calendar.items[0].reassessment_required).toBe(true);
    panel = await open(reviewer);
    await expect(panel.getByText(/Source freshness: STALE/)).toBeVisible();
    await panel
      .getByRole("combobox", { name: "Next filing stage", exact: true })
      .selectOption("preparing");
    await expect(
      panel.getByRole("button", {
        name: "Record evidenced filing stage",
        exact: true,
      }),
    ).toBeDisabled();
    await panel.scrollIntoViewIfNeeded();
    await reviewer.screenshot({
      path: `${screenshots}/AE-IN-foreign-obligation-withdrawn-stale.png`,
    });
    const metadata = await get(
      page.request,
      `intelligence/engagements/${eid}/country-workflows`,
    );
    expect(metadata.country).toBe("AE");
    expect(metadata.default_currency).toBe("AED");
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

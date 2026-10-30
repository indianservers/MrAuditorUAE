import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

const folder = "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-gst";
const sample = JSON.parse(
  readFileSync(`${folder}/parameters-and-expectations.json`, "utf8"),
);
const screenshots = "test-results/country-reports";

async function login(page: Page, email: string) {
  const password = process.env.AUDITOS_SMOKE_PASSWORD;
  if (!password || !email)
    throw new Error("Explicit isolated smoke identities required");
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
    .selectOption("IN");
  await expect(
    page.getByRole("combobox", { name: "Working country", exact: true }),
  ).toHaveValue("IN");
}

test("synthetic India annual GST PAN facts, pending controls, independent approval, export and stale history", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  expect(sample.real_client_data).toBe(false);
  expect(sample.professional_validation).toBe("NOT_ESTABLISHED");
  mkdirSync(screenshots, { recursive: true });
  page.setDefaultTimeout(20000);
  await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 1440, height: 1200 },
  });
  const reviewer = await context.newPage();
  reviewer.setDefaultTimeout(20000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  reviewer.on("pageerror", (error) => errors.push(error.message));
  try {
    await login(reviewer, process.env.AUDITOS_SMOKE_REVIEWER_EMAIL!);
    const headers = {
      "X-Tenant-ID": identities.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    };
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
      code: `ANNUAL-GST-${Date.now()}`,
      name: "SYNTHETIC annual GST control client",
    });
    const entity = await post(page.request, "entities", {
      client_id: client.id,
      name: "SYNTHETIC annual GST India entity",
      country: "IN",
      jurisdiction: "India",
      functional_currency: "INR",
      presentation_currency: "INR",
    });
    const period = await post(page.request, "financial-periods", {
      entity_id: entity.id,
      start_date: "2025-04-01",
      end_date: "2026-03-31",
    });
    const engagement = await post(page.request, "engagements", {
      entity_id: entity.id,
      period_id: period.id,
      name: "SYNTHETIC annual GST scope",
      engagement_type: "External Audit",
    });
    const eid = engagement.id;
    await post(
      page.request,
      `engagements/${eid}/audit/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    const { prefix, evidence, prepare, completed } = makeWorkflowHarness(
      page,
      eid,
      identities.tenant_id,
    );
    const sources: Record<string, WorkflowEvent> = {};
    for (const [role, table, total] of [
      ["scope", "turnover-scope", null],
      ["books", "turnover-amounts", "30000000"],
      ["return", "turnover-amounts", "30000000"],
      ["adjustments", "turnover-adjustments", "0"],
    ] as const) {
      const file = await evidence(
        `SYNTHETIC-annual-gst-${role}.csv`,
        readFileSync(`${folder}/${role}.csv`),
      );
      const source = await prepare({
        evidence_version_id: file.version.id,
        table_type: table,
        label: `SYNTHETIC annual GST ${role}`,
        expected_rows: 1,
        control_totals: total === null ? {} : { INR: total },
      });
      sources[role] = await post(
        reviewer.request,
        `${prefix}/events/${source.id}/review`,
        {
          expected_version: source.version,
          action: "approve",
          comments:
            "SYNTHETIC independent annual turnover source assessment; no client qualification",
        },
      );
      expect(sources[role].body.review_status).toBe("REVIEWED");
    }
    const facts = sample.gst_annual_scope;
    async function fillScope(complete: boolean) {
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await expect(
        page.getByRole("textbox", { name: "Account currency", exact: true }),
      ).toHaveValue("INR");
      await page
        .getByRole("combobox", { name: "Workflow", exact: true })
        .selectOption("tax-turnover-bridge");
      for (const [role, source] of Object.entries(sources))
        await page
          .getByRole("combobox", { name: `${role} source`, exact: true })
          .selectOption(source.id);
      await page
        .getByRole("textbox", { name: "Schedule title", exact: true })
        .fill(
          `SYNTHETIC annual GST ${complete ? "controlled" : "pending"} result`,
        );
      await page
        .getByLabel("Reconciliation date", { exact: true })
        .fill(sample.as_of);
      await page
        .getByRole("textbox", {
          name: "Scope and source rationale",
          exact: true,
        })
        .fill(
          "SYNTHETIC full-year reviewed registration sources and explicitly assessed PAN population",
        );
      await page
        .getByRole("checkbox", {
          name: "Assess GSTR-9 / GSTR-9C candidates with this turnover bridge",
          exact: true,
        })
        .check();
      await page
        .getByRole("textbox", { name: "PAN", exact: true })
        .fill(facts.pan);
      for (const [label, key] of [
        ["Annual GST financial year start", "financial_year_start"],
        ["Annual GST financial year end", "financial_year_end"],
        ["Annual GST rule review date", "rule_review_date"],
      ])
        await page.getByLabel(label, { exact: true }).fill(facts[key]);
      await page
        .getByRole("combobox", {
          name: "Assessed annual GST taxpayer status",
          exact: true,
        })
        .selectOption(facts.taxpayer_type);
      await page
        .getByRole("textbox", {
          name: "Annual GST population, taxpayer status and legal review basis",
          exact: true,
        })
        .fill(facts.assessment);
      if (complete) {
        await page
          .getByRole("textbox", {
            name: "PAN-wide aggregate turnover (INR)",
            exact: true,
          })
          .fill(facts.aggregate_turnover);
        await page
          .getByRole("textbox", {
            name: "Other PAN turnover outside this registration bridge (INR)",
            exact: true,
          })
          .fill(facts.other_pan_turnover);
        await page
          .getByRole("checkbox", {
            name: "PAN-wide population assessed complete, including all registrations and other turnover",
            exact: true,
          })
          .check();
      }
    }
    async function queue() {
      const submitted = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          response.url().endsWith(`/${prefix}/jobs`),
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const response = await submitted;
      expect(response.status(), await response.text()).toBe(202);
      return {
        payload: response.request().postDataJSON().payload,
        result: await completed((await response.json()).id),
      };
    }
    await fillScope(false);
    const pending = await queue();
    expect(pending.payload.gst_annual_scope).toMatchObject({
      aggregate_turnover: null,
      other_pan_turnover: null,
      pan_population_complete: false,
    });
    expect(pending.result.body.blocked).toBe(true);
    expect(pending.result.body.annual_gst_assessment).toMatchObject({
      gstr9: "PENDING_REVIEW",
      gstr9c: "PENDING_REVIEW",
      pending_reasons: expect.arrayContaining([
        "PAN_TURNOVER_CONTROL_MISSING",
        "PAN_POPULATION_NOT_ASSESSED_COMPLETE",
      ]),
    });
    await reviewer.goto(
      `/intelligence/${eid}/country-workflow?event=${pending.result.id}`,
    );
    const pendingRegion = reviewer.getByRole("region", {
      name: "Annual GST applicability candidates",
      exact: true,
    });
    await expect(pendingRegion).toContainText("PAN_TURNOVER_CONTROL_MISSING");
    await expect(pendingRegion).toContainText("Not supplied");
    await expect(
      reviewer.getByRole("button", {
        name: "Independent approval",
        exact: true,
      }),
    ).toBeDisabled();
    const forcedReview = await reviewer.request.post(
      `/api/backend/${prefix}/events/${pending.result.id}/review`,
      {
        headers,
        data: {
          expected_version: pending.result.version,
          action: "approve",
          comments: "SYNTHETIC blocked annual scope must not be approvable",
        },
      },
    );
    expect(forcedReview.status()).toBe(409);
    await pendingRegion.screenshot({
      path: `${screenshots}/IN-annual-gst-missing-controls-pending.png`,
    });
    await fillScope(true);
    await page
      .getByRole("group", {
        name: "India annual GST applicability candidates",
        exact: true,
      })
      .screenshot({
        path: `${screenshots}/IN-annual-gst-explicit-pan-scope.png`,
      });
    const positive = await queue();
    expect(positive.payload.gst_annual_scope).toEqual(facts);
    const result = positive.result;
    expect(result.body.blocked).toBe(false);
    expect(result.body.statutory_calculation_qualified).toBe(false);
    expect(result.body.annual_gst_assessment).toMatchObject({
      contract: "india-annual-gst-candidates/1",
      scope: facts,
      gstr9: "CANDIDATE_REQUIRED",
      gstr9c: "CANDIDATE_THRESHOLD_NOT_EXCEEDED",
      registration_turnover: "30000000",
      pending_reasons: [],
      statutory_qualification: false,
      filing_status: "NOT_ESTABLISHED",
    });
    await page.goto(`/intelligence/${eid}/country-workflow?event=${result.id}`);
    await page
      .getByRole("textbox", {
        name: "Review / exception rationale",
        exact: true,
      })
      .fill("SYNTHETIC author approval must remain prohibited");
    const selfDecision = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().endsWith(`/events/${result.id}/review`),
    );
    await page
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    expect((await selfDecision).status()).toBe(403);
    await reviewer.goto(
      `/intelligence/${eid}/country-workflow?event=${result.id}`,
    );
    await reviewer
      .getByRole("textbox", {
        name: "Review / exception rationale",
        exact: true,
      })
      .fill(
        "SYNTHETIC independent annual GST candidate assessment, not a statutory opinion or filing",
      );
    const decision = reviewer.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        r.url().endsWith(`/events/${result.id}/review`),
    );
    await reviewer
      .getByRole("button", { name: "Independent approval", exact: true })
      .click();
    const reviewed = await decision;
    expect(reviewed.status(), await reviewed.text()).toBe(201);
    const approved: WorkflowEvent = await reviewed.json();
    expect(approved.body.review_status).toBe("REVIEWED");
    await expect(
      reviewer.getByRole("combobox", {
        name: "Saved source or result",
        exact: true,
      }),
    ).toHaveValue(approved.id);
    const downloadEvent = reviewer.waitForEvent("download");
    await reviewer
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    const downloadPath = await (await downloadEvent).path();
    expect(downloadPath).not.toBeNull();
    execFileSync(
      process.platform === "win32"
        ? "../backend/.venv/Scripts/python.exe"
        : "../backend/.venv/bin/python",
      [
        "-c",
        "import io,json,sys\nfrom openpyxl import load_workbook\nw=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True)\na=json.loads(dict(w['Source and review'].values)['annual_gst_assessment'])\nassert a['gstr9']=='CANDIDATE_REQUIRED' and a['gstr9c']=='CANDIDATE_THRESHOLD_NOT_EXCEEDED'\nassert a['scope']['aggregate_turnover']=='30000000' and a['scope']['other_pan_turnover']=='0'\nassert a['statutory_qualification'] is False and a['filing_status']=='NOT_ESTABLISHED'\nassert len(list(w['Rows'].values))==2\nw.close()",
      ],
      { input: readFileSync(downloadPath!), timeout: 15000 },
    );
    const positiveRegion = reviewer.getByRole("region", {
      name: "Annual GST applicability candidates",
      exact: true,
    });
    await expect(positiveRegion).toContainText("30000000");
    await expect(positiveRegion).toContainText(
      "CANDIDATE_THRESHOLD_NOT_EXCEEDED",
    );
    await positiveRegion.screenshot({
      path: `${screenshots}/IN-annual-gst-reviewed-candidates.png`,
    });
    const historical = structuredClone(approved.body);
    await post(
      reviewer.request,
      `${prefix}/events/${sources.scope.id}/review`,
      {
        expected_version: sources.scope.version,
        action: "reject",
        comments:
          "SYNTHETIC annual PAN coverage source withdrawn; preserve original candidates",
      },
    );
    const staleResponse = await reviewer.request.get(
      `/api/backend/${prefix}/events/${approved.id}`,
      { headers },
    );
    expect(staleResponse.status()).toBe(200);
    const stale = await staleResponse.json();
    expect(stale.freshness).toBe("STALE");
    expect(stale.body).toEqual(historical);
    const reloadedResponse = reviewer.waitForResponse(
      (r) =>
        r.request().method() === "GET" &&
        new URL(r.url()).pathname ===
          `/api/backend/${prefix}/events/${approved.id}`,
      { timeout: 30000 },
    );
    await reviewer.goto(
      `/intelligence/${eid}/country-workflow?event=${approved.id}`,
    );
    const reloaded = await reloadedResponse;
    expect(reloaded.status(), await reloaded.text()).toBe(200);
    expect((await reloaded.json()).body).toEqual(historical);
    await expect(
      reviewer.getByRole("combobox", {
        name: "Saved source or result",
        exact: true,
      }),
    ).toHaveValue(approved.id);
    await expect(
      reviewer.getByText("STALE", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      reviewer.getByRole("button", {
        name: "Independent approval",
        exact: true,
      }),
    ).toBeDisabled();
    await reviewer.setViewportSize({ width: 2200, height: 2600 });
    await expect(
      reviewer.getByRole("textbox", { name: "Account currency", exact: true }),
    ).toHaveValue("INR");
    const stalePanel = reviewer
      .getByRole("heading", {
        name: "SYNTHETIC annual GST controlled result",
        exact: true,
      })
      .locator("..");
    await stalePanel.scrollIntoViewIfNeeded();
    await expect(stalePanel).toBeInViewport({ ratio: 1 });
    await expect(
      reviewer.getByRole("row").filter({
        has: reviewer.getByRole("cell", {
          name: "29ABCDE1234F1Z5",
          exact: true,
        }),
      }),
    ).toBeInViewport({ ratio: 1 });
    await reviewer.screenshot({
      path: `${screenshots}/IN-annual-gst-withdrawn-source-stale.png`,
    });
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

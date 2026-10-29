import { runMerchantBrowserWorkflow } from "./merchant-browser-workflow";
import { runPayrollProrationBrowserWorkflow } from "./payroll-proration-browser-workflow";
import { runBenefitSettlementBrowserWorkflow } from "./benefit-settlement-browser-workflow";
import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { runMSMEBrowserWorkflow } from "./msme-browser-workflow";
import { runUAEBankBrowserWorkflow } from "./bank-browser-workflow";

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
    test.setTimeout(240000);
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
      .getByRole("combobox", { name: "Report category", exact: true })
      .selectOption("vat");
    if (code === "AE") {
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .selectOption("uae-vat201-review:emirate-20/1");
      await expect(
        page.getByLabel("Requirement reference 1", { exact: true }),
      ).toHaveValue("vat201.box.1a");
      await expect(
        page.getByLabel("Requirement reference 1", { exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByLabel("Evidence/calculation source required for item 1", {
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", {
          name: "Remove requirement 20",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", {
          name: "Save template version",
          exact: true,
        }),
      ).toBeDisabled();
      await page.setViewportSize({ width: 1440, height: 1600 });
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `${screenshots}/AE-vat201-report-preset.png`,
      });
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .selectOption("uae-vat201-review:ecommerce-20/1");
      await expect(
        page.getByLabel("Requirement reference 20", { exact: true }),
      ).toHaveValue("vat201.box.14");
      await expect(
        page.getByRole("button", {
          name: "Save template version",
          exact: true,
        }),
      ).toBeDisabled();
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `${screenshots}/AE-vat201-ecommerce-report-preset.png`,
      });
      await page.setViewportSize({ width: 1440, height: 1000 });
    } else {
      await expect(
        page.getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        }),
      ).toHaveCount(0);
      await page
        .getByRole("combobox", { name: "Report category", exact: true })
        .selectOption("india-tax-audit");
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .selectOption("india-form26-index:A/1");
      await expect(
        page.getByLabel("Requirement reference 65", { exact: true }),
      ).toHaveValue("form26.schedule.quantities");
      await expect(
        page.getByLabel("Requirement reference 65", { exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByLabel("Evidence/calculation source required for item 1", {
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", {
          name: "Remove requirement 65",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        page.getByRole("button", {
          name: "Save template version",
          exact: true,
        }),
      ).toBeDisabled();
      await page.setViewportSize({ width: 1440, height: 1600 });
      await page
        .getByRole("combobox", {
          name: "Operational report preset",
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `${screenshots}/IN-form26-evidence-index.png`,
      });
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await page
      .getByRole("combobox", { name: "Report category", exact: true })
      .selectOption(code === "AE" ? "uae-ifrs" : "india-statutory");
    await page
      .getByRole("combobox", { name: "Content type", exact: true })
      .selectOption("narrative");
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
    if (
      await page.getByRole("button", { name: "Dismiss notification" }).count()
    ) {
      await page.getByRole("button", { name: "Dismiss notification" }).click();
    }
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
    await expect(
      coverage.getByText(/CURRENT_REVIEWED_SOURCES_RECHECKED/),
    ).toBeVisible();
    if ((await coverage.locator("details").getAttribute("open")) === null) {
      await coverage.locator("summary").click();
    }
    await expect(coverage.getByText(/No statutory opinion/)).toBeVisible();
    if (
      await reviewer
        .getByRole("button", { name: "Dismiss notification" })
        .count()
    ) {
      await reviewer
        .getByRole("button", { name: "Dismiss notification" })
        .click();
    }
    await coverage.screenshot({
      path: `${screenshots}/${code}-reviewed-coverage.png`,
    });

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
    // Reuse the same isolated country scope to exercise the committed GL source form.
    const csv =
      "Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration\n400,Revenue,SALE,2026-06-15,0,100.20,T1,false,false,Sale\n100,Cash,SALE,2026-06-15,100.20,0,T2,false,false,Sale\n";
    const imported = await page.request.post(
      "/api/backend/accounting/imports",
      {
        headers: {
          "X-Tenant-ID": identities.tenant_id,
          Origin: process.env.AUDITOS_E2E_ORIGIN!,
        },
        multipart: {
          options: JSON.stringify({
            client_id: client.id,
            entity_id: entity.id,
            period_id: period.id,
            currency: code === "AE" ? "AED" : "INR",
            expected_rows: 2,
            expected_debit: "100.20",
            expected_credit: "100.20",
            source_complete: true,
          }),
          file: {
            name: "synthetic-turnover.csv",
            mimeType: "text/csv",
            buffer: Buffer.from(csv),
          },
        },
      },
    );
    expect(imported.status(), await imported.text()).toBe(201);
    const batch = await imported.json();
    const validated = await post(
      page.request,
      `accounting/imports/${batch.id}/validate`,
      {},
      200,
    );
    expect(validated.status).toBe("validated");
    await post(page.request, `accounting/imports/${batch.id}/commit`, {}, 200);
    const details = await page.request.get(
      `/api/backend/accounting/imports/${batch.id}`,
      {
        headers: { "X-Tenant-ID": identities.tenant_id },
      },
    );
    expect(details.status()).toBe(200);
    const snapshot = (await details.json()).snapshot_id;
    await page.goto(`/intelligence/${engagement.id}/workflow-source`);
    await page
      .getByText("Prepare book turnover from committed GL", { exact: true })
      .click();
    await page
      .getByRole("combobox", {
        name: "Turnover committed snapshot",
        exact: true,
      })
      .selectOption(snapshot);
    const revenue = page.getByRole("listbox", {
      name: "Turnover revenue accounts",
      exact: true,
    });
    await expect(
      revenue.getByRole("option", { name: "400 · Revenue", exact: true }),
    ).toHaveCount(1);
    await revenue.selectOption({ label: "400 · Revenue" });
    for (const [name, value] of [
      [
        `Turnover registration (${code === "AE" ? "TRN" : "GSTIN"})`,
        code === "AE" ? "100000000000001" : "27ABCDE1234F1Z5",
      ],
      ["Turnover period start", "2026-06-01"],
      ["Turnover period end", "2026-06-30"],
      [
        `Independent signed book turnover (${code === "AE" ? "AED" : "INR"})`,
        "100.20",
      ],
      [
        "Revenue account and registration allocation assessment",
        "SYNTHETIC explicit revenue account and registration allocation",
      ],
      ["Turnover book source title", "SYNTHETIC browser committed turnover"],
    ])
      await page.getByLabel(name, { exact: true }).fill(value);
    const prepareBooks = page.getByRole("button", {
      name: "Prepare turnover books",
      exact: true,
    });
    await expect(prepareBooks).toBeDisabled();
    await page
      .getByLabel("Independent GL movement line count", { exact: true })
      .fill("1");
    const preparedResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/turnover-ledger-source") &&
        r.request().method() === "POST",
    );
    await prepareBooks.click();
    const preparedBooks = await preparedResponse;
    expect(preparedBooks.status(), await preparedBooks.text()).toBe(201);
    const books = await preparedBooks.json();
    expect(books.body.review_status).toBe("UNVERIFIED");
    expect(books.body.allowed_source_roles).toEqual(["books"]);
    expect(books.body.ledger_line_count).toBe(1);
    const turnoverForm = page.locator("details").filter({
      has: page.getByText("Prepare book turnover from committed GL", {
        exact: true,
      }),
    });
    await expect(prepareBooks).toBeEnabled();
    if (
      await page.getByRole("button", { name: "Dismiss notification" }).count()
    ) {
      await page.getByRole("button", { name: "Dismiss notification" }).click();
    }
    await page.setViewportSize({ width: 1440, height: 1800 });
    await turnoverForm.scrollIntoViewIfNeeded();
    await turnoverForm.screenshot({
      path: `${screenshots}/${code}-turnover-ledger.png`,
    });
    const reviewBooks = await post(
      reviewer.request,
      `intelligence/engagements/${engagement.id}/events/${books.id}/review`,
      {
        expected_version: books.version,
        action: "approve",
        comments: "SYNTHETIC independent book source review",
      },
    );
    const nilBooks = await post(
      page.request,
      `intelligence/engagements/${engagement.id}/turnover-ledger-source`,
      {
        snapshot_id: snapshot,
        account_ids: books.body.native_metadata.account_ids,
        registration: books.body.native_metadata.registration,
        period_start: "2026-07-01",
        period_end: "2026-07-31",
        currency: code === "AE" ? "AED" : "INR",
        expected_rows: 0,
        expected_amount: "0",
        nil_reason: "SYNTHETIC no movements in the selected July accounts",
        assessment:
          "SYNTHETIC assessed registration and revenue account allocation",
        label: "SYNTHETIC July nil book movements",
      },
    );
    const reviewNil = await post(
      reviewer.request,
      `intelligence/engagements/${engagement.id}/events/${nilBooks.id}/review`,
      {
        expected_version: nilBooks.version,
        action: "approve",
        comments: "SYNTHETIC independent nil book source review",
      },
    );
    await page.reload();
    await page
      .getByText("Combine reviewed turnover book schedules", { exact: true })
      .click();
    await page
      .getByRole("listbox", {
        name: "Reviewed turnover book components",
        exact: true,
      })
      .selectOption([reviewBooks.id, reviewNil.id]);
    for (const [name, value] of [
      ["Independent combined book row count", "2"],
      [
        `Independent combined signed turnover (${code === "AE" ? "AED" : "INR"})`,
        "100.20",
      ],
      [
        "Combined books scope and disjointness assessment",
        "SYNTHETIC independently reviewed June and July book scopes",
      ],
      [
        "Combined turnover books title",
        "SYNTHETIC browser combined turnover books",
      ],
    ])
      await page.getByLabel(name, { exact: true }).fill(value);
    const compositionResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/turnover-books-composition") &&
        r.request().method() === "POST",
    );
    const composeButton = page.getByRole("button", {
      name: "Prepare combined turnover books",
      exact: true,
    });
    await composeButton.click();
    const composedResponse = await compositionResponse;
    expect(composedResponse.status(), await composedResponse.text()).toBe(201);
    const composed = await composedResponse.json();
    expect(composed.body.rows).toHaveLength(2);
    expect(
      composed.body.rows.every(
        (r: { source_component_event_id?: string }) =>
          !!r.source_component_event_id,
      ),
    ).toBe(true);
    expect(composed.body.review_status).toBe("UNVERIFIED");
    const review = {
      expected_version: composed.version,
      action: "approve",
      comments: "SYNTHETIC independent combined books review",
    };
    await post(
      page.request,
      `intelligence/engagements/${engagement.id}/events/${composed.id}/review`,
      review,
      403,
    );
    await post(
      reviewer.request,
      `intelligence/engagements/${engagement.id}/events/${composed.id}/review`,
      review,
    );
    await expect(composeButton).toBeEnabled();
    if (
      await page.getByRole("button", { name: "Dismiss notification" }).count()
    ) {
      await page.getByRole("button", { name: "Dismiss notification" }).click();
    }
    const compositionForm = page.locator("details").filter({
      has: page.getByText("Combine reviewed turnover book schedules", {
        exact: true,
      }),
    });
    await compositionForm.scrollIntoViewIfNeeded();
    await compositionForm.screenshot({
      path: `${screenshots}/${code}-turnover-composition.png`,
    });
    if (code === "IN") {
      const supporting = await post(
        page.request,
        `engagements/${engagement.id}/audit/evidence`,
        {
          reference: `SYNTHETIC-ITEM-SUPPORT-${Date.now()}`,
          title: "SYNTHETIC source metadata only",
          body: {
            category: "Other",
            retain_until: "2036-12-31",
            narrative:
              "SYNTHETIC metadata for draft mapping controls; no client or legal evidence qualification",
          },
        },
      );
      await page.goto(`/engagements/${engagement.id}/working-papers`);
      await page
        .getByRole("button", { name: "New record", exact: true })
        .click();
      await page
        .getByLabel("Reference", { exact: true })
        .fill(`SYNTHETIC-ITEM-WP-${Date.now()}`);
      await page
        .getByLabel("Title", { exact: true })
        .fill("SYNTHETIC workpaper item mapping draft");
      await page
        .getByRole("textbox", { name: /^folder/i })
        .fill("SYNTHETIC report mappings");
      await page
        .getByLabel("Section 1 text", { exact: true })
        .fill(
          "SYNTHETIC substantive mapping mechanics and source assessment; no legal conclusion",
        );
      await page
        .getByRole("textbox", { name: /^conclusion/i })
        .fill("SYNTHETIC draft controls only; not reviewed client findings");
      await page
        .getByRole("combobox", { name: "Link source record", exact: true })
        .selectOption(supporting.id);
      await page
        .getByRole("combobox", {
          name: "Declare Form 26 item coverage",
          exact: true,
        })
        .selectOption("yes");
      await page
        .getByRole("combobox", { name: "Workpaper report preset", exact: true })
        .selectOption("india-form26-index:A/1");
      await page
        .getByLabel("Workpaper report period start", { exact: true })
        .fill("2026-04-01");
      await page
        .getByLabel("Workpaper report period end", { exact: true })
        .fill("2027-03-31");
      await page
        .getByRole("listbox", {
          name: "Report items supported by this section",
          exact: true,
        })
        .selectOption("form26.C.1");
      await page
        .getByRole("combobox", {
          name: "Supporting workpaper section",
          exact: true,
        })
        .selectOption("0");
      await page
        .getByRole("listbox", {
          name: "Existing protected supporting sources",
          exact: true,
        })
        .selectOption(`record:${supporting.id}`);
      await page
        .getByLabel("Item support and applicability assessment", {
          exact: true,
        })
        .fill(
          "SYNTHETIC explicit source mapping only, awaiting independent workpaper review",
        );
      await page
        .getByRole("button", {
          name: "Add declared item mappings",
          exact: true,
        })
        .click();
      await page.setViewportSize({ width: 1440, height: 1800 });
      const itemForm = page.getByRole("group", {
        name: "Report item coverage declared in this workpaper",
        exact: true,
      });
      await itemForm.scrollIntoViewIfNeeded();
      await itemForm.screenshot({
        path: `${screenshots}/IN-workpaper-item-mapping.png`,
      });
      const savedPaper = page.waitForResponse(
        (r) =>
          r
            .url()
            .endsWith(`/engagements/${engagement.id}/audit/working-papers`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Save version", exact: true })
        .click();
      const saved = await savedPaper;
      expect(saved.status(), await saved.text()).toBe(201);
      const paper = await saved.json();
      expect(paper.status).toBe("IN_PROGRESS");
      expect(paper.body.report_requirement_scope.items[0].key).toBe(
        "form26.C.1",
      );
      expect(
        paper.body.report_requirement_scope.items[0].supporting_sources,
      ).toEqual([{ kind: "record", id: supporting.id }]);
    }
    await page.goto(`/intelligence/${engagement.id}/country-workflow`);
    if (code === "IN") {
      await page
        .getByRole("combobox", { name: "Workflow", exact: true })
        .selectOption("india-msme-payment-timing");
      await expect(page.getByLabel(/Compare arrears only/)).toHaveCount(0);
      await expect(
        page.getByLabel("Tax-year start (for form guidance)", { exact: true }),
      ).toHaveCount(0);
      for (const role of ["assessments", "invoices", "bank", "allocations"]) {
        await expect(
          page.getByRole("combobox", { name: `${role} source`, exact: true }),
        ).toHaveCount(1);
      }
      for (const [label, value] of [
        ["Buyer identifier", "SYNTHETIC-BUYER"],
        ["First invoice month", "2026-04"],
        ["Last invoice month", "2026-06"],
        ["Bank settlement window starts", "2026-04-01"],
        ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
        ["Account currency", "INR"],
      ]) {
        await page.getByLabel(label, { exact: true }).fill(value);
      }
      await page
        .getByRole("combobox", { name: "Bank payment sign", exact: true })
        .selectOption("debit-negative");
      await expect(
        page.getByLabel("Buyer identifier", { exact: true }),
      ).toHaveValue("SYNTHETIC-BUYER");
      await expect(
        page.getByLabel("First invoice month", { exact: true }),
      ).toHaveValue("2026-04");
      await expect(
        page.getByRole("combobox", { name: "Bank payment sign", exact: true }),
      ).toHaveValue("debit-negative");
      await page.setViewportSize({ width: 1440, height: 1600 });
      await page
        .getByLabel("Buyer identifier", { exact: true })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: `${screenshots}/IN-msme-payment-scope.png`,
      });
    } else {
      await expect(
        page
          .getByRole("combobox", { name: "Workflow", exact: true })
          .locator('option[value="india-msme-payment-timing"]'),
      ).toHaveCount(0);
    }
    await page.goto(`/intelligence/${engagement.id}/workflow-source`);
    const sourceType = page.getByRole("combobox", {
      name: "Source table type",
      exact: true,
    });
    if (code === "IN") {
      await sourceType.selectOption("msme-supplier-assessments");
      const contextForm = page.getByRole("group", {
        name: "MSE supporting document context",
        exact: true,
      });
      await expect(
        contextForm.getByRole("combobox", {
          name: "MSE context document",
          exact: true,
        }),
      ).toHaveValue("");
      await expect(
        contextForm.getByRole("textbox", {
          name: "MSE context scope assessment",
          exact: true,
        }),
      ).toBeDisabled();
      await contextForm.scrollIntoViewIfNeeded();
      await contextForm.screenshot({
        path: `${screenshots}/IN-msme-supporting-context.png`,
      });
    } else {
      await expect(
        sourceType.locator('option[value="msme-supplier-assessments"]'),
      ).toHaveCount(0);
    }
    if (code === "IN")
      await runMSMEBrowserWorkflow(
        page,
        reviewer,
        engagement.id,
        identities.tenant_id,
        screenshots,
      );
    if (code === "AE")
      await runUAEBankBrowserWorkflow(
        page,
        reviewer,
        engagement.id,
        identities.tenant_id,
        snapshot,
        screenshots,
      );
    if (code === "AE")
      await runBenefitSettlementBrowserWorkflow(
        page,
        reviewer,
        engagement.id,
        identities.tenant_id,
        screenshots,
      );
    await runMerchantBrowserWorkflow(
      page,
      reviewer,
      engagement.id,
      identities.tenant_id,
      code,
      screenshots,
      entity.name,
    );
    if (code === "IN")
      await runPayrollProrationBrowserWorkflow(
        page,
        reviewer,
        engagement.id,
        identities.tenant_id,
        screenshots,
      );
    expect(errors).toEqual([]);
    await reviewerContext.close();
  });
}

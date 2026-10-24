import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const fixture = JSON.parse(
  readFileSync("../.local-runtime/country-workflows/fixture.json", "utf8"),
);
const shots = "../docs/country-workflows/screenshots/native-sources";
mkdirSync(shots, { recursive: true });

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
      "from app.core.operations_contracts import implementation_hash; print(implementation_hash())",
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
    await page.getByLabel("Source file format").selectOption(source.format);
    await page.getByLabel("Schedule title", { exact: true }).fill(source.title);
    await page
      .getByLabel("Clean retained evidence")
      .selectOption(source.evidence);
    await page.getByLabel("Expected data rows").fill(source.count);
    await page.getByLabel("Independent totals by currency").fill(source.total);
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
    await saveScreenshot(`${shots}/${source.format}-native-review.png`, () =>
      page.screenshot({ fullPage: true }),
    );
  }
  await page.goto(`/intelligence/${fixture.india_engagement}/country-workflow`);
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

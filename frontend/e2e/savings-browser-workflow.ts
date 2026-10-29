import { expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Original synthetic setup/reviews via APIs; calculation, approval, export and both source bridges use UI. */
export async function runSavingsBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  const root =
    "../docs/country-workflows/sample-inputs/SYNTHETIC-savings-scheme/";
  const manifest = JSON.parse(readFileSync(root + "controls.json", "utf8")) as {
    files: Record<
      string,
      {
        file: string;
        sha256: string;
        table_type: string;
        expected_rows: number;
        control_totals: Record<string, string>;
      }
    >;
    documents: Record<string, { sha256: string }>;
  };
  const documents: Record<string, string> = {};
  for (const [name, spec] of Object.entries(manifest.documents)) {
    const bytes = readFileSync(root + name);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    documents[name] = (
      await evidence("SYNTHETIC-savings-" + name, bytes)
    ).version.id;
  }
  const sources: Record<string, string> = {};
  let originalFund!: WorkflowEvent;
  for (const [role, spec] of Object.entries(manifest.files)) {
    const bytes = readFileSync(root + spec.file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    const retained = await evidence(`SYNTHETIC-savings-${role}.csv`, bytes);
    const source = await prepare({
      evidence_version_id: retained.version.id,
      table_type: spec.table_type,
      expected_rows: spec.expected_rows,
      control_totals: spec.control_totals,
      label: `SYNTHETIC savings ${role}`,
      ...(role === "bases"
        ? { savings_enrolment_document_version_id: documents["enrolment.txt"] }
        : {}),
      ...(role === "rules"
        ? { rule_document_version_id: documents["policy.txt"] }
        : {}),
    });
    const reviewed = (await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Synthetic independent fund enrolment, salary comparator, rate band and original observation controls",
      },
    )) as WorkflowEvent;
    sources[role] = reviewed.id;
    if (role === "reported") originalFund = reviewed;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("uae-savings-review");
  for (const [role, id] of Object.entries(sources))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  const title =
    "SYNTHETIC UAE savings basic contributions and fund observations";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "Synthetic separate enrolment facts, assessed basic wage comparators, fund-specific rates and original fund observations",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const queuedResponse = await queued;
  expect(queuedResponse.status(), await queuedResponse.text()).toBe(202);
  const result = await completed((await queuedResponse.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.expected_total).toBe("1415.90");
  expect(result.body.rows.map((r) => r.state)).toEqual([
    "MATCHED",
    "MATCHED",
    "MATCHED",
    "MATCHED",
  ]);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Synthetic independent enrolment, covered-period salary comparator and fund-specific basic contribution assessment",
    );
  const approved = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approval = await approved;
  expect(approval.status(), await approval.text()).toBe(201);
  const reviewed = (await approval.json()) as WorkflowEvent;
  const saved = structuredClone(reviewed.body);
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(reviewed.id);
  const downloaded = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const downloadPath = await (await downloaded).path();
  expect(downloadPath).toBeTruthy();
  execFileSync(
    process.platform === "win32"
      ? "../backend/.venv/Scripts/python.exe"
      : "../backend/.venv/bin/python",
    [
      "-c",
      "import io,sys,json;from openpyxl import load_workbook;r=list(load_workbook(io.BytesIO(sys.stdin.buffer.read()))['Rows'].values);assert len(r)==5;i={k:v for v,k in enumerate(r[0])};assert r[3][i['expected_amount']]=='291.50';assert r[3][i['hours_ratio']]=='0.5';assert all(json.loads(x[i['savings_scope']])['scheme']=='MOHRE_SAVINGS' for x in r[1:])",
    ],
    { input: readFileSync(downloadPath!), timeout: 15000 },
  );
  await page.goto(`/intelligence/${eid}/country-workflow?event=${reviewed.id}`);
  for (const [label, value] of [
    [
      "Savings expectation title",
      "SYNTHETIC controlled basic savings remittances",
    ],
    [
      "Retained savings remittance due-date evidence",
      documents["due-date.txt"],
    ],
    [
      "Savings remittance scope assessment",
      "Synthetic independently checked employee counts, fund amounts and explicitly assessed due dates",
    ],
  ]) {
    const field = page.getByLabel(label, { exact: true });
    if (label.includes("evidence")) await field.selectOption(value);
    else await field.fill(value);
  }
  for (const [fund, count, amount] of [
    ["SYN-FUND-1", "3", "1166.00"],
    ["SYN-FUND-2", "1", "249.90"],
  ]) {
    const name = `${fund} / SYN-EMPLOYER / 2026-06`;
    await page
      .getByRole("checkbox", {
        name: `Select savings group ${name}`,
        exact: true,
      })
      .check();
    await expect(
      page.getByLabel(`Independent participant count ${name}`, { exact: true }),
    ).toHaveValue("");
    await expect(
      page.getByLabel(`Independent expected total ${name}`, { exact: true }),
    ).toHaveValue("");
    for (const [label, value] of [
      [`Independent participant count ${name}`, count],
      [`Independent expected total ${name}`, amount],
      [`Assessed due date ${name}`, "2026-07-15"],
      [`Due-date reference ${name}`, "SYNTHETIC-DUE-DATE-ASSESSMENT"],
    ])
      await page.getByLabel(label, { exact: true }).fill(value);
  }
  await page.setViewportSize({ width: 2200, height: 3400 });
  const reviewedCard = page
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await expect(
    reviewedCard.getByRole("columnheader", { name: "fund id", exact: true }),
  ).toBeVisible();
  await reviewedCard.evaluate((e) => e.scrollIntoView({ block: "center" }));
  expect(
    (await reviewedCard
      .getByRole("heading", { name: title, exact: true })
      .boundingBox())!.y,
  ).toBeGreaterThan(100);
  await expect(
    reviewedCard.getByText("CURRENT", { exact: true }),
  ).toBeVisible();
  const notice = page.getByRole("button", {
    name: "Dismiss notification",
    exact: true,
  });
  if (await notice.count()) await notice.last().click();
  await reviewedCard.screenshot({
    path: `${screenshots}/AE-savings-contributions-reviewed.png`,
  });
  const expectedWait = page.waitForResponse(
    (r) =>
      r.url().endsWith("/contribution-obligation-source") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Prepare expected savings remittances",
      exact: true,
    })
    .click();
  const expectedResponse = await expectedWait;
  expect(expectedResponse.status(), await expectedResponse.text()).toBe(201);
  const expected = (await expectedResponse.json()) as WorkflowEvent;
  expect(expected.body.review_status).toBe("UNVERIFIED");
  expect(expected.body.rows).toHaveLength(4);
  expect(expected.body.rows.every((r) => r.payment_date === null)).toBe(true);
  await page.goto(
    `/intelligence/${eid}/country-workflow?event=${originalFund.id}`,
  );
  await expect(
    page.getByLabel("Independent original fund row count", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByLabel("Independent original fund contribution total (AED)", {
      exact: true,
    }),
  ).toHaveValue("");
  for (const [label, value] of [
    [
      "Fund observation source title",
      "SYNTHETIC original fund remittance observations",
    ],
    ["Independent original fund row count", "4"],
    ["Independent original fund contribution total (AED)", "1415.90"],
    [
      "Original fund population assessment",
      "Synthetic independent original fund participant population and exact AED controls",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const reportedWait = page.waitForResponse(
    (r) =>
      r.url().endsWith("/savings-reported-obligation-source") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Prepare reported fund remittances",
      exact: true,
    })
    .click();
  const reportedResponse = await reportedWait;
  expect(reportedResponse.status(), await reportedResponse.text()).toBe(201);
  const reported = (await reportedResponse.json()) as WorkflowEvent;
  expect(reported.body.allowed_source_roles).toEqual(["reported"]);
  expect(reported.body.rows).toHaveLength(4);
  await post(reviewer.request, `${prefix}/events/${originalFund.id}/review`, {
    expected_version: originalFund.version,
    action: "reject",
    comments:
      "Synthetic withdrawal of independently reviewed original fund observations",
  });
  for (const obj of [reviewed, expected, reported]) {
    const response = await reviewer.request.get(
      `/api/backend/${prefix}/events/${obj.id}`,
      { headers },
    );
    expect(response.status()).toBe(200);
    const stale = (await response.json()) as WorkflowEvent;
    expect(stale.freshness).toBe("STALE");
    expect(stale.body).toEqual(obj.id === reviewed.id ? saved : obj.body);
  }
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    reviewer.getByRole("region", {
      name: "Expected savings basic remittances",
      exact: true,
    }),
  ).toHaveCount(0);
  await reviewer.setViewportSize({ width: 2200, height: 3000 });
  const staleCard = reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..");
  await staleCard.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await expect(staleCard.getByText("STALE", { exact: true })).toBeVisible();
  expect(
    (await staleCard
      .getByRole("heading", { name: title, exact: true })
      .boundingBox())!.y,
  ).toBeGreaterThan(100);
  await staleCard.screenshot({
    path: `${screenshots}/AE-savings-contributions-withdrawn-stale.png`,
  });
}

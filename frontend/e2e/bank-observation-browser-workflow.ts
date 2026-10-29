import { expect, type Page } from "@playwright/test";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Authored account facts are prepared/reviewed by APIs; window calculation and approval use UI. */
export async function runBankObservationBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  country: "AE" | "IN",
  owner: string,
  screenshots: string,
): Promise<WorkflowEvent> {
  const { prefix, post, evidence, prepare, completed } = makeWorkflowHarness(
    page,
    eid,
    tenant,
  );
  const start = country === "AE" ? "2026-01-01" : "2026-03-01";
  const cutoff = country === "AE" ? "2026-12-31" : "2027-03-31";
  const through = country === "AE" ? "2027-01-05" : "2027-04-05";
  const badThrough = country === "AE" ? "2027-01-06" : "2027-04-06";
  const selected: Record<string, string> = {};
  for (const role of ["register", "ledger", "bank"]) {
    const row = {
      id: "SYNTHETIC-COVERAGE-" + role,
      account: "SYNTHETIC-ACCOUNT",
      bank_country: country,
      account_scheme: country === "AE" ? "IBAN" : "LOCAL",
      account_number:
        country === "AE" ? "AE070331234567890123456" : "000123456789",
      routing_code: country === "AE" ? "033" : "SYNB0ABC123",
      currency: country === "AE" ? "AED" : "INR",
      owner_country: country,
      owner_name: owner,
      owner_identifier_scheme: "SYNTHETIC-REGISTRY",
      owner_identifier: "00123",
      valid_from: start,
      valid_through: through,
      assertion_status: "confirmed",
      evidence_reference: "SYNTHETIC independently assessed " + role,
      assessment:
        "Authored original and post-year document coverage only; no bank authentication or client qualification",
    };
    const csv = (values: string[]) =>
      values.map((v) => '"' + v.replaceAll('"', '""') + '"').join(",");
    const file = await evidence(
      "SYNTHETIC-account-coverage-" + role + ".csv",
      Buffer.from(
        csv(Object.keys(row)) + "\n" + csv(Object.values(row)) + "\n",
      ),
    );
    const source = await prepare({
      evidence_version_id: file.version.id,
      table_type: "bank-account-evidence",
      label: "SYNTHETIC cross-year " + role,
      expected_rows: 1,
      control_totals: {},
    });
    selected[role] = (
      await post(reviewer.request, `${prefix}/events/${source.id}/review`, {
        expected_version: source.version,
        action: "approve",
        comments:
          "Independent authored full-window account document comparison only",
      })
    ).id;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption("bank-account-evidence");
  for (const [role, id] of Object.entries(selected))
    await page.getByLabel(role + " source", { exact: true }).selectOption(id);
  const title = "SYNTHETIC " + country + " year-end account coverage";
  for (const [label, value] of [
    ["Schedule title", title],
    ["Reconciliation date", cutoff],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", country === "AE" ? "AED" : "INR"],
    ["Engagement legal entity name", owner],
    ["Owner identifier scheme", "SYNTHETIC-REGISTRY"],
    ["Owner identifier", "00123"],
    ["Account coverage starts (optional)", start],
    ["Account coverage through (optional)", badThrough],
    [
      "Account coverage assessment",
      "Independent all-three-source assessment across the original financial cutoff and later payment observations",
    ],
    [
      "Scope and source rationale",
      "Authored original and subsequent account documents; financial cutoff remains unchanged",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  async function queue() {
    const waiting = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Queue calculation", exact: true })
      .click();
    const response = await waiting;
    expect(response.status(), await response.text()).toBe(202);
    return completed((await response.json()).id);
  }
  const bad = await queue();
  expect(bad.body.blocked).toBe(true);
  expect(bad.freshness).toBe("CURRENT");
  await reviewer.goto(`/intelligence/${eid}/country-workflow?event=${bad.id}`);
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    reviewer
      .getByRole("table", {
        name: "Bank account identity observations",
        exact: true,
      })
      .getByRole("cell", { name: /account evidence outside validity/i }),
  ).toHaveCount(3);
  async function capture(name: string) {
    const viewport = reviewer.viewportSize();
    try {
      await reviewer.setViewportSize({ width: 2200, height: 3400 });
      const heading = reviewer.getByRole("heading", {
        name: title,
        exact: true,
      });
      await heading.scrollIntoViewIfNeeded();
      await expect(heading).toBeInViewport();
      await expect(
        reviewer.getByText(`Financial cutoff: ${cutoff}.`, { exact: true }),
      ).toBeInViewport();
      await expect(
        reviewer.getByText(/Assessed document coverage:/),
      ).toBeInViewport();
      await expect(
        reviewer
          .getByRole("table", {
            name: "Bank account identity observations",
            exact: true,
          })
          .getByRole("row")
          .filter({ hasText: "evidence reference" }),
      ).toBeInViewport();
      await reviewer.screenshot({
        path: `${screenshots}/${country}-account-coverage-${name}.png`,
        fullPage: true,
      });
    } finally {
      if (viewport) await reviewer.setViewportSize(viewport);
    }
  }
  await capture("incomplete-blocked");
  await page
    .getByLabel("Account coverage through (optional)", { exact: true })
    .fill(through);
  const good = await queue();
  expect(good.body.blocked).toBe(false);
  await reviewer.goto(`/intelligence/${eid}/country-workflow?event=${good.id}`);
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Independent synthetic coverage assessment, including original cutoff and later observations; not bank authentication",
    );
  const waiting = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${good.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const response = await waiting;
  expect(response.status(), await response.text()).toBe(201);
  const approved: WorkflowEvent = await response.json();
  await expect(
    reviewer.getByLabel("Saved source or result", { exact: true }),
  ).toHaveValue(approved.id);
  await expect(reviewer.getByText(/Assessed document coverage:/)).toHaveText(
    new RegExp(start + " through " + through),
  );
  await capture("reviewed");
  return approved;
}

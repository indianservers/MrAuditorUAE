import { expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

/** Actual API setup; calculation, approval and remittance preparation use the UI. */
export async function runEstablishmentChargesBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { prefix, headers, post, evidence, prepare, completed } =
    makeWorkflowHarness(page, eid, tenant);
  async function captureCompleteSchedule(name: string) {
    const previousViewport = page.viewportSize();
    try {
      await page.setViewportSize({ width: 2200, height: 3400 });
      const title = page.getByRole("heading", {
        name: "SYNTHETIC India establishment charges",
        exact: true,
      });
      await title.scrollIntoViewIfNeeded();
      await expect(title).toBeInViewport();
      // The application scrolls inside its shell; fullPage alone clips rows.
      await expect(
        page.getByRole("row", { name: /SYN-EST-C.*PF:EDLI/ }),
      ).toBeInViewport();
      await page.screenshot({
        path: `${screenshots}/${name}.png`,
        fullPage: true,
      });
    } finally {
      if (previousViewport) await page.setViewportSize(previousViewport);
    }
  }
  const root =
    "../docs/country-workflows/sample-inputs/SYNTHETIC-establishment-charges/";
  const manifest = JSON.parse(readFileSync(root + "controls.json", "utf8")) as {
    expected_total: string;
    authored_expected: {
      registration: string;
      component: string;
      expected_amount: string;
    }[];
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
  const policyBytes = readFileSync(root + "policy.txt");
  expect(createHash("sha256").update(policyBytes).digest("hex")).toBe(
    manifest.documents["policy.txt"].sha256,
  );
  const policy = await evidence(
    "SYNTHETIC-establishment-policy.txt",
    policyBytes,
  );
  const selected: Record<string, string> = {};
  for (const [role, spec] of Object.entries(manifest.files)) {
    const bytes = readFileSync(root + spec.file);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(spec.sha256);
    const original = await evidence(
      `SYNTHETIC-establishment-${role}.csv`,
      bytes,
    );
    const source = await prepare({
      evidence_version_id: original.version.id,
      table_type: spec.table_type,
      expected_rows: spec.expected_rows,
      control_totals: spec.control_totals,
      label: `SYNTHETIC establishment ${role}`,
      ...(role === "rules"
        ? { rule_document_version_id: policy.version.id }
        : {}),
    });
    const reviewed = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "Synthetic independent establishment populations, status, wage controls and assessed policy",
      },
    );
    selected[role] = reviewed.id;
  }
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByRole("combobox", { name: "Workflow", exact: true })
    .selectOption("india-establishment-charges");
  for (const [role, id] of Object.entries(selected))
    await page
      .getByRole("combobox", { name: `${role} source`, exact: true })
      .selectOption(id);
  await page
    .getByLabel("Schedule title", { exact: true })
    .fill("SYNTHETIC India establishment charges");
  await page
    .getByLabel("Reconciliation date", { exact: true })
    .fill("2026-06-30");
  await page
    .getByLabel("Scope and source rationale", { exact: true })
    .fill(
      "Independent per-establishment members, controlled wages and assessed minima; synthetic only",
    );
  const queued = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/jobs`) && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Queue calculation", exact: true })
    .click();
  const submission = await queued;
  expect(submission.status(), await submission.text()).toBe(202);
  const result = await completed((await submission.json()).id);
  expect(result.body.blocked).toBe(false);
  expect(result.body.expected_total).toBe(manifest.expected_total);
  expect(result.body.rows).toHaveLength(6);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "Independent synthetic control review; separate establishments, member caps and one minimum per establishment",
    );
  const approval = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approved = await approval;
  expect(approved.status(), await approved.text()).toBe(201);
  const reviewed = (await approved.json()) as WorkflowEvent;
  const originalBody = structuredClone(reviewed.body);
  await page.goto(`/intelligence/${eid}/country-workflow?event=${reviewed.id}`);
  await expect(
    page.getByRole("columnheader", {
      name: "applied establishment minimum",
      exact: true,
    }),
  ).toBeVisible();
  const form = page.getByRole("region", {
    name: "Expected contribution remittances",
    exact: true,
  });
  await expect(form).toBeVisible();
  await form
    .getByLabel("Expected remittance source title", { exact: true })
    .fill("SYNTHETIC six establishment remittance controls");
  await form
    .getByLabel("Retained due-date evidence version", { exact: true })
    .fill(policy.version.id);
  await form
    .getByLabel("Independent contribution group controls (JSON)", {
      exact: true,
    })
    .fill(
      JSON.stringify(
        manifest.authored_expected.map((row) => ({
          registration: row.registration,
          period: "2026-06",
          component: row.component,
          expected_rows: 1,
          amount: row.expected_amount,
          due_date: "2026-07-15",
          due_date_reference:
            "SYNTHETIC July 15 support, not a statutory default",
        })),
      ),
    );
  // Inspect the actual form label/button contract, not an API-only substitute.
  await form
    .getByLabel("Remittance scope and due-date assessment", { exact: true })
    .fill(
      "Synthetic independent group amounts and July 15 due-date support for all six selected establishment components",
    );
  await captureCompleteSchedule("IN-establishment-charges-reviewed");
  const prepared = page.waitForResponse(
    (r) =>
      r.url().endsWith("/contribution-obligation-source") &&
      r.request().method() === "POST",
  );
  await form
    .getByRole("button", {
      name: "Prepare expected remittance source",
      exact: true,
    })
    .click();
  const response = await prepared;
  expect(response.status(), await response.text()).toBe(201);
  const expectation = (await response.json()) as WorkflowEvent;
  expect(expectation.body.rows).toHaveLength(6);
  expect(expectation.body.allowed_source_roles).toEqual(["expected"]);
  const originalExpectation = structuredClone(expectation.body);
  const replacement = await page.request.post(
    `/api/backend/engagements/${eid}/audit/evidence-files/${policy.record}`,
    {
      headers,
      multipart: {
        file: {
          name: "SYNTHETIC-replaced-charge-policy.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("SYNTHETIC changed assessed charge policy"),
        },
      },
    },
  );
  expect(replacement.status(), await replacement.text()).toBe(201);
  for (const [id, body] of [
    [reviewed.id, originalBody],
    [expectation.id, originalExpectation],
  ] as const) {
    const stale = await page.request.get(
      `/api/backend/${prefix}/events/${id}`,
      { headers },
    );
    expect(stale.status(), await stale.text()).toBe(200);
    const current = await stale.json();
    expect(current.freshness).toBe("STALE");
    expect(current.body).toEqual(body);
  }
  await page.goto(`/intelligence/${eid}/country-workflow?event=${reviewed.id}`);
  await expect(
    page.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("region", {
      name: "Expected contribution remittances",
      exact: true,
    }),
  ).toHaveCount(0);
  await captureCompleteSchedule("IN-establishment-charges-withdrawn-stale");
}

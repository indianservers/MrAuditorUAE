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

const screenshots = "test-results/country-reports";

async function login(page: Page, email: string) {
  if (!email || !process.env.AUDITOS_SMOKE_PASSWORD)
    throw new Error("Explicit isolated synthetic identities required");
  await page.goto("/login");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AUDITOS_SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

function csv(rows: Record<string, unknown>[]) {
  const keys = Object.keys(rows[0]);
  const cell = (value: unknown) =>
    `"${String(value ?? "").replaceAll('"', '""')}"`;
  return Buffer.from(
    [
      keys.map(cell).join(","),
      ...rows.map((row) => keys.map((key) => cell(row[key])).join(",")),
    ].join("\n") + "\n",
  );
}

test("synthetic UAE then India FIFO real-worker review, complete export, independent pages and stale history", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 2200, height: 2600 },
  });
  const reviewer = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  reviewer.on("pageerror", (error) => errors.push(error.message));
  page.setDefaultTimeout(20000);
  reviewer.setDefaultTimeout(20000);
  mkdirSync(screenshots, { recursive: true });
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
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
    for (const country of ["AE", "IN"] as const) {
      const currency = country === "AE" ? "AED" : "INR";
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByLabel("Working country", { exact: true })
          .selectOption(country);
        await expect(
          actor.getByLabel("Working country", { exact: true }),
        ).toHaveValue(country);
      }
      const client = await post(page.request, "clients", {
        code: `FIFO-${country}-${Date.now()}`,
        name: `SYNTHETIC FIFO ${country} client`,
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC FIFO ${country} entity`,
        country,
        jurisdiction: country === "AE" ? "UAE" : "India",
        functional_currency: currency,
        presentation_currency: currency,
      });
      const period = await post(page.request, "financial-periods", {
        entity_id: entity.id,
        start_date: country === "AE" ? "2026-01-01" : "2026-04-01",
        end_date: country === "AE" ? "2026-12-31" : "2027-03-31",
      });
      const engagement = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC FIFO ${country}`,
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
      const harness = makeWorkflowHarness(page, eid, identities.tenant_id);
      const { evidence, prepare, prefix, completed, upload } = harness;
      const original = await evidence(
        `SYNTHETIC-${country}-FIFO-policy.txt`,
        Buffer.from(
          "SYNTHETIC independently assessed gross FIFO opening layers and cost inclusion only; not client or professional qualification",
        ),
      );
      const identity = {
        site: "SYN-SITE",
        sku: "SYN-SKU",
        lot: "SYN-LOT",
        uom: "PCS",
        currency,
      };
      const movement = (
        id: string,
        kind: string,
        quantity: string,
        unit_cost: string | null,
        day: string,
        sequence: number,
      ) => ({
        id,
        ...identity,
        date: day,
        sequence,
        kind,
        quantity,
        unit_cost,
        source_evidence_version_id: original.version.id,
        source_sha256: original.version.sha256,
        evidence_reference: "SYN-OPENING-COST",
        assessment:
          "SYNTHETIC independently assessed FIFO policy and original opening cost",
      });
      const rows = Array.from({ length: 25 }, (_, index) =>
        movement(`O${index}`, "opening", "1", "10", "2026-06-01", index),
      );
      rows.push(movement("I", "issue", "24", null, "2026-06-02", 0));
      const controls = [
        {
          ...identity,
          expected_rows: 26,
          opening_quantity: "25",
          receipt_quantity: "0",
          issue_quantity: "24",
          opening_cost: "250",
          receipt_cost: "0",
          rounding_places: 2,
          rounding_method: "HALF_UP",
        },
      ];
      const sources: Record<string, string> = {};
      for (const role of ["movements", "books"] as const) {
        const input =
          role === "movements"
            ? rows
            : [
                {
                  id: "SYN-BOOK",
                  account: "INV",
                  ...identity,
                  quantity: "1",
                  unit_cost: "10",
                  unit_nrv: "12",
                  ownership: "owned",
                  condition: "good",
                  count_date: "2026-06-30",
                },
              ];
        const file = await evidence(
          `SYNTHETIC-${country}-${role}.csv`,
          csv(input),
        );
        const source = await prepare({
          evidence_version_id: file.version.id,
          table_type:
            role === "movements" ? "inventory-cost-movements" : "stock",
          label: `SYNTHETIC FIFO ${country} ${role}`,
          expected_rows: input.length,
          control_totals: {},
          ...(role === "movements"
            ? { inventory_fifo_controls: controls }
            : {
                inventory_quantity_controls: [
                  {
                    ...identity,
                    expected_rows: 1,
                    positive_quantity: "1",
                    negative_quantity: "0",
                  },
                ],
              }),
        });
        const reviewed = await post(
          reviewer.request,
          `${prefix}/events/${source.id}/review`,
          {
            expected_version: source.version,
            action: "approve",
            comments:
              "SYNTHETIC independent population, cost and original source review",
          },
        );
        expect(reviewed.body.review_status).toBe("REVIEWED");
        sources[role] = reviewed.id;
      }
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByLabel("Workflow", { exact: true })
        .selectOption("inventory-fifo-cost");
      for (const [role, id] of Object.entries(sources))
        await page
          .getByLabel(`${role} source`, { exact: true })
          .selectOption(id);
      const title = `SYNTHETIC ${country} FIFO cost result`;
      for (const [label, value] of [
        ["Schedule title", title],
        ["Reconciliation date", "2026-06-30"],
        ["FIFO period start", "2026-06-01"],
        [
          "FIFO policy and scope assessment",
          "SYNTHETIC independent FIFO gross-cost assessment, opening layer order and rounding",
        ],
        ["Account currency", currency],
        [
          "Scope and source rationale",
          "SYNTHETIC controlled openings and issues with separate original cost support",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const submitted = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/${prefix}/jobs`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const queued = await submitted;
      expect(queued.status(), await queued.text()).toBe(202);
      const result = await completed((await queued.json()).id);
      expect(result.body.blocked).toBe(false);
      expect(result.body.inventory_fifo_document_binding).toBe(
        "RETAINED_DOCUMENT_BYTES_VERIFIED",
      );
      expect(result.body.rows[0]).toMatchObject({
        currency,
        raw_fifo_closing_cost: "10",
        covered_issue_cost: "240",
        raw_cost_rollforward_difference: "0",
      });
      expect(result.body.statutory_calculation_qualified).toBe(false);
      await page.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await page
        .getByLabel("Review / exception rationale", { exact: true })
        .fill("SYNTHETIC own output must not be self approved");
      const self = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/events/${result.id}/review`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      expect((await self).status()).toBe(403);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      await reviewer
        .getByLabel("Review / exception rationale", { exact: true })
        .fill(
          "SYNTHETIC independent cost policy, source controls, issue allocation and closing book assessment",
        );
      const decision = reviewer.waitForResponse(
        (response) =>
          response.url().endsWith(`/events/${result.id}/review`) &&
          response.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const approvedResponse = await decision;
      expect(approvedResponse.status(), await approvedResponse.text()).toBe(
        201,
      );
      const approved: WorkflowEvent = await approvedResponse.json();
      expect(approved.body.review_status).toBe("REVIEWED");
      const panel = reviewer.getByRole("region", {
        name: "FIFO cost evidence",
        exact: true,
      });
      for (const title of [
        "FIFO issue allocations · 24",
        "FIFO movement costs · 26",
        "FIFO closing layers · 1",
        "FIFO source controls · 1",
      ])
        await panel.getByText(title, { exact: true }).click();
      await panel
        .getByRole("button", {
          name: "Next FIFO issue allocations",
          exact: true,
        })
        .click();
      const allocations = panel.getByRole("table", {
        name: "FIFO issue allocations",
        exact: true,
      });
      const events = panel.getByRole("table", {
        name: "FIFO movement costs",
        exact: true,
      });
      await expect(
        allocations.getByRole("cell", { name: "O23", exact: true }),
      ).toBeVisible();
      await expect(
        events.getByRole("cell", { name: "O0", exact: true }),
      ).toBeVisible();
      await expect(
        panel.getByRole("button", {
          name: "Next FIFO issue allocations",
          exact: true,
        }),
      ).toBeDisabled();
      await panel
        .getByRole("button", { name: "Next FIFO movement costs", exact: true })
        .click();
      await expect(
        events.getByRole("cell", { name: "I", exact: true }),
      ).toBeVisible();
      await expect(
        allocations.getByRole("cell", { name: "O23", exact: true }),
      ).toBeVisible();
      await panel.screenshot({
        path: `${screenshots}/${country}-FIFO-reviewed-pages.png`,
      });
      const downloading = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const download = await downloading;
      const downloaded = await download.path();
      expect(downloaded).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          [
            "import io,sys",
            "from openpyxl import load_workbook",
            "w=load_workbook(io.BytesIO(sys.stdin.buffer.read()))",
            "assert w['FIFO allocations'].max_row == 25",
            "assert w['FIFO events'].max_row == 27",
            "assert w['FIFO closing layers'].max_row == 2",
            "assert w['FIFO source controls'].max_row == 2",
          ].join("\n"),
        ],
        { input: readFileSync(downloaded!), timeout: 15000 },
      );
      const snapshot = await page.request.get(
        `/api/backend/${prefix}/events/${approved.id}?fifo_limit=100`,
        { headers },
      );
      expect(snapshot.status()).toBe(200);
      const retained = (await snapshot.json()).body;
      expect(retained.fifo_allocations).toHaveLength(24);
      expect(retained.fifo_event_costs).toHaveLength(26);
      await upload(
        original.record,
        `SYNTHETIC-${country}-revised-policy.txt`,
        Buffer.from(
          "SYNTHETIC revised original FIFO policy requires fresh independent assessment",
        ),
      );
      const historical = await page.request.get(
        `/api/backend/${prefix}/events/${approved.id}?fifo_limit=100`,
        { headers },
      );
      expect(historical.status()).toBe(200);
      const stale = await historical.json();
      expect(stale.freshness).toBe("STALE");
      expect(stale.body).toEqual(retained);
      expect(stale.version).toBe(approved.version);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${approved.id}`,
      );
      await expect(
        reviewer.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(
        reviewer.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/${country}-FIFO-original-replaced-stale.png`,
        });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

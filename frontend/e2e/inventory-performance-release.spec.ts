import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import type { WorkflowEvent } from "./msme-browser-workflow";

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

function ledger(current: boolean, revenue: number) {
  const rows = [
    "Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration",
  ];
  const day = `${current ? 2026 : 2025}-06-01`;
  let sequence = 0;
  function leg(
    code: string,
    name: string,
    reference: string,
    debit: number,
    credit: number,
    opening: boolean,
  ) {
    rows.push(
      `${code},${name},${reference},${day},${debit},${credit},SYN-${sequence++},${opening},false,SYNTHETIC ${reference}`,
    );
  }
  for (let index = 0; index < 21; index++) {
    const code = `INV-${String(index).padStart(2, "0")}`;
    leg(code, `Inventory ${index}`, `OPEN-${index}`, 5, 0, true);
    leg("300", "Equity", `OPEN-${index}`, 0, 5, true);
    if (current) {
      leg(code, `Inventory ${index}`, `STOCK-${index}`, 1, 0, false);
      leg("300", "Equity", `STOCK-${index}`, 0, 1, false);
    }
  }
  leg("400", "Revenue", "REVENUE-OPEN", 0, 50, true);
  leg("300", "Equity", "REVENUE-OPEN", 50, 0, true);
  leg("500", "Cost of sales", "COST-OPEN", 100, 0, true);
  leg("300", "Equity", "COST-OPEN", 0, 100, true);
  leg("400", "Revenue", "SALE", 0, revenue, false);
  leg("200", "Cash", "SALE", revenue, 0, false);
  leg("500", "Cost of sales", "COST", current ? 800 : 600, 0, false);
  leg("200", "Cash", "COST", 0, current ? 800 : 600, false);
  return Buffer.from(rows.join("\n") + "\n");
}

test("synthetic UAE then India stock GP UI controls, independent approval, full lineage export and prior-source staleness", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 2200, height: 2600 },
  });
  const reviewer = await context.newPage();
  const errors: string[] = [];
  for (const actor of [page, reviewer]) {
    actor.setDefaultTimeout(20000);
    actor.on("pageerror", (error) => errors.push(error.message));
  }
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
    async function get(path: string) {
      const response = await page.request.get(`/api/backend/${path}`, {
        headers,
      });
      expect(response.status(), await response.text()).toBe(200);
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
        code: `GP-${country}-${Date.now()}`,
        name: `SYNTHETIC stock GP ${country} client`,
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC stock GP ${country} entity`,
        country,
        jurisdiction: country === "AE" ? "UAE" : "India",
        functional_currency: currency,
        presentation_currency: currency,
      });
      const periods: Record<string, string> = {};
      for (const side of ["current", "prior"]) {
        const year = side === "current" ? 2026 : 2025;
        const period = await post(page.request, "financial-periods", {
          entity_id: entity.id,
          start_date: `${year}-${country === "AE" ? "01" : "04"}-01`,
          end_date: country === "AE" ? `${year}-12-31` : `${year + 1}-03-31`,
        });
        periods[side] = period.id;
      }
      const engagement = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: periods.current,
        name: `SYNTHETIC stock GP ${country}`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id;
      const prefix = `intelligence/engagements/${eid}`;
      await post(
        page.request,
        `engagements/${eid}/audit/team`,
        {
          membership_id: identities.reviewer_membership_id,
          role_id: identities.reviewer_role_id,
        },
        200,
      );
      async function commit(side: string, supersedes?: string) {
        const current = side === "current";
        const uploaded = await page.request.post(
          "/api/backend/accounting/imports",
          {
            headers,
            multipart: {
              options: JSON.stringify({
                client_id: client.id,
                entity_id: entity.id,
                period_id: periods[side],
                currency,
                expected_rows: current ? 92 : 50,
                expected_debit: current ? "2076" : supersedes ? "1656" : "1655",
                expected_credit: current
                  ? "2076"
                  : supersedes
                    ? "1656"
                    : "1655",
                source_complete: true,
                ...(supersedes ? { supersedes_id: supersedes } : {}),
              }),
              file: {
                name: `SYNTHETIC-${country}-${side}${supersedes ? "-corrected" : ""}.csv`,
                mimeType: "text/csv",
                buffer: ledger(
                  current,
                  current ? 1000 : supersedes ? 801 : 800,
                ),
              },
            },
          },
        );
        expect(uploaded.status(), await uploaded.text()).toBe(201);
        const batch = await uploaded.json();
        const validation = await post(
          page.request,
          `accounting/imports/${batch.id}/validate`,
          {},
          200,
        );
        expect(validation.status).toBe("validated");
        await post(
          page.request,
          `accounting/imports/${batch.id}/commit`,
          {},
          200,
        );
        const detail = await get(`accounting/imports/${batch.id}`);
        return { id: batch.id, snapshot: detail.snapshot_id as string };
      }
      const current = await commit("current");
      const prior = await commit("prior");
      const accounts: Record<string, Record<string, string>> = {};
      for (const [side, source] of [
        ["current", current],
        ["prior", prior],
      ] as const) {
        const response = await get(
          `${prefix}/accounts?snapshot_id=${source.snapshot}&comparative=${side === "prior"}`,
        );
        accounts[side] = Object.fromEntries(
          response.items.map((row: { code: string; id: string }) => [
            row.code,
            row.id,
          ]),
        );
      }
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByText(
          "Review stock and gross-profit trends from committed accounts",
          { exact: true },
        )
        .click();
      for (const [side, source] of [
        ["current", current],
        ["prior", prior],
      ] as const) {
        await page
          .getByLabel(`${side} stock/GP snapshot`, { exact: true })
          .selectOption(source.snapshot);
        for (const metric of ["inventory", "revenue", "cost_of_sales"]) {
          const name = `${side} ${metric.replaceAll("_", " ")}`;
          const codes =
            metric === "inventory"
              ? Array.from(
                  { length: 21 },
                  (_, i) => `INV-${String(i).padStart(2, "0")}`,
                )
              : [metric === "revenue" ? "400" : "500"];
          await page
            .getByLabel(`${name} accounts`, { exact: true })
            .selectOption(codes.map((code) => accounts[side][code]));
          await page
            .getByLabel(`Independent ${name} account count`, { exact: true })
            .fill(metric === "inventory" ? "21" : "1");
          const amount =
            metric === "inventory"
              ? side === "current"
                ? "126"
                : "105"
              : metric === "revenue"
                ? side === "current"
                  ? "1000"
                  : "800"
                : side === "current"
                  ? "800"
                  : "600";
          await page
            .getByLabel(`Independent ${name} amount`, { exact: true })
            .fill(amount);
          await page
            .getByLabel(`${name} account scope assessment`, { exact: true })
            .fill(
              "SYNTHETIC independently assessed complete account selection, signs and measurement basis",
            );
        }
      }
      await page
        .getByLabel("Stock/GP periods assessed comparable", { exact: true })
        .selectOption("yes");
      await page
        .getByLabel("Stock/GP display rounding", { exact: true })
        .selectOption("HALF_UP");
      const title = `SYNTHETIC ${country} stock and GP comparison`;
      for (const [label, value] of [
        [
          "Stock/GP period comparability assessment",
          "SYNTHETIC comparable annual periods and consistent explicitly selected accounting scope",
        ],
        ["Stock-change review threshold (%)", "20"],
        ["Gross-profit margin change threshold (percentage points)", "5"],
        ["Stock/GP display decimal places", "2"],
        ["Stock/GP review title", title],
        [
          "Stock/GP source rationale",
          "SYNTHETIC independent source controls; opening P&L balances excluded from period movements",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const submitted = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/${prefix}/inventory-performance`) &&
          response.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Prepare stock and GP review",
          exact: true,
        })
        .click();
      const response = await submitted;
      expect(response.status(), await response.text()).toBe(201);
      const result: WorkflowEvent = await response.json();
      expect(result.body.blocked).toBe(false);
      expect(result.body.rows[0]).toMatchObject({
        current_display: "126.00",
        prior_display: "105.00",
        change_display: "20.00",
        currency,
      });
      expect(result.body.rows[4]).toMatchObject({
        current_display: "20.00",
        prior_display: "25.00",
        change_display: "-5.00",
      });
      await expect(
        page.getByLabel("Saved source or result", { exact: true }),
      ).toHaveValue(result.id);
      await expect(
        page.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      await page
        .getByLabel("Review / exception rationale", { exact: true })
        .fill("SYNTHETIC author must not approve own account selection output");
      const self = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
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
          "SYNTHETIC independent selected accounts, totals, period comparability and GP arithmetic review",
        );
      const review = reviewer.waitForResponse(
        (r) =>
          r.url().endsWith(`/events/${result.id}/review`) &&
          r.request().method() === "POST",
      );
      await reviewer
        .getByRole("button", { name: "Independent approval", exact: true })
        .click();
      const reviewed = await review;
      expect(reviewed.status(), await reviewed.text()).toBe(201);
      const approved: WorkflowEvent = await reviewed.json();
      await expect(
        reviewer.getByLabel("Saved source or result", { exact: true }),
      ).toHaveValue(approved.id);
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      await expect(
        reviewer.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeEnabled();
      const panel = reviewer.getByRole("region", {
        name: "Stock and gross-profit source evidence",
        exact: true,
      });
      await panel
        .getByText("Stock/GP independent controls · 6", { exact: true })
        .click();
      await panel
        .getByText("Stock/GP account lineage · 46", { exact: true })
        .click();
      for (let index = 0; index < 2; index++) {
        const loaded = reviewer.waitForResponse(
          (r) =>
            r.url().includes(`events/${approved.id}?`) &&
            r
              .url()
              .includes(`inventory_performance_offset=${(index + 1) * 20}`),
        );
        await panel
          .getByRole("button", {
            name: "Next stock/GP account links",
            exact: true,
          })
          .click();
        expect((await loaded).status()).toBe(200);
      }
      const lineage = panel.getByRole("table", {
        name: "Stock/GP account lineage",
        exact: true,
      });
      await expect(
        lineage.getByRole("cell", { name: "INV-20", exact: true }),
      ).toBeVisible();
      await expect(lineage.getByRole("row")).toHaveCount(7);
      await expect(
        panel.getByRole("button", {
          name: "Next stock/GP account links",
          exact: true,
        }),
      ).toBeDisabled();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/${country}-stock-GP-reviewed-lineage.png`,
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
            "assert w['Stock GP account lineage'].max_row == 47",
            "assert w['Stock GP source controls'].max_row == 7",
            "r=list(w['Rows'].values());gp=r[-1];assert str(gp[r[0].index('change_display')])=='-5.00'",
          ].join("\n"),
        ],
        { input: readFileSync(downloaded!), timeout: 15000 },
      );
      const retained = await get(
        `${prefix}/events/${approved.id}?inventory_performance_limit=100`,
      );
      await commit("prior", prior.id);
      const historical = await get(
        `${prefix}/events/${approved.id}?inventory_performance_limit=100`,
      );
      expect(historical.freshness).toBe("STALE");
      expect(historical.body).toEqual(retained.body);
      expect(historical.version).toBe(retained.version);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${approved.id}`,
      );
      await expect(
        reviewer.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/${country}-stock-GP-prior-superseded-stale.png`,
        });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

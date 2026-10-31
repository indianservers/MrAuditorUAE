import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

type Paper = {
  id: string;
  version: number;
  status: string;
  body: Record<string, unknown>;
};
type Package = {
  eid: string;
  profile: Paper;
  note: Paper;
  financial: { id: string };
  ready: (kind: string, body: unknown) => Promise<Paper>;
};

async function login(page: Page, email: string) {
  const password = process.env.AUDITOS_SMOKE_PASSWORD;
  if (!password || !email)
    throw new Error("Explicit isolated synthetic identities required");
  await page.goto("/login");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

test("prior reported group comparatives retain separate review, original FX, complete export and recursive staleness", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const ids = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(ids.synthetic_only).toBe(true);
  const screenshots = "test-results/country-reports";
  mkdirSync(screenshots, { recursive: true });
  const contexts = await Promise.all([
    browser.newContext({ baseURL: process.env.AUDITOS_E2E_ORIGIN }),
    browser.newContext({ baseURL: process.env.AUDITOS_E2E_ORIGIN }),
  ]);
  const manager = await contexts[0].newPage();
  const partner = await contexts[1].newPage();
  const errors: string[] = [];
  for (const actor of [page, manager, partner]) {
    actor.setDefaultTimeout(20000);
    actor.on("pageerror", (e) => errors.push(e.message));
  }
  await page.setViewportSize({ width: 1800, height: 1500 });
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    await login(manager, ids.manager_email);
    await login(partner, ids.partner_email);
    for (const actor of [page, manager, partner]) {
      await actor.goto("/settings/countries");
      await actor
        .getByRole("combobox", { name: "Working country", exact: true })
        .selectOption("AE");
      await expect(
        actor.getByRole("combobox", { name: "Working country", exact: true }),
      ).toHaveValue("AE");
    }
    const headers = {
      "X-Tenant-ID": ids.tenant_id,
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
    const client = await post(page.request, "clients", {
      code: `GROUP-COMP-${Date.now()}`,
      name: "SYNTHETIC unchanged group comparative client",
    });
    const entities = [];
    for (const index of [0, 1])
      entities.push(
        await post(page.request, "entities", {
          client_id: client.id,
          name: `SYNTHETIC group comparative ${index === 0 ? "parent" : "subsidiary"}`,
          country: "AE",
          jurisdiction: "Synthetic",
          functional_currency: index === 0 ? "AED" : "USD",
          presentation_currency: index === 0 ? "AED" : "USD",
        }),
      );
    const packages: Record<number, Package[]> = { 2025: [], 2026: [] };
    for (const year of [2025, 2026]) {
      for (const index of [0, 1]) {
        const entity = entities[index];
        const scale = year === 2026 && index === 1 ? 2 : 1;
        const period = await post(page.request, "financial-periods", {
          entity_id: entity.id,
          start_date: `${year}-01-01`,
          end_date: `${year}-12-31`,
        });
        const eng = await post(page.request, "engagements", {
          entity_id: entity.id,
          period_id: period.id,
          name: `SYNTHETIC group ${year} member ${index}`,
          engagement_type: "External Audit",
        });
        const eid = eng.id;
        const audit = `engagements/${eid}/audit`;
        for (const role of ["manager", "partner"])
          await post(
            page.request,
            `${audit}/team`,
            {
              membership_id: ids[`${role}_membership_id`],
              role_id: ids[`${role}_role_id`],
            },
            200,
          );
        async function action(
          request: APIRequestContext,
          record: Paper,
          value: string,
        ) {
          return post(
            request,
            `${audit}/records/${record.id}/actions`,
            {
              version: record.version,
              action: value,
              comments:
                "SYNTHETIC independent reporting review; no client or professional qualification",
            },
            200,
          ) as Promise<Paper>;
        }
        async function ready(kind: string, body: unknown) {
          let record = (await post(page.request, `${audit}/ifrs-${kind}`, {
            reference: `SYN-${kind}-${year}-${index}-${Date.now()}`,
            title: `SYNTHETIC ${kind} ${year} member ${index}`,
            body,
          })) as Paper;
          record = await action(page.request, record, "submit");
          const self = await page.request.post(
            `/api/backend/${audit}/records/${record.id}/actions`,
            {
              headers,
              data: {
                version: record.version,
                action: "approve",
                comments:
                  "SYNTHETIC direct self-approval must remain forbidden",
              },
            },
          );
          expect(self.status(), await self.text()).toBe(403);
          record = await action(manager.request, record, "approve");
          if (kind === "financials")
            record = await action(partner.request, record, "approve");
          expect(record.status).toBe("APPROVED");
          return record;
        }
        const rows =
          [
            "Account Code,Account Name,Journal Number,Posting Date,Debit,Credit,Source ID,Opening,Manual,Narration",
            `100,Cash,OPEN,${year}-01-01,${100 * scale},0,L1,true,false,Synthetic opening`,
            `300,Equity,OPEN,${year}-01-01,0,${100 * scale},L2,true,false,Synthetic opening`,
            `100,Cash,S1,${year}-06-01,${50 * scale},0,L3,false,false,Synthetic sale`,
            `400,Revenue,S1,${year}-06-01,0,${50 * scale},L4,false,false,Synthetic sale`,
            `500,Expense,E1,${year}-06-01,${20 * scale},0,L5,false,false,Synthetic expense`,
            `100,Cash,E1,${year}-06-01,0,${20 * scale},L6,false,false,Synthetic expense`,
          ].join("\n") + "\n";
        const uploaded = await page.request.post(
          "/api/backend/accounting/imports",
          {
            headers,
            multipart: {
              options: JSON.stringify({
                client_id: client.id,
                entity_id: entity.id,
                period_id: period.id,
                currency: index === 0 ? "AED" : "USD",
                source_complete: true,
                expected_rows: 6,
                expected_debit: String(170 * scale),
                expected_credit: String(170 * scale),
              }),
              file: {
                name: `SYNTHETIC-group-${year}-${index}.csv`,
                mimeType: "text/csv",
                buffer: Buffer.from(rows),
              },
            },
          },
        );
        expect(uploaded.status(), await uploaded.text()).toBe(201);
        const batch = await uploaded.json();
        expect(
          (
            await post(
              page.request,
              `accounting/imports/${batch.id}/validate`,
              {},
              200,
            )
          ).status,
        ).toBe("validated");
        await post(
          page.request,
          `accounting/imports/${batch.id}/commit`,
          {},
          200,
        );
        const detail = await get(`accounting/imports/${batch.id}`);
        const profile = await ready("profile", {
          snapshot_id: detail.snapshot_id,
          presentation_currency: index === 0 ? "AED" : "USD",
          technical_validation:
            "SYNTHETIC independently reviewed corporate reporting basis",
        });
        await ready("mapping", {
          profile_id: profile.id,
          accounts: [
            ["100", "Cash", "assets"],
            ["300", "Capital", "equity"],
            ["400", "Revenue", "income"],
            ["500", "Expense", "expenses"],
          ].map(([code, label, section]) => ({
            account_code: code,
            allocations: [
              {
                line_code: code,
                label,
                section,
                note: "N1",
                is_cash: code === "100",
              },
            ],
          })),
          rationale: "SYNTHETIC independently classified source accounts",
        });
        await ready("cash-flow", {
          profile_id: profile.id,
          method: "indirect",
          policy: "SYNTHETIC cash policy",
          movement_schedule_source:
            "SYNTHETIC complete ledger without non-cash movements",
        });
        const note = await ready("note", {
          profile_id: profile.id,
          note_reference: "N1",
          text: "SYNTHETIC independently reviewed source disclosure; no actual client qualification",
          linked_line_codes: ["100", "300", "400", "500"],
        });
        for (const category of [
          "presentation",
          "policies",
          "judgments",
          "events_after_reporting",
          "going_concern",
          "N1",
        ])
          await ready("disclosure", {
            profile_id: profile.id,
            standard: "IAS 1",
            category,
            applicability: "applicable",
            rationale: "SYNTHETIC independent scope assessment",
            note_id: note.id,
          });
        const financial = await post(
          page.request,
          `ifrs/engagements/${eid}/financial-statements/${profile.id}`,
          null,
        );
        expect(financial.results.validation.ready).toBe(true);
        await ready("financials", {
          run_id: financial.id,
          release_rationale: "SYNTHETIC independently reviewed member package",
        });
        packages[year].push({ eid, profile, note, financial, ready });
      }
    }
    const groups: Record<
      number,
      { id: string; sha256: string; results: Record<string, unknown> }
    > = {};
    const assumptions: Record<number, Record<string, unknown>> = {};
    for (const year of [2025, 2026]) {
      const members = packages[year].map((member, index) => ({
        engagement_id: member.eid,
        financial_run_id: member.financial.id,
        ownership: index === 0 ? "1" : "0.8",
        power: true,
        variable_returns: true,
        ability_to_affect_returns: true,
        control_rationale: "SYNTHETIC unchanged complete-period group control",
        closing_rate: index === 0 ? "1" : year === 2025 ? "2" : "3",
        average_rate: index === 0 ? "1" : year === 2025 ? "1.5" : "2.5",
        historical_rate: "1",
        opening_rate: "1",
        rate_source: "SYNTHETIC independent dated source rates",
        rate_date: `${year}-12-31`,
        control_effective_from: "2025-01-01",
        acquisition_type: index === 0 ? "parent" : "business_combination",
        accounting_policy: "SYNTHETIC unchanged group policy",
      }));
      assumptions[year] = {
        presentation_currency: "AED",
        members,
        intercompany_nil_assessment: {
          member_engagement_ids: members.map((m) => m.engagement_id),
          period_start: `${year}-01-01`,
          period_end: `${year}-12-31`,
          rationale:
            "SYNTHETIC full member reciprocal population independently assessed as nil",
          source_record_ids: packages[year].map((p) => p.note.id),
        },
      };
      const source = await packages[year][0].ready(
        "consolidation",
        assumptions[year],
      );
      groups[year] = await post(
        page.request,
        `ifrs/engagements/${packages[year][0].eid}/consolidation/${source.id}`,
        null,
      );
    }
    const current = packages[2026][0];
    const prior = packages[2025][0];
    const source = await current.ready("consolidation", {
      ...assumptions[2026],
      comparative_source: {
        engagement_id: prior.eid,
        run_id: groups[2025].id,
        basis:
          "SYNTHETIC unchanged membership, ownership and chart; retain original prior reported amounts without restatement",
      },
    });
    await page.goto(`/ifrs/${current.eid}/consolidation`);
    await page
      .getByRole("combobox", { name: "Approved assumptions", exact: true })
      .selectOption(source.id);
    const responsePromise = page.waitForResponse(
      (r) =>
        r
          .url()
          .endsWith(
            `/ifrs/engagements/${current.eid}/consolidation/${source.id}`,
          ) && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Calculate approved inputs", exact: true })
      .click();
    const response = await responsePromise;
    expect(response.status(), await response.text()).toBe(201);
    const result = await response.json();
    expect(result.results.validation.ready).toBe(false);
    expect(result.results.intercompany_population.status).toBe(
      "EXPLICIT_RETAINED_NIL_ASSESSMENT",
    );
    const cash = result.results.lines.find(
      (row: { line_code: string }) => row.line_code === "100",
    );
    expect(Number(cash.current)).toBe(910);
    expect(Number(cash.comparative)).toBe(390);
    const region = page.getByRole("region", {
      name: "Reporting calculations",
      exact: true,
    });
    const comparative = page.getByRole("region", {
      name: "Prior group comparative source",
      exact: true,
    });
    await expect(
      comparative.getByRole("heading", {
        name: "Prior reported group figures",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      region.getByRole("gridcell", { name: "910.00", exact: true }),
    ).toBeVisible();
    await expect(
      region.getByRole("gridcell", { name: "390.00", exact: true }),
    ).toBeVisible();
    const comparativeBounds = await comparative.boundingBox();
    expect(comparativeBounds).not.toBeNull();
    for (const value of await comparative.locator("dd").all()) {
      const bounds = await value.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(
        comparativeBounds!.x + comparativeBounds!.width + 1,
      );
      expect(
        await value.evaluate((element) => element.scrollWidth),
      ).toBeLessThanOrEqual(Math.ceil(bounds!.width) + 1);
    }
    await comparative.screenshot({
      path: `${screenshots}/AE-group-comparative-source.png`,
    });
    await region.getByRole("gridcell", { name: "Cash", exact: true }).click();
    const lineage = page.getByRole("region", {
      name: "Group financial source lineage",
      exact: true,
    });
    const currentSources = lineage.getByRole("table", {
      name: "Current source accounts",
      exact: true,
    });
    const priorSources = lineage.getByRole("table", {
      name: "Comparative source accounts",
      exact: true,
    });
    await expect(currentSources.getByRole("row")).toHaveCount(3);
    await expect(priorSources.getByRole("row")).toHaveCount(3);
    await expect(
      currentSources.getByRole("cell", { name: "3", exact: true }),
    ).toBeVisible();
    await expect(
      priorSources.getByRole("cell", { name: "2", exact: true }),
    ).toBeVisible();
    // Visibility alone permits content overflowing a shrunken flex panel.
    // Both full tables and the final paging controls must fit its own bounds.
    const panelBounds = await lineage.boundingBox();
    expect(panelBounds).not.toBeNull();
    for (const content of [
      currentSources,
      priorSources,
      lineage.getByRole("button", {
        name: "Next comparative source accounts",
        exact: true,
      }),
    ]) {
      const bounds = await content.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.y).toBeGreaterThanOrEqual(panelBounds!.y);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(
        panelBounds!.y + panelBounds!.height,
      );
    }
    await lineage.screenshot({
      path: `${screenshots}/AE-group-comparative-source-accounts.png`,
    });
    await page.locator(".ifrs-designer").screenshot({
      path: `${screenshots}/AE-group-comparative-original-lineage.png`,
    });
    const downloading = page.waitForEvent("download");
    await region
      .getByRole("button", { name: "Export XLSX", exact: true })
      .click();
    const download = await downloading;
    expect(download.suggestedFilename()).toContain("draft");
    const path = await download.path();
    expect(path).not.toBeNull();
    execFileSync(
      process.platform === "win32"
        ? "../backend/.venv/Scripts/python.exe"
        : "../backend/.venv/bin/python",
      [
        "-c",
        "import io,sys; from openpyxl import load_workbook; w=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True); rows=list(w['Financial package'].values); assert any(r[0]=='Cash' and r[2]=='390.00' for r in rows); assert any(r[0]=='PRIOR GROUP COMPARATIVE SOURCE' for r in rows); assert 'Immutable run' in w.sheetnames",
      ],
      { input: readFileSync(path!), timeout: 15000 },
    );
    await prior.ready("note", {
      profile_id: prior.profile.id,
      note_reference: "SYN-NEW-PRIOR",
      text: "SYNTHETIC newly approved prior-period disclosure requires a new member reporting package",
      linked_line_codes: ["100"],
    });
    await region
      .getByRole("button", {
        name: "Validate current dependencies",
        exact: true,
      })
      .click();
    await expect(region.getByText("STALE", { exact: true })).toBeVisible();
    const historical = await get(
      `ifrs/engagements/${current.eid}/runs/${result.id}`,
    );
    expect(historical.dependencies_current).toBe(false);
    expect(historical.results).toEqual(result.results);
    await region.screenshot({
      path: `${screenshots}/AE-group-comparative-prior-disclosure-stale.png`,
    });
    const stale = await page.request.post(
      `/api/backend/ifrs/engagements/${current.eid}/consolidation/${source.id}`,
      { headers, data: null },
    );
    expect(stale.status()).toBe(409);
    // Exercise the existing stock and aggregate benefit engines through their
    // previously disabled workspaces, after completing the group assertions.
    const schedules: [string, Record<string, unknown>][] = [
      [
        "inventory",
        {
          profile_id: current.profile.id,
          period_start: "2026-01-01",
          period_end: "2026-12-31",
          method: "fifo",
          policy_version: "SYNTHETIC-purchased-stock/1",
          items: [
            {
              reference: "SYNTHETIC-stock-site",
              uom: "each",
              location: "SYNTHETIC-site",
              ownership: "owned",
              opening_quantity: "10",
              opening_unit_cost: "10",
              receipts: [
                {
                  reference: "SYNTHETIC-receipt",
                  date: "2026-02-01",
                  quantity: "10",
                  unit_cost: "20",
                  landed_cost: "20",
                  evidence: "SYNTHETIC invoice and freight",
                },
              ],
              issues: [
                {
                  reference: "SYNTHETIC-dispatch",
                  date: "2026-03-01",
                  quantity: "12",
                  evidence: "SYNTHETIC dispatch",
                },
              ],
              expected_closing_quantity: "8",
              selling_price: "25",
              completion_cost: "2",
              selling_cost: "3",
              nrv_evidence:
                "SYNTHETIC separately assessed price, completion and selling costs; no actual stock existence or condition assurance",
            },
          ],
        },
      ],
      [
        "employee-benefits",
        {
          profile_id: current.profile.id,
          policy_version: "SYNTHETIC-aggregate-benefits/1",
          employment_framework: "uae_mainland",
          framework_assessment:
            "SYNTHETIC explicitly assessed employment scope; no statutory or professional qualification",
          scheme: "defined_benefit",
          measurement_source:
            "SYNTHETIC supplied expert figures; no actuarial valuation is performed",
          actuarial_report_reference: "SYNTHETIC expert report",
          opening_obligation: "100",
          current_service_cost: "20",
          net_interest: "5",
          remeasurement_oci: "7",
          settlements: "12",
          closing_ledger_provision: "120",
          payroll_expense: "1000",
          opening_payroll_payable: "100",
          payroll_deductions: "50",
          confirmed_bank_payments: "900",
          closing_payroll_ledger_payable: "160",
          leave_bonus_accrual: "10",
        },
      ],
    ];
    for (const [kind, body] of schedules) {
      const approved = await current.ready(kind, body);
      // Put the approved input beyond the first 50-record page.
      for (let i = 0; i < 55; i++)
        await post(
          page.request,
          `engagements/${current.eid}/audit/ifrs-${kind}`,
          {
            reference: `SYNTHETIC-unapproved-${kind}-${i}-${Date.now()}`,
            title: `SYNTHETIC unapproved ${kind} pagination record ${i}`,
            body,
          },
        );
      await page.goto(`/ifrs/${current.eid}/${kind}`);
      const reporting = page.getByRole("region", {
        name: "Reporting calculations",
        exact: true,
      });
      const choice = reporting.getByRole("combobox", {
        name: "Approved assumptions",
        exact: true,
      });
      await expect(
        choice.locator(`option[value="${approved.id}"]`),
      ).toHaveCount(0);
      await reporting
        .getByRole("button", { name: "Next approved assumptions", exact: true })
        .click();
      await reporting
        .getByRole("combobox", { name: "Approved assumptions", exact: true })
        .selectOption(approved.id);
      await reporting
        .getByRole("button", {
          name: "Previous approved assumptions",
          exact: true,
        })
        .click();
      await expect(choice).toHaveValue(approved.id);
      const pending = page.waitForResponse(
        (r) =>
          r
            .url()
            .endsWith(
              `/ifrs/engagements/${current.eid}/calculate/${approved.id}`,
            ) && r.request().method() === "POST",
      );
      await reporting
        .getByRole("button", { name: "Calculate approved inputs", exact: true })
        .click();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(201);
      const schedule = await response.json();
      expect(schedule.kind).toBe(kind);
      expect(schedule.results.issues).toEqual([]);
      expect(schedule.results.execution.journal_state).toBe("NOT_POSTED");
      if (kind === "inventory") {
        expect(schedule.results.closing_carrying).toBe("160.00000000");
        expect(schedule.results.schedule[0].closing_cost).toBe("176.00000000");
        expect(schedule.results.schedule[0].closing_write_down).toBe(
          "16.00000000",
        );
      } else {
        expect(schedule.results.obligation_rollforward.closing).toBe("120");
        expect(schedule.results.payroll_bridge.closing).toBe("160");
        expect(schedule.results.payment_state).toBe(
          "NO_PAYMENT_INSTRUCTION_CREATED",
        );
      }
      await expect(
        reporting.getByText("CURRENT", { exact: true }),
      ).toBeVisible();
      const scheduleResults = reporting.getByRole("region", {
        name:
          kind === "inventory"
            ? "Inventory costing results"
            : "Employee benefit accounting results",
        exact: true,
      });
      if (kind === "inventory") {
        await expect(scheduleResults).toContainText("160.00000000");
        const itemTable = scheduleResults.getByRole("table", {
          name: "Inventory item costing",
          exact: true,
        });
        await expect(itemTable.getByRole("row")).toHaveCount(2);
        await itemTable
          .getByRole("cell", { name: "176.00000000", exact: true })
          .scrollIntoViewIfNeeded();
        const costBounds = await itemTable
          .getByRole("cell", { name: "176.00000000", exact: true })
          .boundingBox();
        expect(costBounds).not.toBeNull();
        expect(costBounds!.width).toBeGreaterThanOrEqual(239);
      } else {
        const obligation = scheduleResults.getByRole("region", {
          name: "Benefit obligation rollforward",
          exact: true,
        });
        await expect(obligation.getByText("120", { exact: true })).toHaveCount(
          2,
        );
        await expect(
          obligation.getByText("120", { exact: true }).first(),
        ).toBeVisible();
        await expect(
          scheduleResults.getByRole("region", {
            name: "Payroll accounting bridge",
            exact: true,
          }),
        ).toContainText("160");
      }
      await scheduleResults.screenshot({
        path: `${screenshots}/AE-${kind}-approved-calculation.png`,
      });
      const exportPending = page.waitForEvent("download");
      await reporting
        .getByRole("button", { name: "Export JSON", exact: true })
        .click();
      const exportedPath = await (await exportPending).path();
      expect(exportedPath).not.toBeNull();
      const exported = JSON.parse(readFileSync(exportedPath!, "utf8"));
      expect(exported.id).toBe(schedule.id);
      expect(exported.released).toBe(false);
      expect(exported.results).toEqual(schedule.results);
    }
    const identified = await current.ready("inventory", {
      profile_id: current.profile.id,
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      method: "specific_identification",
      policy_version: "SYNTHETIC-individual-machines/1",
      items: [100, 300].map((cost, index) => ({
        reference: `SYNTHETIC-machine-${index}`,
        sku: "SYNTHETIC-non-interchangeable-machine",
        uom: "each",
        location: "SYNTHETIC-Dubai",
        ownership: "owned",
        identification_reference: `SYNTHETIC-serial-${index}`,
        identification_assessment:
          "SYNTHETIC individually tracked non-interchangeable machine; professional eligibility remains unqualified",
        opening_cost_evidence: `SYNTHETIC-invoice-${index}`,
        opening_quantity: "1",
        opening_unit_cost: String(cost),
        issues:
          index === 1
            ? [
                {
                  reference: "SYNTHETIC-selected-dispatch",
                  date: "2026-03-01",
                  quantity: "1",
                  evidence: "SYNTHETIC serial-1 dispatch acknowledgement",
                },
              ]
            : [],
        expected_closing_quantity: index === 1 ? "0" : "1",
        selling_price: "500",
        nrv_evidence: "SYNTHETIC individual-unit sale quotation",
      })),
    });
    await page.goto(`/ifrs/${current.eid}/inventory`);
    const identifiedRegion = page.getByRole("region", {
      name: "Reporting calculations",
      exact: true,
    });
    await identifiedRegion
      .getByRole("combobox", { name: "Approved assumptions", exact: true })
      .selectOption(identified.id);
    const identifiedPending = page.waitForResponse(
      (r) =>
        r
          .url()
          .endsWith(
            `/ifrs/engagements/${current.eid}/calculate/${identified.id}`,
          ) && r.request().method() === "POST",
    );
    await identifiedRegion
      .getByRole("button", { name: "Calculate approved inputs", exact: true })
      .click();
    const identifiedResponse = await identifiedPending;
    expect(identifiedResponse.status(), await identifiedResponse.text()).toBe(
      201,
    );
    const identifiedRun = await identifiedResponse.json();
    expect(identifiedRun.results.closing_carrying).toBe("100.00000000");
    expect(identifiedRun.results.schedule[1].issue_cost).toBe("300.00000000");
    const identifiedResults = identifiedRegion.getByRole("region", {
      name: "Inventory costing results",
      exact: true,
    });
    const identifiedTable = identifiedResults.getByRole("table", {
      name: "Inventory item costing",
      exact: true,
    });
    await expect(identifiedTable.getByRole("row")).toHaveCount(3);
    await identifiedTable
      .getByRole("cell", { name: "SYNTHETIC-serial-1", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      identifiedTable.getByRole("cell", {
        name: "SYNTHETIC-serial-1",
        exact: true,
      }),
    ).toBeVisible();
    await identifiedResults.screenshot({
      path: `${screenshots}/AE-inventory-specific-identification.png`,
    });
    const projectLot = await current.ready("inventory", {
      profile_id: current.profile.id,
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      method: "specific_identification",
      policy_version: "SYNTHETIC-segregated-project/1",
      items: [
        {
          reference: "SYNTHETIC-project-A",
          sku: "SYNTHETIC-project-component",
          uom: "each",
          location: "SYNTHETIC-Dubai",
          ownership: "owned",
          identification_reference: "SYNTHETIC-project-A",
          identification_basis: "segregated_project_lot",
          identification_assessment:
            "SYNTHETIC independently assessed non-interchangeable purchased project lot",
          opening_quantity: "5",
          opening_unit_cost: "0",
          opening_layers: [
            {
              reference: "A",
              quantity: "2",
              unit_cost: "10",
              evidence: "SYNTHETIC invoice A",
            },
            {
              reference: "B",
              quantity: "3",
              unit_cost: "30",
              evidence: "SYNTHETIC invoice B",
            },
          ],
          receipts: [
            {
              reference: "C",
              date: "2026-02-01",
              quantity: "4",
              unit_cost: "50",
              landed_cost: "4",
              evidence: "SYNTHETIC invoice C and freight",
            },
          ],
          issues: [
            {
              reference: "I",
              date: "2026-03-01",
              quantity: "3",
              evidence: "SYNTHETIC physical issue",
              cost_allocations: [
                {
                  layer_reference: "B",
                  quantity: "2",
                  evidence: "SYNTHETIC attribution B",
                },
                {
                  layer_reference: "C",
                  quantity: "1",
                  evidence: "SYNTHETIC attribution C",
                },
              ],
            },
          ],
          expected_closing_quantity: "6",
          selling_price: "500",
          nrv_evidence: "SYNTHETIC separately assessed project lot NRV",
        },
      ],
    });
    await page.goto(`/ifrs/${current.eid}/inventory`);
    const projectRegion = page.getByRole("region", {
      name: "Reporting calculations",
      exact: true,
    });
    await projectRegion
      .getByRole("combobox", { name: "Approved assumptions", exact: true })
      .selectOption(projectLot.id);
    const projectPending = page.waitForResponse(
      (r) =>
        r
          .url()
          .endsWith(
            `/ifrs/engagements/${current.eid}/calculate/${projectLot.id}`,
          ) && r.request().method() === "POST",
    );
    await projectRegion
      .getByRole("button", { name: "Calculate approved inputs", exact: true })
      .click();
    const projectResponse = await projectPending;
    expect(projectResponse.status(), await projectResponse.text()).toBe(201);
    const projectRun = await projectResponse.json();
    expect(projectRun.results.closing_carrying).toBe("203.00000000");
    expect(projectRun.results.schedule[0].issue_cost).toBe("111.00000000");
    const projectResults = projectRegion.getByRole("region", {
      name: "Inventory costing results",
      exact: true,
    });
    await projectResults
      .getByText("Identified project cost layers (3)", { exact: true })
      .click();
    const projectLayers = projectResults.getByRole("table", {
      name: "Identified project cost layers",
      exact: true,
    });
    await expect(projectLayers.getByRole("row")).toHaveCount(4);
    await projectResults
      .getByRole("region", {
        name: "Identified project cost layers",
        exact: true,
      })
      .screenshot({
        path: `${screenshots}/AE-inventory-project-cost-layers.png`,
      });
    await projectResults
      .getByText("Identified project issue allocations (2)", { exact: true })
      .click();
    const projectAllocations = projectResults.getByRole("table", {
      name: "Identified project issue allocations",
      exact: true,
    });
    await expect(projectAllocations.getByRole("row")).toHaveCount(3);
    await projectAllocations
      .getByRole("cell", { name: "SYNTHETIC attribution C", exact: true })
      .scrollIntoViewIfNeeded();
    await expect(
      projectAllocations.getByRole("cell", {
        name: "SYNTHETIC attribution C",
        exact: true,
      }),
    ).toBeVisible();
    await projectResults
      .getByRole("region", {
        name: "Identified project issue allocations",
        exact: true,
      })
      .screenshot({
        path: `${screenshots}/AE-inventory-project-issue-allocations.png`,
      });
    expect(errors).toEqual([]);
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

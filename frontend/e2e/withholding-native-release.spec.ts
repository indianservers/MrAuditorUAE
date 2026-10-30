import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { runWithholdingPANBrowserWorkflow } from "./withholding-pan-browser-workflow";
import { runSalaryAnnualBrowserWorkflow } from "./salary-annual-browser-workflow";
import {
  makeWorkflowHarness,
  type WorkflowEvent,
} from "./msme-browser-workflow";

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

test("India historical native samples and explicit dated Form 138/140/143/144 fixtures, controlled forms, full lineage and crosswalk staleness", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  const screenshots = "test-results/country-reports";
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 2200, height: 1600 },
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
    for (const actor of [page, reviewer]) {
      await actor.goto("/settings/countries");
      await actor
        .getByRole("combobox", { name: "Working country", exact: true })
        .selectOption("IN");
    }
    const headers = {
      "X-Tenant-ID": identities.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    };
    async function create(path: string, data: unknown, status = 201) {
      const response = await page.request.post(`/api/backend/${path}`, {
        headers,
        data,
      });
      expect(response.status(), await response.text()).toBe(status);
      return response.json();
    }
    const client = await create("clients", {
      code: `NWH-${Date.now()}`,
      name: "SYNTHETIC historical native withholding client",
    });
    const entity = await create("entities", {
      client_id: client.id,
      name: "SYNTHETIC India historical statement entity",
      country: "IN",
      jurisdiction: "India",
      functional_currency: "INR",
      presentation_currency: "INR",
    });
    const period = await create("financial-periods", {
      entity_id: entity.id,
      start_date: "2020-04-01",
      end_date: "2021-03-31",
    });
    const engagement = await create("engagements", {
      entity_id: entity.id,
      period_id: period.id,
      name: "SYNTHETIC historical native statement review",
      engagement_type: "External Audit",
    });
    const eid = engagement.id;
    await create(
      `engagements/${eid}/audit/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    const { prefix, post, evidence, upload, completed } = makeWorkflowHarness(
      page,
      eid,
      identities.tenant_id,
    );
    for (const form of [
      "26Q",
      "27EQ",
      "27Q",
      "143",
      "138",
      "140",
      "144",
      "24Q",
      "24Q-Q4",
    ] as const) {
      const isNumbered = ["138", "140", "143", "144"].includes(form);
      const isDeduction = ["140", "144"].includes(form);
      const bsr =
        form === "140"
          ? "3000012"
          : form === "144"
            ? "4000013"
            : form.startsWith("24Q")
              ? "0000412"
              : form === "138"
                ? "2000090"
                : form === "143"
                  ? "5000032"
                  : form === "26Q"
                    ? "0000809"
                    : form === "27Q"
                      ? "0000525"
                      : "0000897";
      const count =
        form.startsWith("24Q") || isDeduction
          ? 1
          : form === "138"
            ? 2
            : form === "143"
              ? 1
              : form === "26Q"
                ? 4
                : form === "27Q"
                  ? 2
                  : 10;
      const month =
        form === "24Q-Q4"
          ? "2025-02"
          : form.startsWith("24Q")
            ? "2018-12"
            : isNumbered
              ? "2026-05"
              : form === "26Q"
                ? "2020-04"
                : form === "27Q"
                  ? "2019-12"
                  : "2020-10";
      const total =
        form === "140"
          ? "900"
          : form === "144"
            ? "2000"
            : form.startsWith("24Q")
              ? "1000"
              : form === "138"
                ? "4000"
                : form === "143"
                  ? "700"
                  : form === "26Q"
                    ? "1900"
                    : form === "27Q"
                      ? "166000"
                      : "1000";
      const gross =
        form === "140"
          ? "11200"
          : form === "144"
            ? "24000"
            : form.startsWith("24Q")
              ? "1000"
              : form === "138"
                ? "24100"
                : form === "143"
                  ? "213000"
                  : form === "26Q"
                    ? "100000"
                    : form === "27Q"
                      ? "20000000"
                      : "10000";
      const groups = Array.from({ length: count }, (_, i) => ({
        transaction_reference: `SYN-ASSESSMENT-${i + 1}`,
        transaction_date:
          month + (form === "140" ? "-02" : form === "27Q" ? "-10" : "-01"),
        period: month,
        rule_reference: "SYN-ASSESSED-SECTION",
        party_records: [`1/1/${i + 1}`],
      }));
      const publicOriginal = readFileSync(
        form === "24Q-Q4"
          ? "../docs/country-workflows/authority-references/protean-legacy-2025-05-27/protean-24Q-Q4-original-sample.txt"
          : form.startsWith("24Q")
            ? "../docs/country-workflows/authority-references/protean-legacy-2025-05-27/protean-24Q-Q3-original-sample.txt"
            : form === "138"
              ? "../docs/country-workflows/authority-references/form138-2026-07-22/protean-form138-original-sample.txt"
              : form === "143" || isDeduction
                ? `../docs/country-workflows/authority-references/form${form}-2026-07-22/protean-form${form}-original-sample.txt`
                : `../docs/country-workflows/authority-references/protean-legacy-2025-05-27/protean-${form}-original-sample.txt`,
      );
      let sourceBytes = publicOriginal;
      if (form === "143" || isDeduction) {
        await evidence(
          `public-issuer-${form}-incomplete-original-sample.txt`,
          publicOriginal,
        );
        expect(publicOriginal.subarray(-2).toString("ascii")).toBe("\r\n");
        const records = publicOriginal
          .subarray(0, -2)
          .toString("ascii")
          .split("\r\n")
          .map((line) => line.split("^"));
        for (const [line, field, value] of [
          [3, 17, "00001"],
          [3, 24, "1000.00"],
          [3, 25, form === "140" ? "100.00" : "1000.00"],
          [4, 18, "Y"],
        ] as const)
          records[line - 1][field - 1] = value;
        if (form === "144") records[3][32] = "1234567890";
        sourceBytes = Buffer.from(
          records.map((row) => row.join("^")).join("\r\n") + "\r\n",
          "ascii",
        );
      }
      if (form === "138") {
        await evidence(
          "public-issuer-138-conflicted-original-sample.txt",
          publicOriginal,
        );
        sourceBytes = readFileSync(
          "../docs/country-workflows/sample-inputs/SYNTHETIC-dated-form138/SYNTHETIC-explicit-completion-138.txt",
        );
      }
      if (form === "24Q-Q4") {
        await evidence(
          "unchanged-public-q4-width-conflict.txt",
          publicOriginal,
        );
        sourceBytes = readFileSync(
          "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-complete-q4.txt",
        );
      }
      const file = await evidence(
        isNumbered || form === "24Q-Q4"
          ? `SYNTHETIC-explicit-completion-${form}.txt`
          : `public-issuer-${form}-original-sample.txt`,
        sourceBytes,
      );
      const mapping = await evidence(
        `SYNTHETIC-${form}-independent-crosswalk.txt`,
        Buffer.from(
          JSON.stringify(
            {
              classification:
                "SYNTHETIC_MAPPING_NOT_CLIENT_OR_LEGAL_QUALIFICATION",
              ...(form === "24Q-Q4"
                ? {
                    annual_controls: JSON.parse(
                      readFileSync(
                        "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-annual-controls.json",
                        "utf8",
                      ),
                    ),
                  }
                : {}),
              groups,
            },
            null,
            2,
          ),
        ),
      );
      const title = `SYNTHETIC ${form} controlled regular observations`;
      await page.goto(`/intelligence/${eid}/workflow-source`);
      await page
        .getByRole("combobox", { name: "Source file format", exact: true })
        .selectOption(
          form === "24Q-Q4"
            ? "india-24q-regular-q4-v7.5"
            : form.startsWith("24Q")
              ? "india-24q-regular-q1q3-v6.3"
              : isNumbered
                ? `india-form${form}-regular-20260722-v1.1`
                : form === "26Q"
                  ? "india-26q-regular-v7.8"
                  : form === "27Q"
                    ? "india-27q-regular-v7.5"
                    : "india-27eq-regular-v6.9",
        );
      await page
        .getByRole("combobox", { name: "Clean retained evidence", exact: true })
        .selectOption(file.version.id);
      await page
        .getByRole("combobox", {
          name: "Native statement quarter",
          exact: true,
        })
        .selectOption(
          form === "24Q-Q4" ? "Q4" : form === "26Q" || isNumbered ? "Q1" : "Q3",
        );
      await page
        .getByRole("combobox", {
          name: "Assessed native source selection",
          exact: true,
        })
        .selectOption("current");
      await page
        .getByRole("combobox", {
          name: "Retained native transaction and section crosswalk",
          exact: true,
        })
        .selectOption(mapping.version.id);
      for (const [label, value] of [
        ["Schedule title", title],
        ["Expected data rows", String(count)],
        ["Independent totals by currency", `INR=${total}`],
        ["Native statement TAN", isNumbered ? "BLRF02329F" : "MUMN77777A"],
        [
          isNumbered
            ? "Native tax year (six digits)"
            : "Native financial year (six digits)",
          isNumbered
            ? "202627"
            : form === "24Q-Q4"
              ? "202425"
              : form.startsWith("24Q")
                ? "201819"
                : form === "27Q"
                  ? "201920"
                  : "202021",
        ],
        ["Native observation cutoff", "2026-10-30"],
        ["Native batch count", "1"],
        ["Native challan count", "1"],
        ["Native party count", String(count)],
        ...(isDeduction
          ? [
              ["Native tax deducted control (INR)", total],
              [
                "Native challan tax control (INR)",
                form === "140" ? "10000" : "21000",
              ],
              ["Native challan interest control (INR)", "1000"],
              [
                "Native challan fee control (INR)",
                form === "140" ? "100" : "1000",
              ],
              [
                "Native challan penalty control (INR)",
                form === "140" ? "100" : "1000",
              ],
              ["Native allocated interest control (INR)", "1000"],
              [
                "Native allocated penalty control (INR)",
                form === "140" ? "100" : "1000",
              ],
              ["Native cash withdrawal general control (INR)", "0"],
              ["Native cash withdrawal cooperative control (INR)", "0"],
            ]
          : form === "138"
            ? [
                ["Native tax deducted control (INR)", "4000"],
                ["Native challan tax control (INR)", "22000"],
                ["Native challan interest control (INR)", "1000"],
                ["Native challan fee control (INR)", "1000"],
                ["Native challan penalty control (INR)", "100"],
                ["Native allocated interest control (INR)", "1000"],
                ["Native allocated penalty control (INR)", "100"],
              ]
            : form === "143"
              ? [
                  ["Native tax collected control (INR)", "700"],
                  ["Native challan tax control (INR)", "210000"],
                  ["Native challan interest control (INR)", "1000"],
                  ["Native challan fee control (INR)", "1000"],
                  ["Native challan other control (INR)", "1000"],
                  ["Native allocated interest control (INR)", "1000"],
                  ["Native allocated other control (INR)", "1000"],
                ]
              : [
                  ["Native income tax control (INR)", total],
                  ["Native surcharge control (INR)", "0"],
                  ["Native cess control (INR)", "0"],
                ]),
        ["Native allocated deposit control (INR)", total],
        ["Native challan deposit control (INR)", gross],
        [
          "Native payment base control (INR)",
          form === "140"
            ? "1000"
            : form === "144"
              ? "2100"
              : form.startsWith("24Q")
                ? "10000"
                : form === "138"
                  ? "4200"
                  : form === "143"
                    ? "21000"
                    : form === "26Q"
                      ? "19000"
                      : form === "27Q"
                        ? "26600000"
                        : "10000",
        ],
        ["Native crosswalk groups (JSON)", JSON.stringify(groups)],
        [
          "Native source and crosswalk assessment",
          "SYNTHETIC independently counted original public example and retained mapping; no filing, bank settlement, legal or client qualification",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      if (form === "138") {
        await page
          .getByRole("combobox", {
            name: "Salary deposit-date source conflict assessment",
            exact: true,
          })
          .selectOption("DD29_EIGHT_DIGIT_DATE_PER_NUMBERED_REMARKS");
      }
      if (form === "27EQ")
        await page
          .getByLabel("Native purchase value control (INR)", { exact: true })
          .fill("10000");
      if (form === "24Q-Q4")
        await page
          .getByLabel("Annual salary populations and totals (JSON)", {
            exact: true,
          })
          .fill(
            readFileSync(
              "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-annual-controls.json",
              "utf8",
            ),
          );
      const submitted = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/${prefix}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const queued = await submitted;
      expect(queued.status(), await queued.text()).toBe(202);
      const native = await completed((await queued.json()).id);
      expect(native.body.rows).toHaveLength(count);
      expect(native.body.allowed_source_roles).toEqual(["reported"]);
      const metadata = native.body.native_metadata as Record<string, unknown>;
      expect(metadata.filing_or_acknowledgment).toBe("NOT_EVIDENCED");
      expect(metadata.bank_payment_or_tax_credit).toBe("NOT_EVIDENCED");
      expect(metadata.fvu_validation).toBe("NOT_PERFORMED");
      expect(
        (metadata.component_controls as Record<string, string>).challan_deposit,
      ).toBe(gross + ".00");
      const self = await page.request.post(
        `/api/backend/${prefix}/events/${native.id}/review`,
        {
          headers,
          data: {
            expected_version: native.version,
            action: "approve",
            comments: "SYNTHETIC self review must remain prohibited",
          },
        },
      );
      expect(self.status()).toBe(403);
      const reviewed: WorkflowEvent = await post(
        reviewer.request,
        `${prefix}/events/${native.id}/review`,
        {
          expected_version: native.version,
          action: "approve",
          comments:
            "SYNTHETIC independent complete source and crosswalk controls; no FVU or filing conclusion",
        },
      );
      await reviewer.goto(
        `/intelligence/${eid}/workflow-source?event=${reviewed.id}`,
      );
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      const links = reviewer.getByRole("table", {
        name: "Native withholding party links",
        exact: true,
      });
      await expect(links.getByRole("row")).toHaveCount(count + 1);
      await expect(
        links.getByRole("cell", { name: `1/1/${count}`, exact: true }),
      ).toBeVisible();
      const challans = reviewer.getByRole("table", {
        name: "Native withholding challans",
        exact: true,
      });
      await expect(challans.getByRole("row")).toHaveCount(2);
      await expect(
        challans.getByRole("cell", {
          name: bsr,
          exact: true,
        }),
      ).toBeVisible();
      const grossColumn = (
        await challans.getByRole("columnheader").allTextContents()
      ).findIndex((text) => text.trim() === "gross deposit");
      expect(grossColumn).toBeGreaterThanOrEqual(0);
      await expect(
        challans.getByRole("row").nth(1).getByRole("cell").nth(grossColumn),
      ).toHaveText(gross + ".00");
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/IN-${form}-native-regular-reviewed.png`,
        });
      const downloading = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const downloaded = await (await downloading).path();
      expect(downloaded).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          [
            "import io,sys",
            "from decimal import Decimal",
            "from openpyxl import load_workbook",
            "w=load_workbook(io.BytesIO(sys.stdin.buffer.read()))",
            "v=list(w['Withholding party links'].values);r=[dict(zip(v[0],x)) for x in v[1:]]",
            `assert len(r)==${count}`,
            `assert sum(Decimal(x['total_tax']) for x in r)==Decimal('${total}')`,
            `assert r[-1]['party_key']=='1/1/${count}'`,
            "c=list(w['Withholding challans'].values);assert len(c)==2",
            `assert c[1][c[0].index('bsr_or_form24g_reference')]=='${bsr}'`,
            ...(isDeduction
              ? [
                  `assert r[0]['numbered_form']=='${form}'`,
                  "assert r[0]['recorded_deposited_flag']=='Y'",
                  "assert 'income_tax' not in r[0] and 'surcharge' not in r[0] and 'cess' not in r[0]",
                  "assert r[0]['recorded_cash_withdrawal_general'] is None",
                  "assert r[0]['recorded_cash_withdrawal_cooperative'] is None",
                  `assert c[1][c[0].index('recorded_penalty')]=='${form === "140" ? "100.00" : "1000.00"}'`,
                ]
              : []),
            ...(form === "144"
              ? [
                  "assert r[0]['recorded_destination_country']=='04'",
                  "assert r[0]['recorded_numbered_rate_basis']=='B'",
                  "assert r[0]['recorded_residence_contact']=='69877877878'",
                  "assert 'recorded_section202_opt_out' not in r[0]",
                ]
              : []),
            ...(form === "143"
              ? [
                  "assert r[0]['recorded_deposited_flag']=='Y'",
                  "assert 'income_tax' not in r[0]",
                  "assert c[1][c[0].index('ddo_serial')]=='00001'",
                  "assert c[1][c[0].index('recorded_payment_mode')]=='B'",
                  "assert c[1][c[0].index('allocated_interest')]=='1000.00'",
                ]
              : []),
            ...(form === "138"
              ? [
                  "assert [x['recorded_deposit_date'] for x in r]==['2026-05-09']*2",
                  "assert 'recorded_rate' not in r[0]",
                  "assert c[1][c[0].index('recorded_penalty')]=='100.00'",
                ]
              : []),
            ...(form.startsWith("24Q")
              ? [
                  `assert r[0]['recorded_deposit_date']=='${form === "24Q-Q4" ? "2025-02-14" : "2018-12-14"}'`,
                  "assert r[0]['income_tax']=='1000.00'",
                  "assert 'recorded_rate' not in r[0]",
                ]
              : []),
            ...(form === "24Q-Q4"
              ? [
                  "assert all('Salary '+t in w.sheetnames for t in ['SD','S16','C6A','94P','P16','P6A'])",
                  "a=list(w['Salary SD'].values);assert len(a[0])==93 and a[1][22]=='-1000.00'",
                  "a=list(w['Salary P6A'].values);assert a[1][11]=='700.00' and a[1][13]=='500.00'",
                ]
              : []),
            ...(form === "27Q"
              ? [
                  "assert [x['recorded_rate_basis'] for x in r]==['B','B']",
                  "assert [x['nature_of_remittance_code'] for x in r]==['21','49']",
                  "assert [x['residence_country_code'] for x in r]==['113','113']",
                  "assert r[0]['foreign_tax_identifier'] is None",
                ]
              : []),
          ].join("\n"),
        ],
        { input: readFileSync(downloaded!), timeout: 15000 },
      );
      if (form === "24Q-Q4") {
        const annual = reviewer.getByRole("region", {
          name: "Native annual salary observations",
          exact: true,
        });
        await expect(
          annual
            .getByRole("table", {
              name: "Annual original records",
              exact: true,
            })
            .getByRole("row"),
        ).toHaveCount(7);
        for (let i = 0; i < 3; i++)
          await annual
            .getByRole("button", { name: "Next annual fields", exact: true })
            .click();
        await expect(
          annual
            .getByRole("table", {
              name: "Annual numbered source fields",
              exact: true,
            })
            .getByRole("cell", { name: "88", exact: true }),
        ).toBeVisible();
        await annual.screenshot({
          path: `${screenshots}/IN-24Q-Q4-annual-field88.png`,
        });
        await annual
          .getByRole("combobox", { name: "Annual record type", exact: true })
          .selectOption("P6A");
        await expect(
          annual
            .getByRole("table", {
              name: "Annual numbered source fields",
              exact: true,
            })
            .getByRole("cell", { name: "700.00", exact: true }),
        ).toBeVisible();
        await annual.screenshot({
          path: `${screenshots}/IN-24Q-Q4-pension-chapter-lineage.png`,
        });
      }
      if (isDeduction) {
        await expect(
          links.getByRole("columnheader", { name: "income tax", exact: true }),
        ).toHaveCount(0);
        await links.locator("..").evaluate((element) => {
          const header = Array.from(element.querySelectorAll("th")).find(
            (node) => node.textContent === "numbered form",
          );
          if (!header) throw new Error("Numbered source lineage missing");
          element.scrollLeft = header.offsetLeft;
        });
        await links.locator("..").screenshot({
          path: `${screenshots}/IN-${form}-numbered-source-fields.png`,
        });
        if (form === "144") {
          await links.locator("..").evaluate((element) => {
            const header = Array.from(element.querySelectorAll("th")).find(
              (node) => node.textContent === "recorded residence address",
            );
            if (!header) throw new Error("Numbered residence lineage missing");
            element.scrollLeft = header.offsetLeft;
          });
          await expect(
            links.getByRole("cell", { name: "69877877878", exact: true }),
          ).toBeVisible();
          await links.locator("..").screenshot({
            path: `${screenshots}/IN-144-recorded-residence-fields.png`,
          });
        }
      }
      if (form === "27Q") {
        expect(metadata.nonresident_treaty_and_residence_qualification).toBe(
          "NOT_PERFORMED",
        );
        await expect(
          links.getByRole("columnheader", {
            name: "residence country code",
            exact: true,
          }),
        ).toBeVisible();
        await links.locator("..").evaluate((element) => {
          const header = Array.from(element.querySelectorAll("th")).find(
            (node) => node.textContent === "recorded rate basis",
          );
          if (!header) throw new Error("Nonresident field header missing");
          element.scrollLeft = header.offsetLeft;
        });
        await links.locator("..").screenshot({
          path: `${screenshots}/IN-27Q-nonresident-recorded-fields.png`,
        });
      }
      await upload(
        mapping.record,
        `SYNTHETIC-${form}-crosswalk-corrected.txt`,
        Buffer.from(
          "SYNTHETIC corrected independent crosswalk requires new assessment",
        ),
      );
      const response = await reviewer.request.get(
        `/api/backend/${prefix}/events/${reviewed.id}`,
        { headers },
      );
      expect(response.status()).toBe(200);
      const historical = await response.json();
      expect(historical.freshness).toBe("STALE");
      expect(historical.body).toEqual(reviewed.body);
      expect(historical.version).toBe(reviewed.version);
      await reviewer.goto(
        `/intelligence/${eid}/workflow-source?event=${reviewed.id}`,
      );
      await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
      await expect(
        reviewer.getByRole("button", {
          name: "Independent approval",
          exact: true,
        }),
      ).toBeDisabled();
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/IN-${form}-native-crosswalk-superseded-stale.png`,
        });
    }
    const salaryPeriod = await create("financial-periods", {
      entity_id: entity.id,
      start_date: "2024-04-01",
      end_date: "2025-03-31",
    });
    const salaryEngagement = await create("engagements", {
      entity_id: entity.id,
      period_id: salaryPeriod.id,
      name: "SYNTHETIC four-quarter salary comparison",
      engagement_type: "External Audit",
    });
    await create(
      `engagements/${salaryEngagement.id}/audit/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    await runSalaryAnnualBrowserWorkflow(
      page,
      reviewer,
      salaryEngagement.id,
      identities.tenant_id,
      screenshots,
    );
    const panPeriod = await create("financial-periods", {
      entity_id: entity.id,
      start_date: "2026-04-01",
      end_date: "2027-03-31",
    });
    const panEngagement = await create("engagements", {
      entity_id: entity.id,
      period_id: panPeriod.id,
      name: "SYNTHETIC current missing-PAN treatment review",
      engagement_type: "External Audit",
    });
    await create(
      `engagements/${panEngagement.id}/audit/team`,
      {
        membership_id: identities.reviewer_membership_id,
        role_id: identities.reviewer_role_id,
      },
      200,
    );
    await runWithholdingPANBrowserWorkflow(
      page,
      reviewer,
      panEngagement.id,
      identities.tenant_id,
      screenshots,
    );
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

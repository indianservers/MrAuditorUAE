import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { runWithholdingPANBrowserWorkflow } from "./withholding-pan-browser-workflow";
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

test("India historical native samples and explicit dated Form 143 fixture, controlled forms, full lineage and crosswalk staleness", async ({
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
    for (const form of ["26Q", "27EQ", "27Q", "143"] as const) {
      const count =
        form === "143" ? 1 : form === "26Q" ? 4 : form === "27Q" ? 2 : 10;
      const month =
        form === "143"
          ? "2026-05"
          : form === "26Q"
            ? "2020-04"
            : form === "27Q"
              ? "2019-12"
              : "2020-10";
      const total =
        form === "143"
          ? "700"
          : form === "26Q"
            ? "1900"
            : form === "27Q"
              ? "166000"
              : "1000";
      const gross =
        form === "143"
          ? "213000"
          : form === "26Q"
            ? "100000"
            : form === "27Q"
              ? "20000000"
              : "10000";
      const groups = Array.from({ length: count }, (_, i) => ({
        transaction_reference: `SYN-ASSESSMENT-${i + 1}`,
        transaction_date: month + (form === "27Q" ? "-10" : "-01"),
        period: month,
        rule_reference: "SYN-ASSESSED-SECTION",
        party_records: [`1/1/${i + 1}`],
      }));
      const publicOriginal = readFileSync(
        form === "143"
          ? "../docs/country-workflows/authority-references/form143-2026-07-22/protean-form143-original-sample.txt"
          : `../docs/country-workflows/authority-references/protean-legacy-2025-05-27/protean-${form}-original-sample.txt`,
      );
      let sourceBytes = publicOriginal;
      if (form === "143") {
        await evidence(
          "public-issuer-143-incomplete-original-sample.txt",
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
          [3, 25, "1000.00"],
          [4, 18, "Y"],
        ] as const)
          records[line - 1][field - 1] = value;
        sourceBytes = Buffer.from(
          records.map((row) => row.join("^")).join("\r\n") + "\r\n",
          "ascii",
        );
      }
      const file = await evidence(
        form === "143"
          ? "SYNTHETIC-explicit-completion-143.txt"
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
          form === "143"
            ? "india-form143-regular-20260722-v1.1"
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
        .selectOption(form === "26Q" || form === "143" ? "Q1" : "Q3");
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
        ["Native statement TAN", form === "143" ? "BLRF02329F" : "MUMN77777A"],
        [
          form === "143"
            ? "Native tax year (six digits)"
            : "Native financial year (six digits)",
          form === "143" ? "202627" : form === "27Q" ? "201920" : "202021",
        ],
        ["Native observation cutoff", "2026-10-30"],
        ["Native batch count", "1"],
        ["Native challan count", "1"],
        ["Native party count", String(count)],
        ...(form === "143"
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
          form === "143"
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
      if (form === "27EQ")
        await page
          .getByLabel("Native purchase value control (INR)", { exact: true })
          .fill("10000");
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
          name:
            form === "143"
              ? "5000032"
              : form === "26Q"
                ? "0000809"
                : form === "27Q"
                  ? "0000525"
                  : "0000897",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        challans.getByRole("cell", { name: gross + ".00", exact: true }),
      ).toBeVisible();
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
            `assert c[1][c[0].index('bsr_or_form24g_reference')]=='${form === "143" ? "5000032" : form === "26Q" ? "0000809" : form === "27Q" ? "0000525" : "0000897"}'`,
            ...(form === "143"
              ? [
                  "assert r[0]['recorded_deposited_flag']=='Y'",
                  "assert 'income_tax' not in r[0]",
                  "assert c[1][c[0].index('ddo_serial')]=='00001'",
                  "assert c[1][c[0].index('recorded_payment_mode')]=='B'",
                  "assert c[1][c[0].index('allocated_interest')]=='1000.00'",
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
    await runWithholdingPANBrowserWorkflow(
      page,
      reviewer,
      eid,
      identities.tenant_id,
      screenshots,
    );
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

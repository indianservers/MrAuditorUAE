import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { makeWorkflowHarness } from "./msme-browser-workflow";

export async function runSalaryAnnualBrowserWorkflow(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, post, evidence, upload, prepare } =
    makeWorkflowHarness(page, eid, tenant);
  const sourceIds: Record<string, string> = {};
  for (const q of ["Q1", "Q2", "Q3", "Q4"] as const) {
    const total = q === "Q1" ? "10000" : q === "Q4" ? "1000" : "500";
    const month = q === "Q1" ? "04" : q === "Q2" ? "07" : "10";
    const controls = JSON.parse(
      readFileSync(
        "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-quarterly-controls.json",
        "utf8",
      ),
    );
    let raw = readFileSync(
      q === "Q4"
        ? "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-complete-q4.txt"
        : "../docs/country-workflows/authority-references/protean-legacy-2025-05-27/protean-24Q-Q3-original-sample.txt",
    );
    if (q !== "Q4") {
      expect(raw.subarray(-2).toString()).toBe("\r\n");
      const records = raw
        .subarray(0, -2)
        .toString("ascii")
        .split("\r\n")
        .map((line) => line.split("^"));
      for (const [line, field, value] of [
        [1, 5, "01042025"],
        [2, 16, "202526"],
        [2, 17, "202425"],
        [2, 18, q],
        [2, 47, total + ".00"],
        [3, 22, total + ".00"],
        [3, 27, total + ".00"],
        [3, 29, total + ".00"],
        [3, 30, total + ".00"],
        [3, 33, total + ".00"],
        [3, 18, "14" + month + "2024"],
        [4, 14, total + ".00"],
        [4, 17, total + ".00"],
        [4, 19, total + ".00"],
        [4, 23, "16" + month + "2024"],
        [4, 24, "16" + month + "2024"],
        [4, 25, "14" + month + "2024"],
      ] as const)
        records[line - 1][field - 1] = value;
      raw = Buffer.from(
        records.map((r) => r.join("^")).join("\r\n") + "\r\n",
        "ascii",
      );
      Object.assign(controls, {
        quarter: q,
        income_tax: total,
        allocated_deposit: total,
        challan_deposit: total,
      });
      controls.groups[0].period = "2024-" + month;
      controls.groups[0].transaction_date = "2024-" + month + "-16";
    }
    const file = await evidence(`SYNTHETIC-annual-comparison-${q}.txt`, raw);
    const mapping = await evidence(
      `SYNTHETIC-quarter-${q}-mapping.txt`,
      Buffer.from(
        JSON.stringify({
          classification: "SYNTHETIC_QUARTER_MAPPING",
          quarter: q,
          controls,
        }),
      ),
    );
    controls.crosswalk_document_version_id = mapping.version.id;
    const source = await prepare({
      file_format:
        q === "Q4"
          ? "india-24q-regular-q4-v7.5"
          : "india-24q-regular-q1q3-v6.3",
      table_type: "withholding-records",
      evidence_version_id: file.version.id,
      label: `SYNTHETIC annual ${q} native salary`,
      expected_rows: 1,
      control_totals: { INR: total },
      native_withholding_controls: controls,
      ...(q === "Q4"
        ? {
            salary_annual_controls: JSON.parse(
              readFileSync(
                "../docs/country-workflows/sample-inputs/SYNTHETIC-annual-24q/SYNTHETIC-annual-controls.json",
                "utf8",
              ),
            ),
          }
        : {}),
    });
    const reviewed = await post(
      reviewer.request,
      `${prefix}/events/${source.id}/review`,
      {
        expected_version: source.version,
        action: "approve",
        comments:
          "SYNTHETIC independently reviewed complete native quarter and controlled original annual observations",
      },
    );
    sourceIds[q] = reviewed.id;
  }
  const employees = [
    {
      annual_key: "SD/1/1",
      parties: Object.keys(sourceIds).map((quarter) => ({
        quarter,
        party_key: "1/1/1",
      })),
      identity_status: "assessed_same_employee",
      assessment:
        "SYNTHETIC independently assessed employee across the four original quarterly populations",
    },
  ];
  const mapping = await evidence(
    "SYNTHETIC-independent-four-quarter-mapping.txt",
    Buffer.from(
      JSON.stringify({
        classification: "SYNTHETIC_INDEPENDENT_ANNUAL_MAPPING",
        employees,
        expected_current_employer_tax: "12000.00",
      }),
    ),
  );
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByText(
      "Compare four salary quarters with annual current-employer tax",
      { exact: true },
    )
    .click();
  for (const q of Object.keys(sourceIds))
    await page
      .getByRole("combobox", { name: `Salary ${q} native source`, exact: true })
      .selectOption(sourceIds[q]);
  await page
    .getByRole("combobox", {
      name: "Independent annual employee and nil-quarter crosswalk",
      exact: true,
    })
    .selectOption(mapping.version.id);
  const title = "SYNTHETIC all-quarter current-employer salary comparison";
  await page
    .getByLabel("Annual salary comparison title", { exact: true })
    .fill(title);
  await page
    .getByLabel("Annual salary employee mapping (JSON)", { exact: true })
    .fill(JSON.stringify(employees));
  await page
    .getByLabel("Annual salary full-population assessment", { exact: true })
    .fill(
      "SYNTHETIC independent all-quarter and complete SD population assessment; previous employers and other credits excluded",
    );
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/salary-annual-comparison`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Prepare annual salary comparison",
      exact: true,
    })
    .click();
  const response = await submitted;
  expect(response.status(), await response.text()).toBe(201);
  const result = await response.json();
  expect(result.body.rows[0].quarterly_tax).toBe("12000.00");
  expect(result.body.rows[0].annual_current_employer_tax).toBe("12000.00");
  expect(result.body.exception_count).toBe(0);
  const self = await page.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments: "SYNTHETIC self review remains forbidden",
      },
    },
  );
  expect(self.status()).toBe(403);
  const reviewed = await post(
    reviewer.request,
    `${prefix}/events/${result.id}/review`,
    {
      expected_version: result.version,
      action: "approve",
      comments:
        "SYNTHETIC independently reviewed all-quarter source linkage and current-employer comparison only",
    },
  );
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("REVIEWED", { exact: true })).toBeVisible();
  const lineage = reviewer.getByRole("region", {
    name: "Annual salary quarter lineage",
    exact: true,
  });
  await expect(lineage.getByRole("table").getByRole("row")).toHaveCount(5);
  await lineage.screenshot({
    path: `${screenshots}/IN-24Q-all-quarter-reviewed-links.png`,
  });
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/IN-24Q-all-quarter-comparison-reviewed.png`,
    });
  const downloading = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  const download = await (await downloading).path();
  expect(download).not.toBeNull();
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
        "v=list(w['Salary quarter links'].values)",
        "assert len(v)==5",
        "assert [r[v[0].index('quarter')] for r in v[1:]]==['Q1','Q2','Q3','Q4']",
        "assert 'Unassigned salary parties' in w.sheetnames",
      ].join("\n"),
    ],
    { input: readFileSync(download!), timeout: 15000 },
  );
  await upload(
    mapping.record,
    "SYNTHETIC-changed-annual-identity.txt",
    Buffer.from(
      "SYNTHETIC updated annual identity mapping requires reassessment",
    ),
  );
  const stale = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(stale.status()).toBe(200);
  const historical = await stale.json();
  expect(historical.freshness).toBe("STALE");
  expect(historical.body).toEqual(reviewed.body);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer
    .getByRole("heading", { name: title, exact: true })
    .locator("..")
    .screenshot({
      path: `${screenshots}/IN-24Q-all-quarter-crosswalk-stale.png`,
    });
}

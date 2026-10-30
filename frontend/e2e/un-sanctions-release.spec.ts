import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
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

test("synthetic UAE then India native UN XML controls, alias adjudication, complete export and source withdrawal", async ({
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
    viewport: { width: 1900, height: 1400 },
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
    const sharedHeaders = {
      "X-Tenant-ID": identities.tenant_id,
      Origin: process.env.AUDITOS_E2E_ORIGIN!,
    };
    async function create(path: string, data: unknown, status = 201) {
      const response = await page.request.post(`/api/backend/${path}`, {
        headers: sharedHeaders,
        data,
      });
      expect(response.status(), await response.text()).toBe(status);
      return response.json();
    }
    for (const country of ["AE", "IN"] as const) {
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption(country);
        await expect(
          actor.getByRole("combobox", { name: "Working country", exact: true }),
        ).toHaveValue(country);
      }
      const client = await create("clients", {
        code: `UN-${country}-${Date.now()}`,
        name: `SYNTHETIC UN ${country} client`,
      });
      const currency = country === "AE" ? "AED" : "INR";
      const entity = await create("entities", {
        client_id: client.id,
        name: `SYNTHETIC UN ${country} entity`,
        country,
        jurisdiction: country === "AE" ? "UAE" : "India",
        functional_currency: currency,
        presentation_currency: currency,
      });
      const period = await create("financial-periods", {
        entity_id: entity.id,
        start_date: country === "AE" ? "2026-01-01" : "2026-04-01",
        end_date: country === "AE" ? "2026-12-31" : "2027-03-31",
      });
      const engagement = await create("engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC UN ${country}`,
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
      const { headers, prefix, post, evidence, completed, prepare } =
        makeWorkflowHarness(page, eid, identities.tenant_id);
      const bytes = readFileSync(
        "../docs/country-workflows/sample-inputs/SYNTHETIC-un-consolidated.xml",
      );
      const file = await evidence("SYNTHETIC-un-consolidated.xml", bytes);
      const sourceTitle = `SYNTHETIC ${country} controlled UN snapshot`;
      await page.goto(`/intelligence/${eid}/workflow-source`);
      await page
        .getByRole("combobox", { name: "Source file format", exact: true })
        .selectOption("un-sc-consolidated-xml");
      await page
        .getByRole("combobox", { name: "Clean retained evidence", exact: true })
        .selectOption(file.version.id);
      for (const [label, value] of [
        ["Schedule title", sourceTitle],
        ["Expected data rows", "6"],
        ["UN XML generated timestamp with timezone", "2026-06-29T23:00:00Z"],
        ["UN individuals", "1"],
        ["UN entities", "1"],
        ["UN original script names", "1"],
        ["UN individual alias names", "2"],
        ["UN entity alias names", "1"],
        ["UN empty alias records", "2"],
        [
          "UN snapshot population assessment",
          "SYNTHETIC independent subject, original script and alias counts; no identity or legal qualification",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      await expect(
        page.getByLabel("Independent totals by currency", { exact: true }),
      ).toHaveCount(0);
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
      let native = await completed((await queued.json()).id);
      expect(native.body.rows).toHaveLength(6);
      expect(native.body.allowed_source_roles).toEqual(["list"]);
      const metadata = native.body.native_metadata as Record<string, unknown>;
      expect(metadata.identity_or_legal_clearance).toBe("NOT_DETERMINED");
      expect(metadata.authenticity).toBe("UPLOADED_SNAPSHOT_NOT_AUTHENTICATED");
      const self = await page.request.post(
        `/api/backend/${prefix}/events/${native.id}/review`,
        {
          headers,
          data: {
            expected_version: native.version,
            action: "approve",
            comments: "SYNTHETIC source self-approval must fail",
          },
        },
      );
      expect(self.status()).toBe(403);
      native = await post(
        reviewer.request,
        `${prefix}/events/${native.id}/review`,
        {
          expected_version: native.version,
          action: "approve",
          comments:
            "SYNTHETIC independent original XML and population assessment; no clearance",
        },
      );
      const selected: Record<string, string> = { list: native.id };
      for (const [role, table, content] of [
        [
          "subjects",
          "screening-subjects",
          "id,name,evidence_reference\nSUBJECT-1,Example Alias,SYNTHETIC-ID\n",
        ],
        [
          "policy",
          "screening-policies",
          `id,minimum_similarity,maximum_list_age_days,list_version,evidence_reference\nPOLICY-1,1,7,${metadata.list_version},SYNTHETIC-POLICY\n`,
        ],
      ]) {
        const retained = await evidence(
          `SYNTHETIC-un-${role}.csv`,
          Buffer.from(content),
        );
        const source = await prepare({
          evidence_version_id: retained.version.id,
          table_type: table,
          expected_rows: 1,
          control_totals: {},
          label: `SYNTHETIC UN ${role}`,
        });
        const approved = await post(
          reviewer.request,
          `${prefix}/events/${source.id}/review`,
          {
            expected_version: source.version,
            action: "approve",
            comments:
              "SYNTHETIC independent subject or exact snapshot version policy review",
          },
        );
        selected[role] = approved.id;
      }
      const title = `SYNTHETIC ${country} UN aliases require adjudication`;
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByRole("combobox", { name: "Workflow", exact: true })
        .selectOption("sanctions-name-review");
      for (const [role, id] of Object.entries(selected))
        await page
          .getByRole("combobox", { name: `${role} source`, exact: true })
          .selectOption(id);
      await page.getByLabel("Schedule title", { exact: true }).fill(title);
      await page
        .getByLabel("Reconciliation date", { exact: true })
        .fill("2026-06-30");
      await page
        .getByLabel("Scope and source rationale", { exact: true })
        .fill(
          "SYNTHETIC two source aliases for one list subject; source quality is not positive identification or clearance",
        );
      const calculation = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/${prefix}/jobs`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", { name: "Queue calculation", exact: true })
        .click();
      const calculationResponse = await calculation;
      expect(
        calculationResponse.status(),
        await calculationResponse.text(),
      ).toBe(202);
      let result = await completed((await calculationResponse.json()).id);
      const row = result.body.rows[0];
      expect(row.state).toBe("POTENTIAL_NAME_MATCH");
      expect(row.candidate_count).toBe(2);
      expect(row.reviewer_disposition).toBe("UNREVIEWED");
      await page.goto(
        `/intelligence/${eid}/country-workflow?event=${result.id}`,
      );
      const table = page.getByRole("table", {
        name: "Name-screening candidates",
        exact: true,
      });
      await expect(table.getByRole("row")).toHaveCount(3);
      await expect(
        table.getByRole("cell", { name: "Good", exact: true }),
      ).toBeVisible();
      await expect(
        table.getByRole("cell", { name: "Low", exact: true }),
      ).toBeVisible();
      await expect(
        table.getByRole("cell", { name: "ZZi.001", exact: true }),
      ).toHaveCount(2);
      await expect(
        page.getByText(/Low-quality aliases alone are insufficient/),
      ).toBeVisible();
      const blocked = await reviewer.request.post(
        `/api/backend/${prefix}/events/${result.id}/review`,
        {
          headers,
          data: {
            expected_version: result.version,
            action: "approve",
            comments:
              "SYNTHETIC unadjudicated candidate result must remain unapproved",
          },
        },
      );
      expect(blocked.status()).toBe(409);
      result = await post(
        page.request,
        `${prefix}/events/${result.id}/review`,
        {
          expected_version: result.version,
          action: "accept",
          item_id: String(row.id),
          comments:
            "SYNTHETIC both aliases retained and independently assessed; Low alone does not identify a person; no real identity clearance",
        },
      );
      const reviewed: WorkflowEvent = await post(
        reviewer.request,
        `${prefix}/events/${result.id}/review`,
        {
          expected_version: result.version,
          action: "approve",
          comments:
            "SYNTHETIC independent review of the complete candidate observations and recorded disposition; no client clearance",
        },
      );
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
      );
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      await reviewer
        .getByRole("region", {
          name: "Screening candidate review",
          exact: true,
        })
        .screenshot({
          path: `${screenshots}/${country}-UN-alias-quality-reviewed.png`,
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
            "from openpyxl import load_workbook",
            "w=load_workbook(io.BytesIO(sys.stdin.buffer.read()))",
            "v=list(w['Screening candidates'].values);r=[dict(zip(v[0],x)) for x in v[1:]]",
            "assert len(r)==2 and {x['native_alias_quality'] for x in r}=={'Good','Low'}",
            "assert all(x['native_reference_number']=='ZZi.001' and x['list_subject_id']=='UN:1' for x in r)",
          ].join("\n"),
        ],
        { input: readFileSync(downloaded!), timeout: 15000 },
      );
      await post(reviewer.request, `${prefix}/events/${native.id}/review`, {
        expected_version: native.version,
        action: "reject",
        comments:
          "SYNTHETIC uploaded XML source withdrawal requires new evidence assessment",
      });
      const historicalResponse = await reviewer.request.get(
        `/api/backend/${prefix}/events/${reviewed.id}`,
        { headers },
      );
      expect(historicalResponse.status()).toBe(200);
      const historical = await historicalResponse.json();
      expect(historical.freshness).toBe("STALE");
      expect(historical.body).toEqual(reviewed.body);
      expect(historical.version).toBe(reviewed.version);
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
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
          path: `${screenshots}/${country}-UN-source-withdrawn-stale.png`,
        });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

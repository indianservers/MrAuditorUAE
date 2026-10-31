import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { makeWorkflowHarness } from "./msme-browser-workflow";

async function login(page: Page, email: string) {
  if (!email || !process.env.AUDITOS_SMOKE_PASSWORD)
    throw new Error("Explicit isolated synthetic identities required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AUDITOS_SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
}

test("UAE company accounts duty, explicit written request, independent review and legal-adoption staleness", async ({
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
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 1800, height: 1600 },
  });
  const reviewer = await context.newPage();
  const errors: string[] = [];
  for (const actor of [page, reviewer]) {
    actor.setDefaultTimeout(20000);
    actor.on("pageerror", (e) => errors.push(e.message));
  }
  try {
    await login(page, process.env.AUDITOS_SMOKE_EMAIL!);
    await login(reviewer, process.env.AUDITOS_SMOKE_REVIEWER_EMAIL!);
    for (const actor of [page, reviewer]) {
      await actor.goto("/settings/countries");
      await actor
        .getByRole("combobox", { name: "Working country", exact: true })
        .selectOption("AE");
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
    const client = await post(page.request, "clients", {
      code: `CCL-${Date.now()}`,
      name: "SYNTHETIC CCL assessment client",
    });
    const entity = await post(page.request, "entities", {
      client_id: client.id,
      name: "SYNTHETIC UAE company-law entity",
      country: "AE",
      jurisdiction: "Synthetic",
      functional_currency: "AED",
      presentation_currency: "AED",
    });
    const period = await post(page.request, "financial-periods", {
      entity_id: entity.id,
      start_date: "2025-01-01",
      end_date: "2025-12-31",
    });
    const eng = await post(page.request, "engagements", {
      entity_id: entity.id,
      period_id: period.id,
      name: "SYNTHETIC completed company FY2025",
      engagement_type: "External Audit",
    });
    const eid = eng.id;
    await post(
      page.request,
      `engagements/${eid}/audit/team`,
      {
        membership_id: ids.reviewer_membership_id,
        role_id: ids.reviewer_role_id,
      },
      200,
    );
    const { evidence, upload, prefix } = makeWorkflowHarness(
      page,
      eid,
      ids.tenant_id,
    );
    const folder =
      "../docs/country-workflows/authority-references/uae-company-law-2026-10-31";
    const law = await evidence(
      "original-company-law-english.pdf",
      readFileSync(`${folder}/moet-hosted-companies-law32-2021-english.pdf`),
    );
    const amendment = await evidence(
      "original-company-law-amendment.pdf",
      readFileSync(`${folder}/fdl20-2025-arabic-original.pdf`),
    );
    const adoption = await evidence(
      "SYNTHETIC-company-legal-adoption.txt",
      Buffer.from(
        "SYNTHETIC independently adopted whole-period source chain and publication date2025-11-01 for testing only. This is not the real Gazette date or professional qualification.",
      ),
    );
    const facts = await evidence(
      "SYNTHETIC-company-facts.txt",
      Buffer.from(
        "SYNTHETIC separate scenarios: LLC subject to CCL for completed FY2025; no requests in one population, one independently assessed written partner/shareholder request in another, holding-company accounts and all copies delivered on2026-09-30. No actual client evidence.",
      ),
    );
    const reviewed: { id: string; body: Record<string, unknown> }[] = [];
    for (const written of [false, true]) {
      await page.goto(`/intelligence/${eid}/country-workflow`);
      await page
        .getByText(
          "Assess UAE company-law accounts and written-request duties",
          { exact: true },
        )
        .click();
      const title = `SYNTHETIC company accounts ${written ? "written request" : "nil request population"}`;
      for (const [label, value] of [
        ["Company accounts assessment title", title],
        ["Company registration reference", "SYNTHETIC-CCL-REG"],
        ["Company fiscal year start", "2025-01-01"],
        ["Company fiscal year end", "2025-12-31"],
        ["Company assessed on", "2026-10-01"],
        ["Company rule adopted from", "2025-01-01"],
        ["Company rule adopted through", "2026-12-31"],
        [
          "Declared amendment publication date (leave blank if not established)",
          "2025-11-01",
        ],
        [
          "Company operative source-chain assessment",
          "SYNTHETIC independently assessed whole-period source chain with declared publication2025-11-01; no actual Gazette or legal qualification",
        ],
        [
          "Company-law applicability and exclusions assessment",
          "SYNTHETIC independently assessed whole-period company scope and exclusions",
        ],
        [
          "Company and request evidence assessment",
          "SYNTHETIC independently assessed exact completed fiscal year, LLC and explicit written-request population",
        ],
      ])
        await page.getByLabel(label, { exact: true }).fill(value);
      const choices = [
        ["Company source-chain status", "assessed_adopted"],
        ["Company other operative changes", "assessed_none"],
        ["Company-law applicability", "assessed_applies"],
        ["Company fiscal year validity", "assessed_valid"],
        ["Assessed company legal form", "limited_liability"],
        ["Holding company assessed", written ? "assessed_yes" : "assessed_no"],
        [
          "Company written request population",
          written ? "written_request" : "assessed_none",
        ],
        ["Original Ministry-hosted unofficial English law PDF", law.version.id],
        ["Original Arabic company-law amendment PDF", amendment.version.id],
        [
          "Separate company-law operative adoption evidence",
          adoption.version.id,
        ],
        ["Separate company and request facts", facts.version.id],
      ];
      if (written) {
        for (const [label, value] of [
          [
            "Written request received on (leave blank if not established)",
            "2026-09-20",
          ],
          [
            "Response delivered on (leave blank if not established)",
            "2026-09-30",
          ],
          [
            "Written request day-counting assessment",
            "SYNTHETIC independently adopted calendar-day counting excluding receipt day",
          ],
        ])
          await page.getByLabel(label, { exact: true }).fill(value);
        choices.push(
          ["Written requester eligibility", "assessed_partner_or_shareholder"],
          ["Selected year is last audited accounts", "assessed_yes"],
          [
            "Written request counting basis",
            "assessed_calendar_days_excluding_receipt",
          ],
          ["Company response status", "assessed_responded"],
          ["Accounts copy delivered", "assessed_yes"],
          ["Auditor report copy delivered", "assessed_yes"],
          ["Group accounts copy delivered", "assessed_yes"],
        );
      }
      for (const [label, value] of choices)
        await page
          .getByRole("combobox", { name: label, exact: true })
          .selectOption(value);
      const pending = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/${prefix}/uae-company-accounts-duty`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: "Prepare company-law accounts assessment",
          exact: true,
        })
        .click();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(201);
      const result = await response.json();
      expect(result.body.rows[0].annual_audit_required).toBe(true);
      expect(result.body.rows[0].entity_audit_exemption_established).toBe(
        false,
      );
      expect(result.body.exception_count).toBe(0);
      const self = await page.request.post(
        `/api/backend/${prefix}/events/${result.id}/review`,
        {
          headers,
          data: {
            expected_version: result.version,
            action: "approve",
            comments: "SYNTHETIC self-review must remain forbidden",
          },
        },
      );
      expect(self.status()).toBe(403);
      reviewed.push(
        await post(reviewer.request, `${prefix}/events/${result.id}/review`, {
          expected_version: result.version,
          action: "approve",
          comments:
            "SYNTHETIC independent procedure and original-document review only; no actual client, legal or professional qualification",
        }),
      );
      await reviewer.goto(
        `/intelligence/${eid}/country-workflow?event=${reviewed.at(-1)!.id}`,
      );
      await expect(
        reviewer.getByText("REVIEWED", { exact: true }),
      ).toBeVisible();
      const summary = reviewer.getByRole("region", {
        name: "UAE company-law accounts summary",
        exact: true,
      });
      await expect(summary).toContainText("At least five years");
      if (written) {
        expect(result.body.rows[0].response_deadline).toBe("2026-09-30");
        expect(result.body.rows[0].response_complete).toBe(true);
        await expect(summary).toContainText("2026-09-30");
        await expect(summary).toContainText("Assessed complete");
      }
      await reviewer
        .getByRole("heading", { name: title, exact: true })
        .locator("..")
        .screenshot({
          path: `${screenshots}/AE-company-accounts-${written ? "written-request" : "nil-request"}-reviewed.png`,
        });
      const downloading = reviewer.waitForEvent("download");
      await reviewer
        .getByRole("button", { name: "Export XLSX", exact: true })
        .click();
      const path = await (await downloading).path();
      expect(path).not.toBeNull();
      execFileSync(
        process.platform === "win32"
          ? "../backend/.venv/Scripts/python.exe"
          : "../backend/.venv/bin/python",
        [
          "-c",
          "import io,sys; from openpyxl import load_workbook; w=load_workbook(io.BytesIO(sys.stdin.buffer.read()),read_only=True); r=list(w['Rows'].values); assert str(r[1][r[0].index('annual_audit_required')]).lower()=='true'; assert str(r[1][r[0].index('minimum_register_retention_years')])=='5'",
        ],
        { input: readFileSync(path!), timeout: 15000 },
      );
    }
    await upload(
      adoption.record,
      "SYNTHETIC-revised-legal-adoption.txt",
      Buffer.from(
        "SYNTHETIC changed legal adoption requires independent reassessment",
      ),
    );
    for (const original of reviewed) {
      const response = await reviewer.request.get(
        `/api/backend/${prefix}/events/${original.id}`,
        { headers },
      );
      expect(response.status()).toBe(200);
      const historical = await response.json();
      expect(historical.freshness).toBe("STALE");
      expect(historical.body).toEqual(original.body);
    }
    await reviewer.goto(
      `/intelligence/${eid}/country-workflow?event=${reviewed.at(-1)!.id}`,
    );
    await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
    await expect(
      reviewer.getByRole("button", {
        name: "Independent approval",
        exact: true,
      }),
    ).toBeDisabled();
    await reviewer
      .getByRole("heading", {
        name: "SYNTHETIC company accounts written request",
        exact: true,
      })
      .locator("..")
      .screenshot({
        path: `${screenshots}/AE-company-accounts-adoption-stale.png`,
      });
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

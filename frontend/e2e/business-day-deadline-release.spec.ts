import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

type Paper = {
  id: string;
  version: number;
  status: string;
  body: Record<string, unknown>;
};

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

test("explicit UAE and India business-day calendars, independent filing and replacement staleness", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const identities = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(identities.synthetic_only).toBe(true);
  const screenshots = "test-results/country-reports";
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 1800, height: 1800 },
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
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption(country);
      }
      const currency = country === "AE" ? "AED" : "INR";
      const client = await post(page.request, "clients", {
        code: `BD-${country}-${Date.now()}`,
        name: "SYNTHETIC business-calendar client",
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC ${country} business-calendar entity`,
        country,
        jurisdiction: country,
        functional_currency: currency,
        presentation_currency: currency,
      });
      const period = await post(page.request, "financial-periods", {
        entity_id: entity.id,
        start_date: "2026-01-01",
        end_date: "2026-12-31",
      });
      const engagement = await post(page.request, "engagements", {
        entity_id: entity.id,
        period_id: period.id,
        name: `SYNTHETIC ${country} business-calendar evidence review`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id;
      const audit = `engagements/${eid}/audit`,
        base = `grc/engagements/${eid}`;
      await post(
        page.request,
        `${audit}/team`,
        {
          membership_id: identities.reviewer_membership_id,
          role_id: identities.reviewer_role_id,
        },
        200,
      );
      async function action(
        request: APIRequestContext,
        prefix: string,
        paper: Paper,
        value: string,
      ): Promise<Paper> {
        return post(
          request,
          `${prefix}/records/${paper.id}/actions`,
          {
            version: paper.version,
            action: value,
            comments:
              "SYNTHETIC independent calendar/source decision; not legal or national holiday qualification",
          },
          200,
        );
      }
      const { evidence, upload } = makeWorkflowHarness(
        page,
        eid,
        identities.tenant_id,
      );
      const documents: Record<string, Paper> = {};
      let calendarRecord = "";
      for (const role of ["rule", "facts", "calendar", "readiness"]) {
        const file = await evidence(
          `SYNTHETIC-${country}-business-${role}.txt`,
          Buffer.from(
            `SYNTHETIC ${role}; five working days, excluded trigger, weekend 5/6 and fictional June 29 holiday; no legal qualification`,
          ),
        );
        if (role === "calendar") calendarRecord = file.record;
        let paper: Paper = await get(`${audit}/records/${file.record}`);
        paper = await action(page.request, audit, paper, "submit");
        documents[role] = await action(
          reviewer.request,
          audit,
          paper,
          "approve",
        );
      }
      const reference = `SYN-BUSINESS-${country}`;
      let paper: Paper = await post(
        page.request,
        `${base}/records/obligation`,
        {
          reference,
          title: `SYNTHETIC ${country} five working day obligation`,
          body: {
            owner_id: identities.preparer_user_id,
            entity_id: entity.id,
            module: "policy",
            source_url: "https://synthetic.invalid/business-calendar-rule",
            jurisdiction: country,
            jurisdiction_scope: {
              entity_country: country,
              obligation_country: country,
              relationship: "domestic",
              applicability: "assessed_applicable",
              assessment:
                "SYNTHETIC exact country and complete calendar assessment",
            },
            effective_from: "2026-01-01",
            required_evidence:
              "Independent original policy, event facts, complete calendar and readiness evidence",
            compliance_assessment: "pending",
            filing_stage: "preparing",
            rule_evidence_id: documents.rule.id,
            calendar_evidence_id: documents.calendar.id,
            fact_evidence_ids: [documents.facts.id],
            readiness_evidence_ids: [documents.readiness.id],
            reviewer_id: identities.reviewer_user_id,
            entity_facts: {
              trigger: "2026-06-26",
              assessment: "SYNTHETIC observed event and assessed calendar only",
            },
            deadline_kind: "firm_internal",
            deadline_rule: {
              identifier: "SYNTHETIC-five-working-days",
              version: 1,
              effective_from: "2026-01-01",
              trigger: "2026-06-26",
              date_basis: "specified_event",
              days_after: 5,
              timezone: country === "AE" ? "Asia/Dubai" : "Asia/Kolkata",
              day_count_basis: "business",
              business_trigger_policy: "exclude",
              business_calendar: {
                coverage_start: "2026-06-01",
                coverage_end: "2026-07-31",
                weekend_days: [5, 6],
                holidays: ["2026-06-29"],
                independent_holiday_count: 1,
                assessment:
                  "SYNTHETIC independently checked complete operating calendar; not actual national holidays",
              },
            },
          },
        },
      );
      expect(paper.body.deadline).toBe("2026-07-06");
      async function open(actor: Page) {
        await actor.goto(`/grc/${eid}/obligations`);
        await actor
          .getByRole("gridcell", { name: reference, exact: true })
          .click();
        const panel = actor.getByRole("region", {
          name: "Filing readiness",
          exact: true,
        });
        await expect(panel).toContainText("2026-07-06");
        await expect(
          panel.getByRole("region", {
            name: "Business-day deadline basis",
            exact: true,
          }),
        ).toContainText("exclude the triggering day");
        await expect(panel).toContainText("2026-06-29");
        return panel;
      }
      async function stage(actor: Page, value: string): Promise<Paper> {
        const panel = actor.getByRole("region", {
          name: "Filing readiness",
          exact: true,
        });
        await panel
          .getByRole("combobox", { name: "Next filing stage", exact: true })
          .selectOption(value);
        const response = actor.waitForResponse(
          (r) =>
            r.url().includes(`/obligations/${paper.id}/filing-stage`) &&
            r.request().method() === "POST",
        );
        await panel
          .getByRole("button", {
            name: "Record evidenced filing stage",
            exact: true,
          })
          .click();
        const result = await response;
        expect(result.status(), await result.text()).toBe(200);
        return result.json();
      }
      await open(page);
      paper = await stage(page, "under_review");
      paper = await action(page.request, base, paper, "submit");
      paper = await action(reviewer.request, base, paper, "approve");
      let panel = await open(reviewer);
      paper = await stage(reviewer, "approved_for_submission");
      await expect(panel).toContainText("Source freshness: CURRENT");
      const notice = reviewer.getByRole("button", {
        name: "Dismiss notification",
        exact: true,
      });
      if (await notice.count()) await notice.last().click();
      await panel.screenshot({
        path: `${screenshots}/${country}-business-deadline-reviewed.png`,
      });
      const retained = structuredClone(paper.body);
      const protectedUpload = await page.request.post(
        `/api/backend/${audit}/evidence-files/${calendarRecord}`,
        {
          headers,
          multipart: {
            file: {
              name: "SYNTHETIC-forbidden-approved-calendar-replacement.txt",
              mimeType: "text/plain",
              buffer: Buffer.from(
                "SYNTHETIC approved evidence must be reopened before replacing original bytes",
              ),
            },
          },
        },
      );
      expect(protectedUpload.status(), await protectedUpload.text()).toBe(409);
      documents.calendar = await action(
        reviewer.request,
        audit,
        documents.calendar,
        "reopen",
      );
      await upload(
        calendarRecord,
        `SYNTHETIC-${country}-business-calendar-replacement.txt`,
        Buffer.from(
          "SYNTHETIC calendar correction requires new independent review and a recalculated deadline",
        ),
      );
      const historical: Paper = await get(`${audit}/records/${paper.id}`);
      expect(historical.body).toEqual(retained);
      panel = await open(reviewer);
      await expect(panel).toContainText("Source freshness: STALE");
      await panel
        .getByLabel("Actual submission evidence record ID", { exact: true })
        .fill(documents.readiness.id);
      await expect(
        panel.getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        }),
      ).toBeDisabled();
      await expect(panel).toContainText("2026-07-06");
      await panel.screenshot({
        path: `${screenshots}/${country}-business-calendar-replaced-stale.png`,
      });
      const comparisonDocs: Record<string, Paper> = {};
      for (const role of ["rule", "facts"]) {
        const original = await evidence(
          `SYNTHETIC-${country}-later-of-${role}.txt`,
          Buffer.from(
            `SYNTHETIC ${role}: notice 2026-12-01 plus one month versus period end 2026-12-31 plus three months; explicit later-of policy, not statutory qualification`,
          ),
        );
        let record: Paper = await get(`${audit}/records/${original.record}`);
        record = await action(page.request, audit, record, "submit");
        comparisonDocs[role] = await action(
          reviewer.request,
          audit,
          record,
          "approve",
        );
      }
      const comparisonBody = {
        ...Object.fromEntries(
          Object.entries(paper.body).filter(
            ([key]) =>
              !["review_stage", "review_cycle", "review_approvers"].includes(
                key,
              ),
          ),
        ),
        filing_stage: "preparing",
        source_url: "https://synthetic.invalid/later-of-policy",
        required_evidence:
          "Independent original policy, both dated event facts and readiness evidence",
        deadline: null,
        calendar_evidence_id: null,
        obligation_period_start: "2026-01-01",
        obligation_period_end: "2026-12-31",
        rule_evidence_id: comparisonDocs.rule.id,
        fact_evidence_ids: [comparisonDocs.facts.id],
        entity_facts: { notice: "2026-12-01", period_end: "2026-12-31" },
        deadline_rule: {
          identifier: "SYN-notice",
          version: 1,
          effective_from: "2026-01-01",
          trigger: "2026-12-01",
          date_basis: "specified_event",
          months_after: 1,
          timezone: country === "AE" ? "Asia/Dubai" : "Asia/Kolkata",
          later_of: [
            {
              identifier: "SYN-period",
              trigger: "2026-12-31",
              date_basis: "period_end",
              months_after: 3,
            },
          ],
        },
      };
      const comparisonReference = `SYN-LATER-OF-${country}`;
      paper = await post(page.request, `${base}/records/obligation`, {
        reference: comparisonReference,
        title: `SYNTHETIC ${country} separately triggered later-of deadline`,
        body: comparisonBody,
      });
      expect(paper.body.deadline).toBe("2027-03-31");
      async function openComparison(actor: Page) {
        await actor.goto(`/grc/${eid}/obligations`);
        await actor
          .getByRole("gridcell", { name: comparisonReference, exact: true })
          .click();
        const readiness = actor.getByRole("region", {
          name: "Filing readiness",
          exact: true,
        });
        const basis = readiness.getByRole("region", {
          name: "Later-of deadline comparison",
          exact: true,
        });
        await expect(basis).toContainText("2026-12-01");
        await expect(basis).toContainText("2026-12-31");
        await expect(basis).toContainText(comparisonDocs.rule.id);
        await expect(basis).toContainText("2027-01-01");
        await expect(basis).toContainText(
          "Calculated base deadline: 2027-03-31",
        );
        await expect(
          basis.getByRole("group", {
            name: "Deadline candidate SYN-period",
            exact: true,
          }),
        ).toContainText("Selected");
        await expect(
          basis.getByRole("group", {
            name: "Deadline candidate SYN-notice",
            exact: true,
          }),
        ).not.toContainText("Selected");
        await expect(readiness).toContainText("2027-03-31");
        return readiness;
      }
      await openComparison(page);
      paper = await stage(page, "under_review");
      paper = await action(page.request, base, paper, "submit");
      paper = await action(reviewer.request, base, paper, "approve");
      panel = await openComparison(reviewer);
      paper = await stage(reviewer, "approved_for_submission");
      await expect(panel).toContainText("Source freshness: CURRENT");
      if (await notice.count()) await notice.last().click();
      await panel.screenshot({
        path: `${screenshots}/${country}-later-of-reviewed.png`,
      });
      const comparisonRetained = structuredClone(paper.body);
      await action(reviewer.request, audit, comparisonDocs.facts, "reopen");
      const unchanged: Paper = await get(`${audit}/records/${paper.id}`);
      expect(unchanged.body).toEqual(comparisonRetained);
      panel = await openComparison(reviewer);
      await expect(panel).toContainText("Source freshness: STALE");
      await panel
        .getByLabel("Actual submission evidence record ID", { exact: true })
        .fill(documents.readiness.id);
      await expect(
        panel.getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        }),
      ).toBeDisabled();
      await panel.screenshot({
        path: `${screenshots}/${country}-later-of-facts-withdrawn-stale.png`,
      });
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

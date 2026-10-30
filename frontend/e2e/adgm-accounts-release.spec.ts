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

test("source-pinned ADGM first accounts timetable retains original authority and calendar evidence", async ({
  page,
  browser,
}) => {
  test.setTimeout(360000);
  const ids = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(ids.synthetic_only).toBe(true);
  const screenshots = "test-results/country-reports";
  mkdirSync(screenshots, { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.AUDITOS_E2E_ORIGIN,
    viewport: { width: 1800, height: 2200 },
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
    for (const country of ["AE"] as const) {
      for (const actor of [page, reviewer]) {
        await actor.goto("/settings/countries");
        await actor
          .getByRole("combobox", { name: "Working country", exact: true })
          .selectOption(country);
      }
      const currency = country === "AE" ? "AED" : "INR";
      const client = await post(page.request, "clients", {
        code: `ADGM-${country}-${Date.now()}`,
        name: "SYNTHETIC ADGM procedure client",
      });
      const entity = await post(page.request, "entities", {
        client_id: client.id,
        name: `SYNTHETIC ${country} ADGM procedure entity`,
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
        name: `SYNTHETIC ${country} ADGM authority procedure`,
        engagement_type: "External Audit",
      });
      const eid = engagement.id,
        audit = `engagements/${eid}/audit`,
        base = `grc/engagements/${eid}`;
      await post(
        page.request,
        `${audit}/team`,
        {
          membership_id: ids.reviewer_membership_id,
          role_id: ids.reviewer_role_id,
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
              "SYNTHETIC independent source and assessed ADGM procedure review; no legal/client qualification",
          },
          200,
        );
      }
      const originals: Record<string, Paper> = {};
      const harness = makeWorkflowHarness(page, eid, ids.tenant_id);
      for (const [role, name] of [
        ["rule", "adgm-companies-consolidated-ver20260626.pdf"],
        ["guidance", "adgm-annual-accounts-v2-20261014.pdf"],
        ["facts", ""],
        ["calendar", ""],
        ["readiness", ""],
        ["duty", ""],
      ]) {
        let recordId: string;
        if (name) {
          const record = await post(page.request, `${audit}/evidence`, {
            reference: `SYN-ADGM-${role}-${Date.now()}`,
            title: `Original public ADGM ${role} PDF for synthetic case`,
            body: { category: "Other", retain_until: "2036-12-31" },
          });
          const response = await page.request.post(
            `/api/backend/${audit}/evidence-files/${record.id}`,
            {
              headers,
              timeout: 120000,
              multipart: {
                file: {
                  name,
                  mimeType: "application/pdf",
                  buffer: readFileSync(
                    `../docs/country-workflows/authority-references/adgm-accounts-2026-10-31/${name}`,
                  ),
                },
              },
            },
          );
          expect(response.status(), await response.text()).toBe(201);
          expect(
            (await response.json()).scan_status,
            `Original source ${name} requires a complete clean scanner verdict`,
          ).toBe("CLEAN");
          recordId = record.id;
        } else {
          const file = await harness.evidence(
            `SYNTHETIC-ADGM-${role}.txt`,
            Buffer.from(
              `SYNTHETIC independently assessed ${role}; fictional company, explicitly zero-holiday calendar and readiness; no real client or professional qualification`,
            ),
          );
          recordId = file.record;
        }
        let record: Paper = await get(`${audit}/records/${recordId}`);
        record = await action(page.request, audit, record, "submit");
        originals[role] = await action(
          reviewer.request,
          audit,
          record,
          "approve",
        );
      }
      const reference = "SYN-ADGM-FIRST-ACCOUNTS";
      const body = JSON.parse(
        readFileSync(
          "../docs/country-workflows/sample-inputs/SYNTHETIC-adgm-accounts/long-first-period.json",
          "utf8",
        ),
      );
      Object.assign(body, {
        owner_id: ids.preparer_user_id,
        entity_id: entity.id,
        rule_evidence_id: originals.rule.id,
        adgm_guidance_evidence_id: originals.guidance.id,
        calendar_evidence_id: originals.calendar.id,
        fact_evidence_ids: [originals.facts.id],
        readiness_evidence_ids: [originals.readiness.id],
        reviewer_id: ids.reviewer_user_id,
        filing_stage: "preparing",
      });
      const swapped = {
        ...body,
        rule_evidence_id: originals.guidance.id,
        adgm_guidance_evidence_id: originals.rule.id,
      };
      await post(
        page.request,
        `${base}/records/obligation`,
        { reference, title: "SYNTHETIC swapped ADGM sources", body: swapped },
        409,
      );
      let paper: Paper = await post(
        page.request,
        `${base}/records/obligation`,
        {
          reference,
          title: "SYNTHETIC source-pinned ADGM long first accounts",
          body,
        },
      );
      expect(paper.body.deadline).toBe("2028-06-30");
      paper = await post(
        page.request,
        `${base}/obligations/${paper.id}/filing-stage`,
        { version: paper.version, stage: "under_review" },
        200,
      );
      paper = await action(page.request, base, paper, "submit");
      paper = await action(reviewer.request, base, paper, "approve");
      async function open() {
        await reviewer.goto(`/grc/${eid}/obligations`);
        await reviewer
          .getByRole("gridcell", { name: reference, exact: true })
          .click();
        const result = reviewer.getByRole("region", {
          name: "ADGM accounts timetable assessment",
          exact: true,
        });
        await expect(result).toContainText("TIMETABLE ON ASSESSED FACTS");
        await expect(result).toContainText("2026-09-30 to 2027-12-31");
        await expect(result).toContainText("first long");
        await expect(
          reviewer.getByRole("region", {
            name: "Filing readiness",
            exact: true,
          }),
        ).toContainText("2028-06-30");
        return result;
      }
      let result = await open();
      const filing = reviewer.getByRole("region", {
        name: "Filing readiness",
        exact: true,
      });
      await filing
        .getByRole("combobox", { name: "Next filing stage", exact: true })
        .selectOption("approved_for_submission");
      const approved = reviewer.waitForResponse(
        (r) =>
          r.url().includes(`/obligations/${paper.id}/filing-stage`) &&
          r.request().method() === "POST",
      );
      await filing
        .getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        })
        .click();
      const response = await approved;
      expect(response.status(), await response.text()).toBe(200);
      paper = await response.json();
      await expect(result).toContainText("Source freshness: CURRENT");
      const notice = reviewer.getByRole("button", {
        name: "Dismiss notification",
        exact: true,
      });
      if (await notice.count()) await notice.last().click();
      await result.screenshot({
        path: `${screenshots}/${country}-ADGM-procedure-reviewed.png`,
      });
      const retained = structuredClone(paper.body);
      await action(reviewer.request, audit, originals.calendar, "reopen");
      expect((await get(`${audit}/records/${paper.id}`)).body).toEqual(
        retained,
      );
      result = await open();
      await expect(result).toContainText("Source freshness: STALE");
      await expect(result.getByRole("alert")).toContainText(
        "Reassess the original source documents",
      );
      await filing
        .getByLabel("Actual submission evidence record ID", { exact: true })
        .fill(originals.readiness.id);
      await expect(
        filing.getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        }),
      ).toBeDisabled();
      await result.screenshot({
        path: `${screenshots}/${country}-ADGM-calendar-withdrawn-stale.png`,
      });
      // Re-review this same original for a new v2 obligation; the historical v1 body stays stale.
      let calendar = await get(`${audit}/records/${originals.calendar.id}`);
      calendar = await action(page.request, audit, calendar, "submit");
      originals.calendar = await action(
        reviewer.request,
        audit,
        calendar,
        "approve",
      );
      const dutyBody = JSON.parse(
        readFileSync(
          "../docs/country-workflows/sample-inputs/SYNTHETIC-adgm-filing-duty/supporting-documents.json",
          "utf8",
        ),
      );
      Object.assign(dutyBody, {
        owner_id: ids.preparer_user_id,
        entity_id: entity.id,
        rule_evidence_id: originals.rule.id,
        adgm_guidance_evidence_id: originals.guidance.id,
        calendar_evidence_id: originals.calendar.id,
        fact_evidence_ids: [originals.facts.id, originals.duty.id],
        readiness_evidence_ids: [originals.readiness.id],
        reviewer_id: ids.reviewer_user_id,
        filing_stage: "preparing",
      });
      for (const fact of dutyBody.adgm_accounts_scope.filing_duty_checks
        .facts) {
        fact.evidence_ids =
          fact.answer === "unassessed" ? [] : [originals.duty.id];
      }
      const pendingBody = structuredClone(dutyBody);
      pendingBody.adgm_accounts_scope.filing_duty_checks.facts =
        pendingBody.adgm_accounts_scope.filing_duty_checks.facts.filter(
          (fact: { key: string }) => fact.key !== "guarantee_authenticated",
        );
      pendingBody.adgm_accounts_scope.filing_duty = "unassessed";
      pendingBody.jurisdiction_scope.applicability = "potential";
      let pending = await post(page.request, `${base}/records/obligation`, {
        reference: "SYN-ADGM-DUTY-PENDING",
        title: "SYNTHETIC missing guarantee assessment",
        body: pendingBody,
      });
      pending = await action(page.request, base, pending, "submit");
      await post(
        reviewer.request,
        `${base}/records/${pending.id}/actions`,
        {
          version: pending.version,
          action: "approve",
          comments: "SYNTHETIC missing guarantee cannot support approval",
        },
        409,
      );
      const dutyReference = "SYN-ADGM-DUTY-SUPPORT";
      let dutyPaper = await post(page.request, `${base}/records/obligation`, {
        reference: dutyReference,
        title: "SYNTHETIC separately required dormant supporting filings",
        body: dutyBody,
      });
      dutyPaper = await post(
        page.request,
        `${base}/obligations/${dutyPaper.id}/filing-stage`,
        { version: dutyPaper.version, stage: "under_review" },
        200,
      );
      dutyPaper = await action(page.request, base, dutyPaper, "submit");
      dutyPaper = await action(reviewer.request, base, dutyPaper, "approve");
      async function openDuty() {
        await reviewer.goto(`/grc/${eid}/obligations`);
        await reviewer
          .getByRole("gridcell", { name: dutyReference, exact: true })
          .click();
        const panel = reviewer.getByRole("region", {
          name: "ADGM filing duty conditions",
          exact: true,
        });
        await expect(panel).toContainText(
          "Selected procedure: dormant subsidiary supporting documents",
        );
        await expect(panel).toContainText(
          "Individual-accounts exemption does not remove the five supporting-document filings",
        );
        await expect(
          panel
            .getByRole("list", {
              name: "Dormant subsidiary supporting documents",
              exact: true,
            })
            .getByRole("listitem"),
        ).toHaveCount(5);
        await expect(panel).toContainText(
          "Authenticated parent guarantee statement under section 425: unassessed",
        );
        return panel;
      }
      let dutyPanel = await openDuty();
      await filing
        .getByRole("combobox", { name: "Next filing stage", exact: true })
        .selectOption("approved_for_submission");
      const dutyApproval = reviewer.waitForResponse(
        (r) =>
          r.url().includes(`/obligations/${dutyPaper.id}/filing-stage`) &&
          r.request().method() === "POST",
      );
      await filing
        .getByRole("button", {
          name: "Record evidenced filing stage",
          exact: true,
        })
        .click();
      const dutyApproved = await dutyApproval;
      expect(dutyApproved.status(), await dutyApproved.text()).toBe(200);
      dutyPaper = await dutyApproved.json();
      await expect(
        reviewer.getByRole("region", {
          name: "ADGM accounts timetable assessment",
          exact: true,
        }),
      ).toContainText("Source freshness: CURRENT");
      await dutyPanel
        .getByRole("heading", {
          name: "ADGM filing duty conditions",
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      await reviewer.screenshot({
        path: `${screenshots}/${country}-ADGM-duty-support-reviewed.png`,
      });
      await dutyPanel
        .getByRole("list", {
          name: "Dormant subsidiary supporting documents",
          exact: true,
        })
        .screenshot({
          path: `${screenshots}/${country}-ADGM-duty-five-supporting-documents.png`,
        });
      await dutyPanel
        .getByText(/Review source-bound filing-duty conditions/)
        .click();
      const guaranteeCheck = dutyPanel
        .getByRole("list", { name: "Retained filing duty checks", exact: true })
        .getByRole("listitem")
        .filter({
          has: reviewer.getByText("guarantee authenticated", { exact: true }),
        });
      await guaranteeCheck.screenshot({
        path: `${screenshots}/${country}-ADGM-duty-guarantee-source.png`,
      });
      const dutyRetained = structuredClone(dutyPaper.body);
      await action(reviewer.request, audit, originals.duty, "reopen");
      expect((await get(`${audit}/records/${dutyPaper.id}`)).body).toEqual(
        dutyRetained,
      );
      dutyPanel = await openDuty();
      await expect(
        reviewer.getByRole("region", {
          name: "ADGM accounts timetable assessment",
          exact: true,
        }),
      ).toContainText("Source freshness: STALE");
      await dutyPanel
        .getByRole("heading", {
          name: "ADGM filing duty conditions",
          exact: true,
        })
        .scrollIntoViewIfNeeded();
      await reviewer.screenshot({
        path: `${screenshots}/${country}-ADGM-duty-conditions-withdrawn-stale.png`,
      });
      await filing
        .getByLabel("Actual submission evidence record ID", { exact: true })
        .fill(originals.readiness.id);
      const dutyAction = filing.getByRole("button", {
        name: "Record evidenced filing stage",
        exact: true,
      });
      await expect(dutyAction).toBeDisabled();
      await dutyAction.scrollIntoViewIfNeeded();
      await reviewer.screenshot({
        path: `${screenshots}/${country}-ADGM-duty-stale-actions.png`,
      });
      expect((await get(`entities/${entity.id}`)).country).toBe(country);
    }
    expect(errors).toEqual([]);
  } finally {
    await context.close();
  }
});

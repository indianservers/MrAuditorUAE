import { expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

type Line = Record<string, unknown> & {
  reference: string;
  statement: string;
  kind: string;
  amount: string;
};
type Paper = {
  current: {
    members: {
      member: string;
      lines: Line[];
      source_evidence_version_id: string;
      source_sha256: string;
    }[];
  };
};

export async function runTaxGroupWorkpaperBrowser(
  page: Page,
  reviewer: Page,
  eid: string,
  tenant: string,
  screenshots: string,
) {
  const { headers, prefix, evidence, upload } = makeWorkflowHarness(
    page,
    eid,
    tenant,
  );
  const folder =
    "../docs/country-workflows/authority-references/uae-tax-group-afs-2026-10-31";
  const rule = await evidence(
    "original-fta7.pdf",
    readFileSync(`${folder}/fta-decision7-2025-unofficial-english.pdf`),
  );
  const clarification = await evidence(
    "original-ctp007.pdf",
    readFileSync(
      `${folder}/ctp007-tax-group-financial-statements-bilingual.pdf`,
    ),
  );
  const adoption = await evidence(
    "SYNTHETIC-tax-group-adoption.txt",
    Buffer.from(
      "SYNTHETIC independently assessed FTA7/CTP007 adoption for the full completed FY2025. No actual client or legal qualification.",
    ),
  );
  const paper = JSON.parse(
    readFileSync(
      "../docs/country-workflows/sample-inputs/SYNTHETIC-tax-group-statements/mapping.template.json",
      "utf8",
    ),
  ) as Paper;
  for (const [index, member] of paper.current.members.entries()) {
    member.lines.push(
      ...Array.from({ length: 55 }, (_, i) => ({
        ...member.lines[4],
        reference: `ZERO-${index}-${i}`,
        code: `ZERO-${index}-${i}`,
        label: `SYNTHETIC zero source ${index}-${i}`,
        amount: "0",
      })),
    );
    const csv =
      [
        ["reference", "statement", "kind", "amount"],
        ...member.lines.map((line) => [
          line.reference,
          line.statement,
          line.kind,
          line.amount,
        ]),
      ]
        .map((row) => row.map((value) => JSON.stringify(value)).join(","))
        .join("\n") + "\n";
    const original = await evidence(
      `SYNTHETIC-member-${member.member}.csv`,
      Buffer.from(csv),
    );
    member.source_evidence_version_id = original.version.id;
    member.source_sha256 = original.version.sha256;
  }
  const mapping = await evidence(
    "SYNTHETIC-independent-tax-group-mapping.json",
    Buffer.from(JSON.stringify(paper)),
  );
  for (let i = 0; i < 26; i++)
    await evidence(
      `SYNTHETIC-later-original-${i}.txt`,
      Buffer.from(
        `SYNTHETIC distinct later evidence choice ${i}; not group source evidence`,
      ),
    );
  await page.goto(`/intelligence/${eid}/country-workflow`);
  await page
    .getByText("Prepare UAE Tax Group statement workpaper", { exact: true })
    .click();
  for (const [label, value] of [
    ["Tax Group workpaper title", "SYNTHETIC retained Tax Group FY2025"],
    ["Tax Group assessed on", "2026-10-01"],
    ["Tax Group adopted from", "2025-01-01"],
    ["Tax Group adopted through", "2026-12-31"],
    [
      "Tax Group source adoption assessment",
      "SYNTHETIC separately adopted complete-period FTA7/CTP007 sources and member mapping; no actual legal qualification",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByRole("combobox", { name: "Tax Group operative changes", exact: true })
    .selectOption("assessed_none");
  await page
    .getByRole("combobox", { name: "Tax Group original FTA7 PDF", exact: true })
    .selectOption(rule.version.id);
  await page
    .getByRole("combobox", {
      name: "Tax Group original CTP007 PDF",
      exact: true,
    })
    .selectOption(clarification.version.id);
  for (const [label, id] of [
    ["Tax Group legal adoption evidence", adoption.version.id],
    ["Tax Group retained statement mapping", mapping.version.id],
  ]) {
    await page
      .getByRole("button", { name: `Next ${label.toLowerCase()}`, exact: true })
      .click();
    const select = page.getByRole("combobox", { name: label, exact: true });
    await select.selectOption(id);
    await page
      .getByRole("button", {
        name: `Previous ${label.toLowerCase()}`,
        exact: true,
      })
      .click();
    await expect(select).toHaveValue(id);
  }
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/uae-tax-group-statements`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Prepare Tax Group workpaper", exact: true })
    .click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(201);
  const result = await response.json();
  expect(result.body.tax_group_totals[0].assets).toBe("220");
  expect(result.collection_totals.tax_group_source_lines).toBe(131);
  expect(result.body.validation.ready).toBe(false);
  expect(result.body.statutory_issuance).toBe(false);
  const self = await page.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments: "SYNTHETIC self approval is prohibited",
      },
    },
  );
  expect(self.status()).toBe(403);
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${result.id}`,
  );
  await reviewer
    .getByLabel("Review / exception rationale", { exact: true })
    .fill(
      "SYNTHETIC independent review of the retained arithmetic workpaper only; no statutory issue, audit opinion or submission",
    );
  const reviewing = reviewer.waitForResponse(
    (r) =>
      r.url().endsWith(`/events/${result.id}/review`) &&
      r.request().method() === "POST",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .click();
  const approval = await reviewing;
  expect(approval.status(), await approval.text()).toBe(201);
  const reviewed = await approval.json();
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("REVIEWED", { exact: true })).toBeVisible();
  const region = reviewer.getByRole("region", {
    name: "UAE Tax Group statement workpaper",
    exact: true,
  });
  await expect(region).toContainText("does not establish statutory readiness");
  await reviewer
    .getByRole("region", { name: "current Tax Group totals", exact: true })
    .screenshot({ path: `${screenshots}/AE-tax-group-workpaper-totals.png` });
  const position = region.getByRole("region", {
    name: "current position statement",
    exact: true,
  });
  await expect(position).toContainText("220");
  await position.screenshot({
    path: `${screenshots}/AE-tax-group-workpaper-position.png`,
  });
  await region
    .locator("summary")
    .filter({ hasText: /^Tax Group original source contributions$/ })
    .click();
  const sources = region.getByRole("region", {
    name: "Tax Group original source contributions",
    exact: true,
  });
  for (let offset = 25; offset <= 125; offset += 25) {
    await sources
      .getByRole("button", {
        name: "Next tax group original source contributions",
        exact: true,
      })
      .click();
    await expect(sources).toContainText(
      `Records ${offset + 1}–${Math.min(offset + 25, 131)} of 131`,
    );
  }
  await expect(sources).toContainText("closing-equity");
  await sources.screenshot({
    path: `${screenshots}/AE-tax-group-workpaper-last-source-page.png`,
  });
  await region
    .locator("summary")
    .filter({ hasText: /^Tax Group retained documents$/ })
    .click();
  await region
    .locator("summary")
    .filter({ hasText: /^Original files on this page \(6\)$/ })
    .click();
  const originalDownload = reviewer.waitForEvent("download");
  await region
    .getByRole("button", { name: "Download Tax Group evidence 1", exact: true })
    .click();
  const original = await originalDownload;
  expect(readFileSync((await original.path())!)).toEqual(
    readFileSync(`${folder}/fta-decision7-2025-unofficial-english.pdf`),
  );
  const downloading = reviewer.waitForEvent("download");
  await reviewer
    .getByRole("button", { name: "Export XLSX", exact: true })
    .click();
  expect((await downloading).suggestedFilename()).toContain(".xlsx");
  await upload(
    mapping.record,
    "SYNTHETIC-revised-mapping.json",
    Buffer.from(
      JSON.stringify({
        ...paper,
        group_reference: "SYNTHETIC revised group fact mapping",
      }),
    ),
  );
  const historical = await reviewer.request.get(
    `/api/backend/${prefix}/events/${reviewed.id}`,
    { headers },
  );
  expect(historical.status()).toBe(200);
  expect((await historical.json()).freshness).toBe("STALE");
  await reviewer.goto(
    `/intelligence/${eid}/country-workflow?event=${reviewed.id}`,
  );
  await expect(reviewer.getByText("STALE", { exact: true })).toBeVisible();
  await expect(
    reviewer.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  await reviewer
    .getByRole("region", {
      name: "Retained result status and exports",
      exact: true,
    })
    .screenshot({
      path: `${screenshots}/AE-tax-group-workpaper-mapping-stale.png`,
    });
  await expect(reviewer.getByRole("alert")).toContainText(
    "any previous review does not approve the current evidence or rules",
  );
  await reviewer
    .getByRole("button", { name: "Independent approval", exact: true })
    .screenshot({
      path: `${screenshots}/AE-tax-group-workpaper-stale-approval-disabled.png`,
    });
}

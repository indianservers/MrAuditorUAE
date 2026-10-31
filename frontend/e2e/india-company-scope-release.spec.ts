import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { makeWorkflowHarness } from "./msme-browser-workflow";

test("India scope form preserves unknown facts and blocks unresolved adoption", async ({
  page,
}) => {
  test.setTimeout(120000);
  const ids = JSON.parse(
    readFileSync("../.local-runtime/release-smoke/identities.json", "utf8"),
  );
  expect(ids.synthetic_only).toBe(true);
  if (!process.env.AUDITOS_SMOKE_EMAIL || !process.env.AUDITOS_SMOKE_PASSWORD)
    throw new Error("Explicit isolated synthetic identity required");
  await page.goto("/login");
  await page.getByLabel("Email address").fill(process.env.AUDITOS_SMOKE_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.AUDITOS_SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/settings/countries");
  await page
    .getByRole("combobox", { name: "Working country", exact: true })
    .selectOption("IN");
  const headers = {
    "X-Tenant-ID": ids.tenant_id,
    Origin: process.env.AUDITOS_E2E_ORIGIN!,
  };
  async function post(path: string, data: unknown) {
    const response = await page.request.post(`/api/backend/${path}`, {
      headers,
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }
  const client = await post("clients", {
    code: `IN-SCOPE-${Date.now()}`,
    name: "SYNTHETIC India company scope",
  });
  const entity = await post("entities", {
    client_id: client.id,
    name: "SYNTHETIC India company",
    country: "IN",
    jurisdiction: "Synthetic",
    functional_currency: "INR",
    presentation_currency: "INR",
  });
  const period = await post("financial-periods", {
    entity_id: entity.id,
    start_date: "2025-04-01",
    end_date: "2026-03-31",
  });
  const eng = await post("engagements", {
    entity_id: entity.id,
    period_id: period.id,
    name: "SYNTHETIC India scope browser",
    engagement_type: "External Audit",
  });
  const { evidence, prefix } = makeWorkflowHarness(page, eng.id, ids.tenant_id);
  const folder =
    "../docs/country-workflows/authority-references/india-company-reporting-2026-10-31";
  const originals = [
    ["Small-company definition original PDF", "small-company-gsr880-2025.pdf"],
    [
      "SO 4588(E) CARO commencement original PDF",
      "caro2020-commencement-amendment.pdf",
    ],
    ["GSR 583(E) IFC original PDF", "ifc-private-gsr583-2017-original.pdf"],
  ];
  const choices: [string, string][] = [];
  for (const [label, file] of originals)
    choices.push([
      label,
      (await evidence(file, readFileSync(`${folder}/${file}`))).version.id,
    ]);
  // These retained guidance copies exercise an UNRESOLVED workpaper only.
  // They are explicitly not the required Act/order/corrigendum originals.
  const guide = readFileSync(`${folder}/caro2020-icai-guidance-2020.pdf`);
  for (const [index, label] of [
    "Companies Act original PDF",
    "CARO 2020 original order PDF",
    "SO 2218(E) IFC corrigendum original PDF",
  ].entries()) {
    const source = await evidence(
      `SYNTHETIC-unqualified-legal-source-${index}.pdf`,
      Buffer.concat([
        guide,
        Buffer.from(`\n% SYNTHETIC unqualified role ${index}\n`),
      ]),
    );
    choices.push([label, source.version.id]);
  }
  for (const [label, role] of [
    ["Separate India legal adoption evidence", "adoption"],
    ["Separate India company facts evidence", "facts"],
  ]) {
    choices.push([
      label,
      (
        await evidence(
          `SYNTHETIC-${role}.txt`,
          Buffer.from(
            `SYNTHETIC unresolved ${role}; no original legal qualification or client evidence`,
          ),
        )
      ).version.id,
    ]);
  }
  await page.goto(`/intelligence/${eng.id}/country-workflow`);
  await page
    .getByText("Assess India company audit, CARO and IFC reporting scope", {
      exact: true,
    })
    .click();
  for (const [label, value] of [
    ["India scope assessment title", "SYNTHETIC unresolved India scope"],
    ["India company registration reference", "SYN-IN-SCOPE"],
    ["India financial period start", "2025-04-01"],
    ["India financial period end", "2026-03-31"],
    ["India report assessment date", "2026-06-30"],
    ["India rules adopted from", "2025-04-01"],
    ["India rules adopted through", "2026-06-30"],
    [
      "India company facts assessment",
      "SYNTHETIC all entity facts remain unassessed",
    ],
    [
      "India legal source-chain adoption assessment",
      "SYNTHETIC original source chain not yet independently adopted",
    ],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  for (const [label, id] of choices)
    await page.getByLabel(label, { exact: true }).selectOption(id);
  const pending = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/${prefix}/india-company-reporting-scope`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Prepare India reporting scope assessment",
      exact: true,
    })
    .click();
  const response = await pending;
  expect(response.status(), await response.text()).toBe(201);
  const result = await response.json();
  expect(result.body.rows[0].companies_act_section139_audit).toBeNull();
  expect(result.body.ready_for_statutory_issue).toBe(false);
  expect(result.body.blocked).toBe(true);
  const summary = page.getByRole("region", {
    name: "India company reporting scope summary",
    exact: true,
  });
  await expect(summary).toContainText("Companies Act section 139 audit");
  await expect(summary).toContainText("Unresolved");
  await expect(
    page.getByRole("button", { name: "Independent approval", exact: true }),
  ).toBeDisabled();
  const review = await page.request.post(
    `/api/backend/${prefix}/events/${result.id}/review`,
    {
      headers,
      data: {
        expected_version: result.version,
        action: "approve",
        comments: "SYNTHETIC unresolved scope must not be approved",
      },
    },
  );
  expect([403, 409]).toContain(review.status());
  mkdirSync("test-results/country-reports", { recursive: true });
  await summary.screenshot({
    path: "test-results/country-reports/IN-company-scope-unresolved.png",
  });
});

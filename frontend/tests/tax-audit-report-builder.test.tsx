import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StatutoryReportBuilder } from "@/features/statutory-report-builder";
const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  tenant: "tenant",
  country: "IN",
  detail: undefined as unknown,
  presets: undefined as unknown,
}));
vi.mock("@/features/shared", () => ({
  PageHeader: () => <h1>Report designer</h1>,
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select?: (s: typeof state) => unknown) =>
    select ? select(state) : state,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data:
      path === "engagements?limit=100"
        ? {
            items: [
              { id: "one", name: "First" },
              { id: "two", name: "Second" },
            ],
          }
        : path.endsWith("/report-presets")
          ? state.presets
          : path.endsWith("/events/template")
            ? state.detail
            : undefined,
  }),
  useAction: () => ({ mutateAsync: state.mutate, isPending: false }),
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: {
      items: [
        {
          id: "company-scope",
          label: "Reviewed company scope",
          kind: "country-workflow",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
        {
          id: "template",
          label: "Retained template",
          kind: "report-template",
          review_status: "UNVERIFIED",
        },
        {
          id: "case",
          label: "Reviewed case",
          kind: "statutory-checklist",
          area: "india-tax-audit",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
      ],
    },
  }),
}));
describe("tax audit report builder", () => {
  it("sends the explicitly assessed scope and clears it when changing engagement", async () => {
    state.mutate.mockReset().mockResolvedValue({ id: "saved" });
    render(<StatutoryReportBuilder />);
    const change = (label: string, value: string) =>
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    change("Engagement", "one");
    change("Report title", "Tax working draft");
    change("Report category", "india-tax-audit");
    change("Block title", "Assessed source narrative");
    fireEvent.click(screen.getByRole("button", { name: "Add content block" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Save template version" }),
    );
    expect(state.mutate).not.toHaveBeenCalled();
    change("Reviewed tax-audit applicability case", "case");
    change("Tax period start", "2026-04-01");
    change("Tax period end", "2027-03-31");
    change("Accounts audited under another law", "no");
    change("Selected tax-audit form", "26");
    change("Form 26 audit-report part", "B");
    fireEvent.click(
      screen.getByRole("button", { name: "Save template version" }),
    );
    await waitFor(() => expect(state.mutate).toHaveBeenCalledOnce());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "regulatory/engagements/one/report-templates",
      body: {
        category: "india-tax-audit",
        tax_audit_scope: {
          applicability_id: "case",
          tax_period_start: "2026-04-01",
          tax_period_end: "2027-03-31",
          audited_under_other_law: false,
          form: "26",
          audit_report_part: "B",
        },
      },
    });
    change("Engagement", "two");
    expect(screen.getByLabelText("Report title")).toHaveValue("");
    expect(screen.getByLabelText("Report category")).toHaveValue(
      "management-letter",
    );
    change("Report category", "india-tax-audit");
    expect(screen.getByLabelText("Tax period start")).toHaveValue("");
    expect(
      screen.getByLabelText("Reviewed tax-audit applicability case"),
    ).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Save template version" }),
    ).toBeDisabled();
  });
});

it("maps a declared authored requirement to a retained draft block and sends its explicit scope", async () => {
  state.mutate.mockReset().mockResolvedValue({ id: "saved" });
  render(<StatutoryReportBuilder />);
  const change = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  change("Engagement", "one");
  change("Report title", "Management communication");
  change("Block title", "Draft communication");
  change(
    "User-authored narrative / commentary",
    "Synthetic authored management communication",
  );
  fireEvent.click(screen.getByRole("button", { name: "Add content block" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Add declared requirement" }),
  );
  change("Requirement title 1", "Communication requirement");
  change("Requirement disposition 1", "REQUIRED");
  change(
    "Applicability and source basis 1",
    "Synthetic authored communication; external evidence not required for this item",
  );
  fireEvent.click(
    screen.getByLabelText("Evidence/calculation source required for item 1"),
  );
  const existing = screen.getByRole("group", {
    name: "Coverage for Draft communication",
  });
  fireEvent.click(within(existing).getByLabelText("Communication requirement"));
  change("Requirement scope completeness assessment", "assessed");
  change(
    "Requirement scope basis",
    "Synthetic explicit communication scope independently assessed",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalledOnce());
  expect(state.mutate.mock.calls[0][0].body).toMatchObject({
    requirements_assessed: true,
    requirements_basis:
      "Synthetic explicit communication scope independently assessed",
    requirements: [
      {
        key: "item-1",
        title: "Communication requirement",
        disposition: "REQUIRED",
        source_required: false,
      },
    ],
    blocks: [{ requirement_keys: ["item-1"] }],
  });
});

beforeEach(() => {
  state.detail = undefined;
  state.presets = undefined;
});

it("loads an unassessed operational preset, locks mandatory source coverage and resets it on engagement change", () => {
  state.presets = {
    country: "AE",
    items: [
      {
        id: "uae-vat201-review:aggregate-14/1",
        title: "VAT201 operational test preset",
        category: "vat",
        kind: "vat201-comparison",
        allow_not_applicable: false,
        requirements: [1, 2].map((n) => ({
          key: `vat201.box.${n}`,
          title: `VAT201 Box ${n}`,
          disposition: "UNASSESSED",
          source_required: true,
          basis: "Assess the retained reviewed comparison",
        })),
        limitations: [],
      },
    ],
  };
  render(<StatutoryReportBuilder />);
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "one" },
  });
  fireEvent.change(screen.getByLabelText("Report category"), {
    target: { value: "vat" },
  });
  fireEvent.change(screen.getByLabelText("Operational report preset"), {
    target: { value: "uae-vat201-review:aggregate-14/1" },
  });
  expect(screen.getByLabelText("Requirement reference 1")).toHaveValue(
    "vat201.box.1",
  );
  expect(screen.getByLabelText("Requirement reference 1")).toBeDisabled();
  expect(
    screen.getByLabelText("Evidence/calculation source required for item 1"),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Remove requirement 1" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Add declared requirement" }),
  ).toBeDisabled();
  expect(
    screen.getByLabelText("Requirement scope completeness assessment"),
  ).toHaveValue("unassessed");
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "two" },
  });
  fireEvent.change(screen.getByLabelText("Report category"), {
    target: { value: "vat" },
  });
  expect(screen.getByLabelText("Operational report preset")).toHaveValue("");
  expect(
    screen.queryByLabelText("Requirement reference 1"),
  ).not.toBeInTheDocument();
});
it("shows retained requirement gaps to reviewers and blocks approval without editing a draft", () => {
  state.detail = {
    id: "template",
    version: 1,
    freshness: "CURRENT",
    body: {
      title: "Source report",
      category: "management-letter",
      blocks: [],
      review_status: "UNVERIFIED",
      requirements_basis: "Synthetic requirement basis",
      requirements_coverage: {
        complete: false,
        source_validation: "RECHECK_BEFORE_REVIEW_OR_GENERATION",
        items: [
          {
            key: "mandatory",
            title: "Source documentation",
            disposition: "REQUIRED",
            status: "MISSING_COVERAGE",
            block_keys: [],
          },
        ],
      },
    },
  };
  render(<StatutoryReportBuilder />);
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "one" },
  });
  fireEvent.change(screen.getByLabelText("Saved template version"), {
    target: { value: "template" },
  });
  expect(
    within(screen.getByLabelText("Retained requirement coverage")).getByText(
      "MISSING_COVERAGE",
    ),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", {
      name: "Record independent template approval",
    }),
  ).toBeDisabled();
});

it("offers the India index only for tax audit and retains evidence for not-applicable items", () => {
  state.presets = {
    country: "IN",
    items: [
      {
        id: "india-form26-index:A/1",
        title: "Form 26 draft evidence index",
        category: "india-tax-audit",
        kind: "form26-index",
        allow_not_applicable: true,
        not_applicable_keys: ["form26.schedule.gst"],
        limitations: ["Draft evidence index only"],
        requirements: [
          {
            key: "form26.report.A",
            title: "Report part A",
            disposition: "UNASSESSED",
            source_required: true,
            basis: "Assess the retained report workpaper",
          },
          {
            key: "form26.schedule.gst",
            title: "GST schedule group",
            disposition: "UNASSESSED",
            source_required: true,
            basis: "Assess the retained GST workpaper",
          },
        ],
      },
    ],
  };
  render(<StatutoryReportBuilder />);
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "one" },
  });
  fireEvent.change(screen.getByLabelText("Report category"), {
    target: { value: "india-tax-audit" },
  });
  fireEvent.change(screen.getByLabelText("Operational report preset"), {
    target: { value: "india-form26-index:A/1" },
  });
  const disposition = screen.getByLabelText("Requirement disposition 2");
  expect(
    within(screen.getByLabelText("Requirement disposition 1")).getByRole(
      "option",
      { name: "Not applicable with reviewed basis" },
    ),
  ).toBeDisabled();
  expect(
    within(disposition).getByRole("option", {
      name: "Not applicable with reviewed basis",
    }),
  ).toBeEnabled();
  fireEvent.change(disposition, { target: { value: "NOT_APPLICABLE" } });
  expect(
    screen.getByLabelText("Evidence/calculation source required for item 2"),
  ).toBeChecked();
  expect(
    screen.getByLabelText("Evidence/calculation source required for item 2"),
  ).toBeDisabled();
  expect(screen.getByLabelText("Source type")).toHaveValue("record");
  expect(screen.getByLabelText("Content type")).toHaveValue(
    "working_paper_reference",
  );
  fireEvent.change(screen.getByLabelText("Report category"), {
    target: { value: "vat" },
  });
  expect(
    screen.queryByLabelText("Operational report preset"),
  ).not.toBeInTheDocument();
});

it("selects the India company applicability preset as a retained regulatory result", () => {
  state.presets = {
    country: "IN",
    items: [
      {
        id: "india-company-scope:standalone/1",
        title: "India standalone company applicability summary",
        category: "india-statutory",
        kind: "india-company-scope-summary",
        allow_not_applicable: false,
        not_applicable_keys: [],
        requirements: [
          {
            key: "company.scope.small_company",
            title: "Small-company classification",
            disposition: "UNASSESSED",
            source_required: true,
            basis: "Retain current reviewed applicability support",
          },
        ],
        limitations: ["Applicability summary only; not a statutory opinion"],
      },
    ],
  };
  render(<StatutoryReportBuilder />);
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "one" },
  });
  fireEvent.change(screen.getByLabelText("Report category"), {
    target: { value: "india-statutory" },
  });
  fireEvent.change(screen.getByLabelText("Operational report preset"), {
    target: { value: "india-company-scope:standalone/1" },
  });
  expect(screen.getByLabelText("Content type")).toHaveValue(
    "regulatory_checklist",
  );
  expect(screen.getByLabelText("Source type")).toHaveValue("intelligence");
  expect(
    screen.getByText("Applicability summary only; not a statutory opinion"),
  ).toBeInTheDocument();
});

it("retains a CARO inventory's reviewed company scope and defaults to linked workpapers", async () => {
  state.mutate.mockReset().mockResolvedValue({ id: "saved" });
  state.presets = {
    country: "IN",
    items: [
      {
        id: "india-caro-index:consolidated/1",
        title: "CARO consolidated inventory",
        category: "caro",
        kind: "caro-index",
        allow_not_applicable: false,
        not_applicable_keys: [],
        limitations: ["Numbered matters only; no opinion qualification"],
        requirements: ["3.xxi", "4.1", "4.2"].map((ref) => ({
          key: "caro." + ref,
          title: ref,
          disposition: "UNASSESSED",
          source_required: true,
          basis: "Retain assessed source workpaper coverage",
        })),
      },
    ],
  };
  render(<StatutoryReportBuilder />);
  const change = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  change("Engagement", "one");
  change("Report title", "SYNTHETIC CARO draft");
  change("Report category", "caro");
  change("Operational report preset", "india-caro-index:consolidated/1");
  expect(screen.getByLabelText("Content type")).toHaveValue(
    "working_paper_reference",
  );
  expect(screen.getByLabelText("Source type")).toHaveValue("record");
  change("Reviewed CARO company-scope result", "company-scope");
  change("Content type", "narrative");
  change("Block title", "SYNTHETIC unassessed draft");
  fireEvent.click(screen.getByRole("button", { name: "Add content block" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalledOnce());
  expect(state.mutate.mock.calls[0][0].body.company_reporting_scope_id).toBe(
    "company-scope",
  );
  expect(state.mutate.mock.calls[0][0].body.requirements).toHaveLength(3);
});

it("saves every expanded field after searching and editing the last field", async () => {
  state.mutate.mockReset().mockResolvedValue({ id: "saved" });
  const requirements = Array.from({ length: 877 }, (_, i) => ({
    key: `form26.field.synthetic.${i + 1}`,
    title: `Synthetic field ${i + 1}`,
    disposition: "UNASSESSED",
    source_required: true,
    basis: "Synthetic retained source mapping assessment",
  }));
  state.presets = {
    country: "IN",
    items: [
      {
        id: "india-form26-index:B/2",
        title: "Published-field inventory part B",
        category: "india-tax-audit",
        kind: "form26-index",
        allow_not_applicable: true,
        not_applicable_keys: [],
        limitations: ["Unqualified source field inventory"],
        requirements,
      },
    ],
  };
  render(<StatutoryReportBuilder />);
  const change = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  for (const [label, value] of [
    ["Engagement", "one"],
    ["Report title", "SYNTHETIC complete inventory"],
    ["Report category", "india-tax-audit"],
    ["Operational report preset", "india-form26-index:B/2"],
    ["Reviewed tax-audit applicability case", "case"],
    ["Tax period start", "2026-04-01"],
    ["Tax period end", "2027-03-31"],
    ["Accounts audited under another law", "no"],
    ["Selected tax-audit form", "26"],
    ["Form 26 audit-report part", "B"],
    ["Search report requirements", "form26.field.synthetic.877"],
    [
      "Applicability and source basis 877",
      "Independently assessed final field evidence scope",
    ],
    ["Search requirements for this block", "Synthetic field 877"],
  ])
    change(label, value);
  const group = screen.getByRole("group", {
    name: "Requirements covered by this block",
  });
  fireEvent.click(within(group).getByLabelText("Synthetic field 877"));
  change("Content type", "narrative");
  change("Block title", "SYNTHETIC field draft");
  change(
    "User-authored narrative / commentary",
    "Synthetic draft awaiting source workpaper review",
  );
  fireEvent.click(screen.getByRole("button", { name: "Add content block" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalledOnce());
  const body = state.mutate.mock.calls[0][0].body;
  expect(body.requirements).toHaveLength(877);
  expect(body.requirements.slice(0, 876)).toEqual(requirements.slice(0, 876));
  expect(body.requirements[876].basis).toBe(
    "Independently assessed final field evidence scope",
  );
  expect(body.blocks[0].requirement_keys).toEqual([
    "form26.field.synthetic.877",
  ]);
});

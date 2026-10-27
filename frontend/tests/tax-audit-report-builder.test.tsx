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

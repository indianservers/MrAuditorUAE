import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Paper } from "@/features/grc-forms";
const mock = vi.hoisted(() => ({
  record: {} as Paper,
  check: undefined as unknown,
  fetching: false,
  error: null as unknown,
  calls: [] as { path: string; enabled: boolean }[],
}));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutate: vi.fn(), isPending: false }),
  useAPI: (path: string, enabled = true) => {
    mock.calls.push({ path, enabled });
    if (path.endsWith("/workspace"))
      return {
        data: {
          permissions: [
            "prepare",
            "review",
            "compliance.manage",
            "compliance.approve",
          ],
          kind_permissions: { obligation: ["prepare", "review"] },
          schemas: {},
        },
      };
    if (path.includes("compliance-calendar"))
      return { data: mock.check, isFetching: mock.fetching, error: mock.error };
    if (path.includes("/records/obligation?"))
      return { data: { items: [mock.record], total: 1 } };
    return { data: { items: [], total: 0 } };
  },
}));
vi.mock("@/features/shared", () => ({ PageHeader: () => <div /> }));
vi.mock("@/components/grids/financial-data-grid", () => ({
  column: () => ({}),
  FinancialDataGrid: ({
    rows,
    onSelect,
  }: {
    rows: Paper[];
    onSelect: (row: Paper) => void;
  }) => (
    <div>
      {rows.map((row) => (
        <button key={row.id} onClick={() => onSelect(row)}>
          Open {row.reference}
        </button>
      ))}
    </div>
  ),
}));
import { GRCStudio } from "@/features/grc-studio";
beforeEach(() => {
  mock.record = {
    id: "R",
    version: 7,
    reference: "SYN-SCOPE",
    title: "Synthetic obligation",
    kind: "grc-obligation",
    status: "APPROVED",
    body: { filing_stage: "under_review", jurisdiction: "AE" },
  };
  mock.check = undefined;
  mock.error = null;
  mock.fetching = true;
  mock.calls = [];
});
function check(version: number, freshness = "CURRENT", reassessment = false) {
  return {
    items: [
      {
        record_id: "R",
        version,
        freshness,
        calendar_state: "OPEN",
        reassessment_required: reassessment,
      },
    ],
  };
}

it("shows the server comparison only for the selected version and blocks a mismatched saved deadline", () => {
  mock.record.body = {
    filing_stage: "under_review",
    deadline: "2027-03-31",
    deadline_rule: {
      identifier: "SYN-notice",
      trigger: "2026-12-01",
      months_after: 1,
      later_of: [
        { identifier: "SYN-period", trigger: "2026-12-31", months_after: 3 },
      ],
    },
  };
  const trace = {
    state: "CONSISTENT_WITH_SAVED_RULE",
    selected_before_rolling: "2027-03-31",
    calculated_deadline: "2027-03-31",
    convention: "calendar",
    candidates: [
      {
        identifier: "SYN-notice",
        unadjusted_date: "2027-01-01",
        selected: false,
      },
      {
        identifier: "SYN-period",
        unadjusted_date: "2027-03-31",
        selected: true,
      },
    ],
  };
  mock.check = {
    items: [{ ...check(7).items[0], deadline_comparison: trace }],
  };
  mock.fetching = false;
  const { rerender } = render(<GRCStudio eid="E" area="obligations" />);
  fireEvent.click(screen.getByRole("button", { name: "Open SYN-SCOPE" }));
  const section = () =>
    screen.getByRole("region", { name: "Later-of deadline comparison" });
  expect(section()).toHaveTextContent("2027-01-01");
  expect(section()).toHaveTextContent("Calculated base deadline: 2027-03-31");
  expect(section()).toHaveTextContent("Selected");
  mock.record = { ...mock.record, version: 8 };
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(section()).not.toHaveTextContent("2027-01-01");
  expect(section()).toHaveTextContent("Awaiting server calculation");
  mock.check = {
    items: [
      {
        ...check(8, "CURRENT", true).items[0],
        deadline_comparison: { state: "REASSESSMENT_REQUIRED" },
      },
    ],
  };
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(section()).toHaveTextContent(
    "Review the retained rule and saved deadline",
  );
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});
it("requires a currentness projection matching the selected record version", () => {
  const { rerender } = render(<GRCStudio eid="E" area="obligations" />);
  fireEvent.click(screen.getByRole("button", { name: "Open SYN-SCOPE" }));
  const button = () =>
    screen.getByRole("button", { name: "Record evidenced filing stage" });
  expect(button()).toBeDisabled();
  expect(screen.getByText(/Checking current obligation sources/)).toBeVisible();
  expect(
    mock.calls.some(
      (x) =>
        x.path === "grc/engagements/E/compliance-calendar?record_id=R" &&
        x.enabled,
    ),
  ).toBe(true);
  mock.check = check(7);
  mock.fetching = false;
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(button()).toBeEnabled();
  mock.record = { ...mock.record, version: 8 };
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(button()).toBeDisabled();
  mock.check = check(8, "STALE", true);
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(screen.getByText(/Source freshness: STALE/)).toBeVisible();
  expect(button()).toBeDisabled();
  mock.check = check(8, "CURRENT", true);
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(button()).toBeDisabled();
  mock.check = check(8);
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(button()).toBeEnabled();
});
it("fails closed on unavailable or wrong-record projections", () => {
  mock.check = check(7);
  mock.fetching = false;
  const { rerender } = render(<GRCStudio eid="E" area="obligations" />);
  fireEvent.click(screen.getByRole("button", { name: "Open SYN-SCOPE" }));
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeEnabled();
  mock.fetching = true;
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  mock.error = new Error("Unavailable");
  mock.fetching = false;
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(screen.getByText(/could not be verified/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  mock.error = null;
  mock.check = {
    items: [
      {
        record_id: "OTHER",
        version: 7,
        freshness: "CURRENT",
        reassessment_required: false,
      },
    ],
  };
  rerender(<GRCStudio eid="E" area="obligations" />);
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});
it("blocks independent obligation review when current sources require reassessment", () => {
  mock.record = { ...mock.record, status: "REVIEW_REQUIRED" };
  mock.check = check(7, "STALE", true);
  mock.fetching = false;
  render(<GRCStudio eid="E" area="obligations" />);
  fireEvent.click(screen.getByRole("button", { name: "Open SYN-SCOPE" }));
  fireEvent.change(screen.getByLabelText("Review rationale"), {
    target: { value: "Synthetic independent assessment" },
  });
  expect(
    screen.getByRole("button", { name: "Approve independently" }),
  ).toBeDisabled();
});

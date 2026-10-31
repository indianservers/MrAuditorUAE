import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
const state = vi.hoisted(() => ({
  query: {
    data: undefined as unknown,
    error: null as Error | null,
    isLoading: false,
  },
  paths: [] as string[],
  count: 1,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => {
    state.paths.push(path);
    if (path.includes("/runs?kind=financials&")) {
      const offset = Number(
        new URLSearchParams(path.split("?")[1]).get("offset"),
      );
      const rows = Array.from({ length: state.count }, (_, i) => ({
        id: state.count === 1 ? "old" : i === 0 ? "new" : `old-${i}`,
        kind: "financials",
        created_at: "2026-10-24",
      }));
      return {
        data: { items: rows.slice(offset, offset + 50), total: rows.length },
        error: null,
        isLoading: false,
      };
    }
    return state.query;
  },
}));
import { FinancialReview } from "@/features/financial-review";
beforeEach(() => {
  state.paths = [];
  state.count = 1;
  state.query = { data: undefined, error: null, isLoading: false };
});
it("shows stale sources and preserves issue evidence and draft selection", () => {
  state.query.data = {
    ready: false,
    dependencies_current: false,
    scope: "Structured financial statements only",
    casting: [],
    changes: [],
    resolved_issue_keys: [],
    issues: [
      {
        key: "note_tie:1/cash",
        severity: "error",
        location: "1/cash",
        message: "Note values do not agree with the statement.",
        evidence: { expected: "130", actual: "129" },
        carry_forward: true,
      },
    ],
  };
  render(<FinancialReview base="ifrs/engagements/e" rid="new" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Source inputs changed");
  expect(screen.getByText(/Carried forward/)).toBeVisible();
  fireEvent.change(screen.getByLabelText("Compare earlier draft"), {
    target: { value: "old" },
  });
  expect(
    state.paths.some((path) => path.includes("comparison_run_id=old")),
  ).toBe(true);
  expect(
    screen.getByText("No statement line, note or package changes."),
  ).toBeVisible();
});
it("displays request failures instead of a successful review", () => {
  state.query.error = new Error(
    "Draft comparison requires the same reporting period",
  );
  render(<FinancialReview base="ifrs/engagements/e" rid="new" />);
  expect(screen.getByRole("alert")).toHaveTextContent("same reporting period");
  expect(screen.queryByText("Checks passed")).not.toBeInTheDocument();
});

it("reaches an earlier draft beyond100, omits the current run and retains the selected comparison across pages", () => {
  state.count = 151;
  render(<FinancialReview base="ifrs/engagements/e" rid="new" />);
  const select = screen.getByLabelText("Compare earlier draft");
  expect(select.querySelector('option[value="new"]')).toBeNull();
  for (let i = 0; i < 3; i++)
    fireEvent.click(
      screen.getByRole("button", { name: "Next compare earlier draft" }),
    );
  fireEvent.change(select, { target: { value: "old-150" } });
  expect(
    state.paths.some((path) => path.includes("comparison_run_id=old-150")),
  ).toBe(true);
  fireEvent.click(
    screen.getByRole("button", { name: "Previous compare earlier draft" }),
  );
  expect(select).toHaveValue("old-150");
  expect(screen.getByRole("option", { selected: true })).toHaveTextContent(
    "2026-10-24",
  );
});

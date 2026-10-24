import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
const state = vi.hoisted(() => ({
  query: {
    data: undefined as unknown,
    error: null as Error | null,
    isLoading: false,
  },
  paths: [] as string[],
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => {
    state.paths.push(path);
    return state.query;
  },
}));
import { FinancialReview } from "@/features/financial-review";
beforeEach(() => {
  state.paths = [];
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
  render(
    <FinancialReview
      base="ifrs/engagements/e"
      rid="new"
      runs={[{ id: "old", kind: "financials", created_at: "2026-10-24" }]}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Source inputs changed");
  expect(screen.getByText(/Carried forward/)).toBeVisible();
  fireEvent.change(screen.getByLabelText("Compare earlier draft"), {
    target: { value: "old" },
  });
  expect(state.paths.at(-1)).toContain("comparison_run_id=old");
  expect(
    screen.getByText("No statement line, note or package changes."),
  ).toBeVisible();
});
it("displays request failures instead of a successful review", () => {
  state.query.error = new Error(
    "Draft comparison requires the same reporting period",
  );
  render(<FinancialReview base="ifrs/engagements/e" rid="new" runs={[]} />);
  expect(screen.getByRole("alert")).toHaveTextContent("same reporting period");
  expect(screen.queryByText("Checks passed")).not.toBeInTheDocument();
});

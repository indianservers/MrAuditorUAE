import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Analytics } from "@/features/analytics";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: { items: [] }, error: null, isLoading: false }),
  useAction: () => ({ mutate: state.mutate, isPending: false, error: null }),
  useCan: () => true,
  useCurrency: () => "AED",
  usePopulation: () => ({ snapshot: "snapshot-id" }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: () => ({ entity: "entity", period: "period" }),
}));
vi.mock("@/features/ml-signals", () => ({ MLSignals: () => null }));
vi.mock("@/components/charts", () => ({
  Chart: () => null,
  Heatmap: () => null,
}));
vi.mock("@/components/grids/financial-data-grid", () => ({
  FinancialDataGrid: () => null,
  amount: () => ({}),
  column: () => ({}),
}));
vi.mock("@/features/shared", () => ({
  ContextGate: ({ children }: { children: React.ReactNode }) => children,
  PageHeader: () => null,
  PopulationPicker: () => null,
  AIRequest: () => null,
  JobProgress: () => null,
  LineageDetail: () => null,
}));

beforeEach(() => state.mutate.mockReset());
describe("analytics operating calendar", () => {
  it("submits no assumed weekend by default", () => {
    render(<Analytics />);
    fireEvent.click(screen.getByRole("button", { name: "Run analytics" }));
    expect(state.mutate.mock.calls[0][0].body).toMatchObject({
      snapshot_id: "snapshot-id",
      weekend_days: [],
      calendar_rationale: "",
    });
  });
  it("requires an assessment and submits selected weekdays using Monday-zero numbering", () => {
    render(<Analytics />);
    fireEvent.click(screen.getByText("Operating calendar for this population"));
    fireEvent.click(screen.getByLabelText("Friday non-working"));
    fireEvent.click(screen.getByLabelText("Saturday non-working"));
    const run = screen.getByRole("button", { name: "Run analytics" });
    expect(run).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Operating calendar assessment"), {
      target: {
        value: "  Reviewed entity operating calendar for the selected period  ",
      },
    });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(state.mutate.mock.calls[0][0].body).toMatchObject({
      weekend_days: [4, 5],
      calendar_rationale:
        "Reviewed entity operating calendar for the selected period",
    });
  });
});

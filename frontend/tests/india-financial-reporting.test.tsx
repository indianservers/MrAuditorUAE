import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { IndiaFinancialReporting } from "@/features/india-financial-reporting";

vi.mock("@/hooks/use-api", () => ({
  useDirectory: () => ({
    clients: { data: [] },
    entities: { data: [] },
    periods: { data: [] },
  }),
  useAction: () => ({ isPending: false, error: null }),
  useAPI: (path: string) => ({
    data:
      path === "engagements?limit=100"
        ? { items: [{ id: "E", name: "SYNTHETIC India" }] }
        : path.includes("/events/")
          ? {
              id: "RUN",
              version: 1,
              freshness: "CURRENT",
              body: {
                review_status: "UNVERIFIED",
                currency: "INR",
                framework: "Ind AS",
                division: "II",
                totals: { Assets: "120", Equity: "100" },
                period_profit: "20",
                balance_sheet_difference_including_unappropriated_profit: "0",
                comparative_totals: { Assets: "80", Equity: "80" },
                comparative_period_profit: "0",
                rows: [
                  {
                    account_code: "OLD",
                    name: "Prior account",
                    statement_group: "Cash",
                    source_closing_debit_positive: "0",
                    presented_amount: "0",
                    comparative_amount: "80",
                    current_account_in_source: false,
                    comparative_account_in_source: true,
                    source_snapshot_id: null,
                    comparative_source_snapshot_id: "PRIOR-SNAPSHOT",
                  },
                  {
                    account_code: "NEW",
                    name: "Current account",
                    statement_group: "Cash",
                    source_closing_debit_positive: "120",
                    presented_amount: "120",
                    comparative_amount: null,
                    current_account_in_source: true,
                    comparative_account_in_source: false,
                    source_snapshot_id: "CURRENT-SNAPSHOT",
                    comparative_source_snapshot_id: null,
                  },
                ],
                limitations: [],
              },
            }
          : path.endsWith("/inputs")
            ? { snapshots: [] }
            : path === "engagements/E"
              ? { entity_id: "ENTITY", period_id: "PERIOD" }
              : { items: [] },
    error: null,
  }),
}));

it("shows comparative totals and attributes prior-only accounts to their actual source", () => {
  render(<IndiaFinancialReporting />);
  fireEvent.change(screen.getByLabelText("Engagement"), {
    target: { value: "E" },
  });
  const totals = screen.getByRole("region", {
    name: "Retained comparative statement totals",
  });
  expect(totals).toHaveTextContent("Comparative period profit: 0");
  expect(totals).toHaveTextContent("80");
  const old = screen.getByRole("row", { name: /OLD Prior account/ });
  expect(within(old).getByText("Not in current source")).toBeInTheDocument();
  expect(
    within(old).getByText("No current source account"),
  ).toBeInTheDocument();
  expect(within(old).getByText("PRIOR-SNAPSHOT")).toBeInTheDocument();
  const current = screen.getByRole("row", { name: /NEW Current account/ });
  expect(
    within(current).getByText("Not in comparative source"),
  ).toBeInTheDocument();
  expect(within(current).getByText("CURRENT-SNAPSHOT")).toBeInTheDocument();
});

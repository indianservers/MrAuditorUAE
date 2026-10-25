import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BankTransactionDates } from "@/features/bank-transaction-dates";

const state = vi.hoisted(() => ({
  page: null as unknown,
  error: null as Error | null,
  fetching: false,
  retry: vi.fn(),
  paths: [] as string[],
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => {
    state.paths.push(path);
    return {
      data: state.page,
      error: state.error,
      isFetching: state.fetching,
      refetch: state.retry,
    };
  },
}));
const initial = [
  {
    source_role: "books",
    source_row_id: "B1",
    transaction_date: "2026-06-30",
    bank_booking_date: "2026-06-30",
    bank_value_date: "2026-07-02",
    bank_date_basis: "BOOKING_DATE",
    booking_date_review_required: false,
  },
];
beforeEach(() => {
  state.page = null;
  state.error = null;
  state.fetching = false;
  state.paths = [];
  state.retry.mockClear();
});
describe("bank transaction dates", () => {
  it("keeps booking and value dates separate and pages independently", () => {
    state.page = {
      body: {
        transaction_dates: [
          {
            source_role: "statement",
            source_row_id: "LAST",
            transaction_date: "2026-07-01",
            bank_value_date: "2026-07-01",
            bank_date_basis: "VALUE_DATE_FALLBACK",
            booking_date_review_required: true,
          },
        ],
      },
    };
    render(
      <BankTransactionDates
        prefix="/api/example"
        selected="event"
        initial={initial}
        total={101}
      />,
    );
    expect(screen.getByText("2026-07-02")).toBeInTheDocument();
    expect(screen.getByText("false")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next bank dates" }));
    expect(state.paths.at(-1)).toContain("date_offset=100");
    expect(screen.getByText("LAST")).toBeInTheDocument();
    expect(screen.getByText("VALUE_DATE_FALLBACK")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next bank dates" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Previous bank dates" }),
    );
    expect(screen.getByText("B1")).toBeInTheDocument();
  });
  it("does not show initial rows as a failed later page and offers retry", () => {
    state.error = new Error("Date page unavailable");
    render(
      <BankTransactionDates
        prefix="/api/example"
        selected="event"
        initial={initial}
        total={101}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Next bank dates" }));
    expect(screen.queryByText("B1")).not.toBeInTheDocument();
    expect(
      screen.getByText("No bank date rows on this page"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry bank dates" }));
    expect(state.retry).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Next bank dates" }),
    ).toBeDisabled();
  });
});

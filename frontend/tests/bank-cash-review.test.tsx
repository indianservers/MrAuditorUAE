import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { BankCashReview } from "@/features/bank-cash-review";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  data: null as unknown,
  error: null as Error | null,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: state.data, error: state.error }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => {
  state.error = null;
  state.data = {
    state: "ACTIVE_APPROVED_ALLOCATION",
    claim_count: 2,
    approval_error: null,
    related_reviews: [],
  };
  state.mutate.mockReset().mockResolvedValue({ id: "withdrawn" });
});
it("requires a reason and sends a version-bound explicit withdrawal", async () => {
  const selected = vi.fn();
  render(
    <BankCashReview
      eid="eng"
      eventId="approved"
      version={4}
      onSelected={selected}
    />,
  );
  const button = screen.getByRole("button", {
    name: "Withdraw bank cash claim",
  });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Bank cash withdrawal reason"), {
    target: { value: "Superseded source assessment" },
  });
  fireEvent.click(button);
  await waitFor(() => expect(selected).toHaveBeenCalledWith("withdrawn"));
  expect(state.mutate).toHaveBeenCalledWith({
    path: "intelligence/engagements/eng/events/approved/withdraw-bank-cash",
    body: {
      action: "reject",
      expected_version: 4,
      comments: "Superseded source assessment",
    },
  });
});
it("shows conflicts and navigates to the retained competing review", () => {
  state.data = {
    state: "UNRESERVED",
    claim_count: 2,
    approval_error: "BANK_MOVEMENT_OVERALLOCATED_ACROSS_REVIEWS",
    related_reviews: [
      { id: "peer", root_id: "root", title: "Earlier allocation" },
    ],
  };
  const selected = vi.fn();
  render(
    <BankCashReview
      eid="eng"
      eventId="candidate"
      version={1}
      onSelected={selected}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("OVERALLOCATED");
  expect(
    screen.queryByRole("button", { name: "Withdraw bank cash claim" }),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: /Open related allocation/ }),
  );
  expect(selected).toHaveBeenCalledWith("peer");
});
it("does not show a successful capacity check when the request fails", () => {
  state.data = null;
  state.error = new Error("Evidence is inaccessible");
  render(
    <BankCashReview
      eid="eng"
      eventId="candidate"
      version={1}
      onSelected={vi.fn()}
    />,
  );
  expect(screen.getByText("Evidence is inaccessible")).toBeVisible();
  expect(screen.queryByText(/Cash claim:/)).toBeNull();
});

it("links authorized peer reviews to their own engagement and selected event", () => {
  state.data = {
    state: "UNRESERVED",
    claim_count: 2,
    approval_error: null,
    related_reviews: [
      {
        id: "peer",
        root_id: "root",
        engagement_id: "other",
        title: "Tax settlement",
      },
    ],
  };
  render(
    <BankCashReview
      eid="eng"
      eventId="candidate"
      version={1}
      onSelected={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("link", { name: /Open related engagement allocation/ }),
  ).toHaveAttribute("href", "/intelligence/other/country-workflow?event=peer");
});

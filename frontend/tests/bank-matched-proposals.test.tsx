import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { BankMatchedProposals } from "@/features/bank-matched-proposals";

const state = vi.hoisted(() => ({ paths: [] as string[] }));
const proposal = {
  left_ids: ["B1"],
  right_ids: ["S1"],
  rule: "REFERENCE_EXACT",
  variance: "0.00",
  auditor_status: "UNVERIFIED",
};
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => {
    state.paths.push(path);
    if (path.includes("bank-matched-proposal"))
      return {
        data: {
          books: [
            {
              id: "B1",
              reference: "SYNTHETIC BOOK",
              date: "2026-06-15",
              amount: "100.20",
              currency: "AED",
            },
          ],
          statement: [
            {
              id: "S1",
              reference: "SYNTHETIC BANK",
              date: "2026-06-15",
              amount: "100.20",
              currency: "AED",
              bank_booking_date: "2026-06-15",
              bank_value_date: "2026-06-16",
            },
          ],
        },
        error: null,
      };
    return {
      data: {
        body: {
          matches: path.includes("offset=25")
            ? [proposal]
            : Array.from({ length: 25 }, () => proposal),
        },
      },
      error: null,
      isFetching: false,
    };
  },
}));

it("pages every retained proposal and inspects original rows without changing a decision", () => {
  render(
    <BankMatchedProposals
      prefix="intelligence/engagements/e"
      selected="result"
      total={26}
    />,
  );
  expect(screen.getByText("Proposals 1–25 of 26")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Inspect proposal 1" }));
  const details = screen.getByRole("region", {
    name: "Matched proposal transaction details",
  });
  expect(within(details).getByText("SYNTHETIC BOOK")).toBeVisible();
  expect(within(details).getByText("SYNTHETIC BANK")).toBeVisible();
  expect(within(details).getByText("2026-06-16")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /approve|accept/i }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Next matched proposals" }),
  );
  expect(screen.getByText("Proposals 26–26 of 26")).toBeVisible();
  expect(
    screen.queryByRole("region", {
      name: "Matched proposal transaction details",
    }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Inspect proposal 26" }));
  expect(
    state.paths.some((p) => p.endsWith("bank-matched-proposal?index=25")),
  ).toBe(true);
  expect(
    screen.getByRole("button", { name: "Next matched proposals" }),
  ).toBeDisabled();
});

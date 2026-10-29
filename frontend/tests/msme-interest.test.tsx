import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { MSMEInterestDetails } from "@/features/msme-interest";

it("separates a partial interest subtotal from retained principal timing exceptions", () => {
  render(
    <MSMEInterestDetails
      rows={[
        {
          id: "INV",
          expected_amount: null,
          timing_state: "OVERDUE",
          interest_resolution_issue: "Missing rate day 2026-06-02",
        },
      ]}
      expectedTotal="0"
      complete={false}
      principalExceptions={1}
      binding="NO_INTEREST_FACTS_CLAIMED"
    />,
  );
  expect(
    screen.getByText(/Partial outstanding interest subtotal/),
  ).toHaveTextContent("INR 0");
  expect(screen.getByText(/Principal timing exceptions:/)).toHaveTextContent(
    "1",
  );
  expect(screen.getByText(/No resolved interest policy claimed/)).toBeVisible();
  fireEvent.click(screen.getByText(/Invoice INV/));
  expect(screen.getByText(/Missing rate day 2026-06-02/)).toBeVisible();
  expect(
    screen.getByText(/Tax deductions, Section 22 disclosures/),
  ).toBeVisible();
});

it("paginates every trace row without converting exact financial strings to floating point", () => {
  const amount = "999999999999999999.12345678901234567890";
  render(
    <MSMEInterestDetails
      rows={[
        {
          id: "INV",
          expected_amount: "93.23",
          timing_state: "OVERDUE",
          interest_policy: {
            start_basis: "SEPARATELY_ASSESSED_START",
            interest_start: "2026-06-01",
          },
          segments: Array.from({ length: 11 }, (_, index) => ({
            id: `SEG-${index}`,
            interest: amount,
          })),
        },
      ]}
      complete
      expectedTotal="93.23"
      principalExceptions={1}
      binding="RETAINED_DOCUMENT_BYTES_VERIFIED"
      bankControls={[
        {
          transaction_id: "BANK",
          gross_principal_allocated: "900",
          interest_allocated: "90",
          unallocated_outflow: "10",
        },
      ]}
    />,
  );
  fireEvent.click(screen.getByText(/Invoice INV/));
  expect(screen.getByText("SEPARATELY_ASSESSED_START")).toBeVisible();
  fireEvent.click(screen.getByText("Accrual intervals (11)"));
  const table = screen.getByRole("table", { name: "Accrual intervals" });
  expect(within(table).getAllByText(amount)).toHaveLength(10);
  const pager = screen.getByRole("navigation", {
    name: "Accrual intervals pages",
  });
  fireEvent.click(within(pager).getByRole("button", { name: "Next" }));
  expect(within(table).getByText("SEG-10")).toBeVisible();
  expect(within(table).queryByText("SEG-0")).not.toBeInTheDocument();
  expect(within(pager).getByRole("button", { name: "Next" })).toBeDisabled();
  fireEvent.click(screen.getByText("Bank allocation controls (1)"));
  expect(
    screen.getByRole("table", { name: "Bank allocation controls" }),
  ).toHaveTextContent("9009010");
});

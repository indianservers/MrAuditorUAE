import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { AccountingScheduleResults } from "@/features/accounting-schedule-results";

it("retains every item, movement and later-only field with independent pages and exact values", () => {
  render(
    <AccountingScheduleResults
      kind="inventory"
      data={{
        execution: { presentation_currency: "AED" },
        closing_carrying: "12345678901234567890.12345678",
        write_down_movement: "0",
        schedule: Array.from({ length: 101 }, (_, i) => ({
          reference: `ITEM-${i + 1}`,
          closing_quantity: "0",
          closing_cost: "12345678901234567890.12345678",
          ...(i === 100 ? { last_item_field: "LAST-FIELD" } : {}),
        })),
        movements: Array.from({ length: 26 }, (_, i) => ({
          reference: `MOVE-${i + 1}`,
          quantity: "0.12345678",
          evidence: "SYNTHETIC original source",
        })),
        transfers: [],
        issues: [],
      }}
    />,
  );
  const items = screen.getByRole("region", { name: "Inventory item costing" });
  expect(
    within(items).getByRole("columnheader", { name: "last item field" }),
  ).toBeVisible();
  for (let i = 0; i < 4; i++)
    fireEvent.click(
      within(items).getByRole("button", {
        name: "Next inventory item costing",
      }),
    );
  expect(within(items).getByRole("cell", { name: "ITEM-101" })).toBeVisible();
  expect(within(items).getByRole("cell", { name: "LAST-FIELD" })).toBeVisible();
  expect(
    within(items).getByRole("cell", { name: "12345678901234567890.12345678" }),
  ).toBeVisible();
  fireEvent.click(screen.getByText("Inventory cost movements (26)"));
  const movements = screen.getByRole("region", {
    name: "Inventory cost movements",
  });
  fireEvent.click(
    within(movements).getByRole("button", {
      name: "Next inventory cost movements",
    }),
  );
  expect(
    within(movements).getByRole("cell", { name: "MOVE-26" }),
  ).toBeVisible();
  expect(within(items).getByRole("cell", { name: "ITEM-101" })).toBeVisible();
});

it("keeps benefit and payroll rollforwards separate, preserving zero, unknown and explicit framework", () => {
  render(
    <AccountingScheduleResults
      kind="employee-benefits"
      data={{
        execution: { presentation_currency: "INR" },
        employment_framework: "other",
        statutory_settlement_estimate: null,
        oci_movement: "1.23456789",
        obligation_rollforward: {
          opening: "10",
          closing: "0",
          difference: null,
        },
        payroll_bridge: {
          opening: "20",
          closing: "0.00000001",
          confirmed_bank_payments: "0",
        },
        issues: [],
      }}
    />,
  );
  const obligation = screen.getByRole("region", {
    name: "Benefit obligation rollforward",
  });
  const payroll = screen.getByRole("region", {
    name: "Payroll accounting bridge",
  });
  expect(within(obligation).getByText("0")).toBeVisible();
  expect(within(obligation).getByText("—")).toBeVisible();
  expect(within(payroll).getByText("0.00000001")).toBeVisible();
  expect(within(payroll).getByText("0")).toBeVisible();
  expect(screen.getByText("other")).toBeVisible();
  expect(screen.getByText("1.23456789")).toBeVisible();
  expect(screen.getByText(/Reporting currency: INR/)).toBeVisible();
});

it("keeps complete original execution and unknown metadata available on deliberate expansion", () => {
  const { container } = render(
    <AccountingScheduleResults
      kind="inventory"
      data={{
        schedule: [],
        movements: [],
        transfers: [],
        issues: [],
        execution: { original_provenance: "SYNTHETIC-original-reference" },
        future_field: { exact: "0.123456789" },
      }}
    />,
  );
  expect(container.querySelector("pre")).toBeNull();
  const details = screen
    .getByText("Complete retained calculation and provenance")
    .closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle", { bubbles: true }));
  expect(container.querySelector("pre")).toHaveTextContent(
    '"original_provenance": "SYNTHETIC-original-reference"',
  );
  expect(container.querySelector("pre")).toHaveTextContent(
    '"exact": "0.123456789"',
  );
});

it("exposes malformed retained rows rather than declaring a complete clean schedule", () => {
  render(
    <AccountingScheduleResults
      kind="inventory"
      data={{
        schedule: [null, "bad-row", { reference: "VALID", closing_cost: "0" }],
        movements: [],
        transfers: [],
        issues: [],
      }}
    />,
  );
  const items = screen.getByRole("region", { name: "Inventory item costing" });
  expect(within(items).getByRole("alert")).toHaveTextContent(
    "2 source records are not structured rows",
  );
  expect(within(items).getByRole("cell", { name: "VALID" })).toBeVisible();
});

import React from "react";
import { it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FinancialChart } from "@/components/charts/financial-chart";
import {
  FinancialDataGrid,
  column,
  amount,
} from "@/components/grids/financial-data-grid";
it("sorts scientific zeros and large decimal amounts without floating point", () => {
  const compare = amount("value", "Amount").comparator!;
  if (typeof compare !== "function")
    throw new Error("Expected amount comparator");
  expect(compare("0E-8", "0.00000001", null!, null!, false)).toBe(-1);
  expect(compare("-0.10000000", "0E-8", null!, null!, false)).toBe(-1);
  expect(
    compare(
      "99999999999999999999.00000001",
      "99999999999999999999.00000000",
      null!,
      null!,
      false,
    ),
  ).toBe(1);
});
it("shows a truthful empty chart without inventing data", () => {
  render(<FinancialChart title="Risk distribution" data={[]} />);
  expect(screen.getByRole("heading", { name: "No chart data" })).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
it("provides usable financial grid controls and error state", () => {
  const { rerender } = render(
    <FinancialDataGrid
      name="component-test"
      rows={[]}
      columns={[column("code", "Account Code")]}
    />,
  );
  expect(screen.getByRole("button", { name: "CSV · page" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Columns" }));
  expect(screen.getByRole("dialog", { name: "Visible columns" })).toBeVisible();
  expect(screen.getByLabelText("Account Code")).toBeChecked();
  rerender(
    <FinancialDataGrid
      rows={[]}
      columns={[]}
      error={new Error("Backend unavailable")}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
});

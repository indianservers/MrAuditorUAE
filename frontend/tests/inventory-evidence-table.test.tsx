import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InventoryEvidenceTable } from "@/features/inventory-evidence-table";

vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: path.includes("confirmation_link_offset=100") ? {body: {confirmation_coverage_links: [{source_row_id: "LINK-LAST", item_id: "INV-LAST", evidence_reference: "REPLY-PAGE-9"}]}} : path.includes("purchase_offset=100")
      ? {
          body: {
            purchase_quantity_controls: [
              {
                order_id: "PO-LAST",
                line_reference: "LINE-LAST",
                vendor: "V1",
                currency: "AED",
                uom: "KG",
                document_type: "order",
                expected_rows: 1,
                quantity: "2",
              },
            ],
          },
        }
      : path.includes("inventory_offset=100")
        ? {
            body: {
              inventory_quantity_controls: [
                {
                  site: "WH",
                  sku: "LAST",
                  lot: "B",
                  uom: "EA",
                  currency: "AED",
                  expected_rows: 2,
                  positive_quantity: "4",
                  negative_quantity: "-1",
                },
              ],
            },
          }
        : undefined,
    isFetching: false,
    error: null,
  }),
}));

describe("inventory evidence pagination", () => {
  it("pages purchase controls independently and retains declared units", () => {
    render(
      <InventoryEvidenceTable
        prefix="intelligence/engagements/eng"
        selected="purchase"
        total={101}
        purchase
        initial={Array.from({ length: 100 }, (_, index) => ({
          order_id: "PO-" + index,
          line_reference: "LINE-1",
          vendor: "V1",
          currency: "AED",
          uom: "PCS",
          document_type: "order",
          expected_rows: 1,
          quantity: "2",
        }))}
      />,
    );
    fireEvent.click(
      screen.getByText("Purchase quantity controls · 101 partitions"),
    );
    expect(screen.getByRole("cell", { name: "PO-0" })).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Next quantity control rows" }),
    );
    expect(screen.getByRole("cell", { name: "PO-LAST" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "KG" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next quantity control rows" }),
    ).toBeDisabled();
  });
  it("pages control partitions independently without aggregating units or signs", () => {
    render(
      <InventoryEvidenceTable
        prefix="intelligence/engagements/eng"
        selected="source"
        total={101}
        initial={Array.from({ length: 100 }, (_, index) => ({
          site: "WH",
          sku: "SKU-" + index,
          lot: "A",
          uom: "EA",
          currency: "AED",
          expected_rows: 1,
          positive_quantity: "1",
          negative_quantity: "0",
        }))}
      />,
    );
    fireEvent.click(
      screen.getByText("Inventory quantity controls · 101 partitions"),
    );
    expect(screen.getByRole("cell", { name: "SKU-0" })).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Next quantity control rows" }),
    );
    expect(screen.getByRole("cell", { name: "LAST" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "-1" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next quantity control rows" }),
    ).toBeDisabled();
  });
});


it("pages reviewed confirmation links using an independent offset", () => {
  render(<InventoryEvidenceTable prefix="/audit" selected="result" initial={Array.from({length:100},(_,i)=>({source_row_id:`LINK-${i}`,item_id:`INV-${i}`}))} total={101} confirmation />);
  fireEvent.click(screen.getByText("Partial confirmation item links · 101 links"));
  fireEvent.click(screen.getByRole("button", {name:"Next confirmation link rows"}));
  expect(screen.getByText("INV-LAST")).toBeVisible();
  expect(screen.getByText("REPLY-PAGE-9")).toBeVisible();
  expect(screen.getByRole("button", {name:"Next confirmation link rows"})).toBeDisabled();
});

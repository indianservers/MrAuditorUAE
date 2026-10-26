import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InventoryEvidenceTable } from "@/features/inventory-evidence-table";

vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: path.includes("purchase_offset=100")
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

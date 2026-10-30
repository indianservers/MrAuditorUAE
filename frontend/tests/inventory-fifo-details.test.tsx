import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InventoryFIFODetails } from "@/features/inventory-fifo-details";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string, enabled: boolean) => {
    request(path, enabled);
    return {
      data: { body: { fifo_allocations: [{ layer_source_row_id: "LAST-LAYER", cost: "0" }], fifo_event_costs: [{ source_row_id: "LAST-EVENT" }] } },
      error: null, isFetching: false,
    };
  },
}));

describe("FIFO retained cost evidence", () => {
  it("pages allocations independently from events and retains zero cost", () => {
    render(<InventoryFIFODetails prefix="/intelligence/engagements/E" selected="R" body={{ fifo_allocations: [{ layer_source_row_id: "FIRST-LAYER" }], fifo_event_costs: [{ source_row_id: "FIRST-EVENT" }] }} totals={{ fifo_allocations: 21, fifo_event_costs: 21 }} />);
    fireEvent.click(screen.getByText("FIFO issue allocations · 21"));
    fireEvent.click(screen.getByText("FIFO movement costs · 21"));
    fireEvent.click(screen.getByRole("button", { name: "Next FIFO issue allocations" }));
    expect(screen.getByRole("cell", { name: "LAST-LAYER" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "0" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "FIRST-EVENT" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Next FIFO issue allocations" })).toBeDisabled();
    expect(request).toHaveBeenCalledWith("/intelligence/engagements/E/events/R?limit=1&fifo_offset=20&fifo_limit=20", true);
    fireEvent.click(screen.getByRole("button", { name: "Previous FIFO issue allocations" }));
    expect(screen.getByRole("cell", { name: "FIRST-LAYER" })).toBeVisible();
  });

  it("resets collection offsets when a different result is selected", () => {
    const body = { fifo_allocations: [{ layer_source_row_id: "FIRST" }] };
    const view = render(<InventoryFIFODetails prefix="/audit" selected="A" body={body} totals={{ fifo_allocations: 21 }} />);
    fireEvent.click(screen.getByText("FIFO issue allocations · 21"));
    fireEvent.click(screen.getByRole("button", { name: "Next FIFO issue allocations" }));
    view.rerender(<InventoryFIFODetails prefix="/audit" selected="B" body={body} totals={{ fifo_allocations: 21 }} />);
    fireEvent.click(screen.getByText("FIFO issue allocations · 21"));
    expect(screen.getByRole("cell", { name: "FIRST" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous FIFO issue allocations" })).toBeDisabled();
  });
});

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { VATCompositionSource } from "@/features/vat-composition-source";

const mutate = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));

describe("VAT201 composition", () => {
  beforeEach(() => {
    mutate.mockReset();
    mutate.mockResolvedValue({ id: "composed" });
  });
  const source = (
    id: string,
    freshness = "CURRENT",
    review_status = "REVIEWED",
  ) => ({
    id,
    label: id,
    kind: "workflow-source",
    table_type: "return-boxes",
    freshness,
    review_status,
  });
  it("offers only current reviewed box sources and requires explicit independent controls", async () => {
    const created = vi.fn();
    render(
      <VATCompositionSource
        eid="eng"
        sources={[
          source("imports"),
          source("other-boxes"),
          source("stale", "STALE"),
          source("unreviewed", "CURRENT", "UNVERIFIED"),
        ]}
        onCreated={created}
      />,
    );
    fireEvent.click(screen.getByText("Compose reviewed VAT201 book schedules"));
    expect(screen.getAllByRole("option")).toHaveLength(2);
    const prepare = screen.getByRole("button", {
      name: "Prepare composed VAT201 books",
    });
    expect(prepare).toBeDisabled();
    const schedules = screen.getByLabelText(
      "Reviewed VAT201 component schedules",
    ) as HTMLSelectElement;
    Array.from(schedules.options).forEach((option) => {
      option.selected = true;
    });
    fireEvent.change(schedules);
    for (const [name, value] of [
      ["Composed VAT201 source title", "Assessed books"],
      ["Independent composed taxable amount", "2400"],
      ["Independent composed tax total", "230"],
      ["Independent composed adjustment total", "0"],
      [
        "VAT201 composition scope assessment",
        "Independent complete disjoint box populations reviewed",
      ],
    ])
      fireEvent.change(screen.getByLabelText(name), { target: { value } });
    fireEvent.click(prepare);
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith({
        path: "intelligence/engagements/eng/vat201-composition-source",
        body: {
          source_ids: ["imports", "other-boxes"],
          label: "Assessed books",
          taxable_amount: "2400",
          tax: "230",
          adjustment: "0",
          assessment: "Independent complete disjoint box populations reviewed",
        },
      }),
    );
    expect(created).toHaveBeenCalledWith("composed");
  });
});

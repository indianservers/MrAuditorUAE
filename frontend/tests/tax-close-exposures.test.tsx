import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TaxCloseExposures } from "@/features/tax-close-exposures";
const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  country: "AE",
  blocked: false,
  fresh: "CURRENT",
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (s: { tenant: string; country: string }) => unknown) =>
    select({ tenant: "t", country: state.country }),
}));
vi.mock("@/features/intelligence-exports", () => ({
  IntelligenceExports: () => null,
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({ data: { items: [] }, hasOlder: false }),
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAction: () => ({ mutateAsync: state.mutate, isPending: false }),
  useAPI: (path: string, enabled = true) => ({
    data: !enabled
      ? undefined
      : path.includes("working-papers")
        ? {
            items: path.includes("offset=50")
              ? [{ id: "b", reference: "Paper B", status: "APPROVED" }]
              : [
                  { id: "a", reference: "Paper A", status: "APPROVED" },
                  { id: "draft", reference: "Draft paper", status: "DRAFT" },
                ],
            total: 51,
          }
        : {
            id: "result",
            version: 1,
            freshness: state.fresh,
            body: {
              title: "Saved result",
              blocked: state.blocked,
              review_status: "UNVERIFIED",
              unique_findings: 1,
              workpaper_reference_count: 2,
              duplicate_references_eliminated: 1,
              totals_by_currency: {
                AED: {
                  positive_impact: "125.00000001",
                  negative_impact: "-20",
                  finding_count: 2,
                },
              },
              rows: [],
              issues: [],
              limitations: [],
            },
          },
  }),
}));
beforeEach(() => {
  state.mutate.mockReset().mockResolvedValue({ id: "result" });
  state.blocked = false;
  state.fresh = "CURRENT";
  state.country = "AE";
});
async function prepare() {
  fireEvent.click(screen.getByLabelText("Paper A · APPROVED"));
  fireEvent.click(screen.getByRole("button", { name: "Next roll-up papers" }));
  fireEvent.click(screen.getByLabelText("Paper B · APPROVED"));
  fireEvent.change(screen.getByLabelText("Roll-up title"), {
    target: { value: "Tax close" },
  });
  fireEvent.change(
    screen.getByLabelText("Tax-close population and review rationale"),
    { target: { value: "Reviewed source population rationale" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare finding roll-up" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
}
describe("tax-close exposure source population", () => {
  it("retains papers across pages, excludes drafts and sends exact source identities", async () => {
    render(<TaxCloseExposures eid="e" />);
    expect(screen.queryByLabelText("Draft paper · DRAFT")).toBeNull();
    await prepare();
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "regulatory/engagements/e/tax-close-rollups",
      body: { workpaper_ids: ["a", "b"] },
    });
    expect(
      await screen.findByText(/1 repeated references eliminated/),
    ).toBeTruthy();
    expect(screen.getByText("125.00000001")).toBeTruthy();
    expect(screen.getByText("-20")).toBeTruthy();
    expect(screen.getByLabelText("Retained finding roll-up")).toHaveValue(
      "result",
    );
  });
  it("does not enable independent approval for an incomplete result", async () => {
    state.blocked = true;
    render(<TaxCloseExposures eid="e" />);
    await prepare();
    expect(
      await screen.findByRole("button", {
        name: "Independently approve finding roll-up",
      }),
    ).toBeDisabled();
  });
  it("resets selected papers when the country changes", () => {
    const { rerender } = render(<TaxCloseExposures eid="e" />);
    fireEvent.click(screen.getByLabelText("Paper A · APPROVED"));
    expect(
      screen.getByText("1 selected workpapers (maximum 50)."),
    ).toBeTruthy();
    state.country = "IN";
    rerender(<TaxCloseExposures eid="e" />);
    expect(
      screen.getByText("0 selected workpapers (maximum 50)."),
    ).toBeTruthy();
  });
});

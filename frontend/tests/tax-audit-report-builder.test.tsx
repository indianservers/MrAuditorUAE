import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StatutoryReportBuilder } from "@/features/statutory-report-builder";
const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  tenant: "tenant",
  country: "IN",
}));
vi.mock("@/features/shared", () => ({
  PageHeader: () => <h1>Report designer</h1>,
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select?: (s: typeof state) => unknown) =>
    select ? select(state) : state,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data:
      path === "engagements?limit=100"
        ? {
            items: [
              { id: "one", name: "First" },
              { id: "two", name: "Second" },
            ],
          }
        : undefined,
  }),
  useAction: () => ({ mutateAsync: state.mutate, isPending: false }),
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: {
      items: [
        {
          id: "case",
          label: "Reviewed case",
          kind: "statutory-checklist",
          area: "india-tax-audit",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
      ],
    },
  }),
}));
describe("tax audit report builder", () => {
  it("sends the explicitly assessed scope and clears it when changing engagement", async () => {
    state.mutate.mockReset().mockResolvedValue({ id: "saved" });
    render(<StatutoryReportBuilder />);
    const change = (label: string, value: string) =>
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    change("Engagement", "one");
    change("Report title", "Tax working draft");
    change("Report category", "india-tax-audit");
    change("Block title", "Assessed source narrative");
    fireEvent.click(screen.getByRole("button", { name: "Add content block" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Save template version" }),
    );
    expect(state.mutate).not.toHaveBeenCalled();
    change("Reviewed tax-audit applicability case", "case");
    change("Tax period start", "2026-04-01");
    change("Tax period end", "2027-03-31");
    change("Accounts audited under another law", "no");
    change("Selected tax-audit form", "26");
    change("Form 26 audit-report part", "B");
    fireEvent.click(
      screen.getByRole("button", { name: "Save template version" }),
    );
    await waitFor(() => expect(state.mutate).toHaveBeenCalledOnce());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "regulatory/engagements/one/report-templates",
      body: {
        category: "india-tax-audit",
        tax_audit_scope: {
          applicability_id: "case",
          tax_period_start: "2026-04-01",
          tax_period_end: "2027-03-31",
          audited_under_other_law: false,
          form: "26",
          audit_report_part: "B",
        },
      },
    });
    change("Engagement", "two");
    expect(screen.getByLabelText("Report title")).toHaveValue("");
    expect(screen.getByLabelText("Report category")).toHaveValue(
      "management-letter",
    );
    change("Report category", "india-tax-audit");
    expect(screen.getByLabelText("Tax period start")).toHaveValue("");
    expect(
      screen.getByLabelText("Reviewed tax-audit applicability case"),
    ).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Save template version" }),
    ).toBeDisabled();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  emptyTaxScope,
  selectedTaxScope,
  TaxAuditScopeForm,
} from "@/features/tax-audit-scope";
const fixtures = vi.hoisted(() => ({
  items: [] as Record<string, string>[],
  selected: undefined as unknown,
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({ data: { items: fixtures.items }, hasOlder: false }),
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: fixtures.selected }),
}));
describe("tax audit scope selection", () => {
  it("requires explicit audit basis, accepting an assessed false value", () => {
    const draft = {
      ...emptyTaxScope,
      applicability_id: "case",
      tax_period_start: "2025-04-01",
      tax_period_end: "2026-03-31",
      form: "3CB-3CD" as const,
    };
    expect(() => selectedTaxScope(draft)).toThrow("audit basis");
    expect(
      selectedTaxScope({
        ...draft,
        audited_under_other_law: false,
        audit_report_part: "B",
      }),
    ).toMatchObject({
      audited_under_other_law: false,
      audit_report_part: null,
    });
  });
  it("requires the Form 26 report part without inferring it", () => {
    const draft = {
      ...emptyTaxScope,
      applicability_id: "case",
      tax_period_start: "2026-04-01",
      tax_period_end: "2027-03-31",
      audited_under_other_law: true,
      form: "26" as const,
    };
    expect(() => selectedTaxScope(draft)).toThrow("Part A or B");
    expect(
      selectedTaxScope({ ...draft, audit_report_part: "A" }).audit_report_part,
    ).toBe("A");
  });
  it("requires reselection when loading obsolete report-part letters", () => {
    const retained = {
      ...emptyTaxScope,
      applicability_id: "case",
      tax_period_start: "2026-04-01",
      tax_period_end: "2027-03-31",
      audited_under_other_law: true,
      form: "26",
      audit_report_part: "C",
    } as unknown as Parameters<typeof selectedTaxScope>[0];
    expect(() => selectedTaxScope(retained)).toThrow("Part A or B");
  });
  it("offers only current reviewed tax cases and retains a selected older case", () => {
    fixtures.items = [
      {
        id: "good",
        label: "Reviewed current",
        kind: "statutory-checklist",
        area: "india-tax-audit",
        review_status: "REVIEWED",
        freshness: "CURRENT",
      },
      {
        id: "stale",
        label: "Stale case",
        kind: "statutory-checklist",
        area: "india-tax-audit",
        review_status: "REVIEWED",
        freshness: "STALE",
      },
      {
        id: "draft",
        label: "Draft case",
        kind: "statutory-checklist",
        area: "india-tax-audit",
        review_status: "DRAFT",
        freshness: "CURRENT",
      },
      {
        id: "gst",
        label: "GST case",
        kind: "statutory-checklist",
        area: "gst",
        review_status: "REVIEWED",
        freshness: "CURRENT",
      },
    ];
    fixtures.selected = {
      id: "older",
      kind: "statutory-checklist",
      freshness: "CURRENT",
      body: {
        title: "Retained older case",
        area: "india-tax-audit",
        review_status: "REVIEWED",
      },
    };
    render(
      <TaxAuditScopeForm
        eid="eng"
        value={{ ...emptyTaxScope, applicability_id: "older" }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("option", { name: "Reviewed current" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("option", { name: "Retained older case" }),
    ).toBeTruthy();
    for (const name of ["Stale case", "Draft case", "GST case"])
      expect(screen.queryByRole("option", { name })).toBeNull();
    expect(
      screen.getByLabelText("Reviewed tax-audit applicability case"),
    ).toHaveValue("older");
  });
});

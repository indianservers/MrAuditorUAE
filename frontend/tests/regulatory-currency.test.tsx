import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAPI } from "@/hooks/use-api";
import { RegulatoryAssessmentPanel } from "@/features/regulatory-assessment";
const context = vi.hoisted(() => ({ country: "AE" }));
beforeEach(() => {
  context.country = "AE";
  vi.clearAllMocks();
});

vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: { items: [] },
    error: null,
    hasOlder: false,
  }),
}));

vi.mock("@/stores/workspace", () => ({
  useScope: (selector: (state: { country: string }) => unknown) =>
    selector({ country: "AE" }),
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: vi.fn((path: string) => ({
    data: path.endsWith("country-workflows")
      ? { country: context.country }
      : {
          items: path.startsWith("regulatory/rules")
            ? [
                {
                  id: "aed",
                  rule_key: "AE-SYNTHETIC-AED",
                  version: 1,
                  state: "PUBLISHED",
                  body: {
                    framework: "IFRS",
                    method: "flat_rate",
                    calculation_currency: "AED",
                    effective_from: "2026-01-01",
                  },
                },
                {
                  id: "usd",
                  rule_key: "AE-SYNTHETIC-USD",
                  version: 1,
                  state: "PUBLISHED",
                  body: {
                    framework: "IFRS",
                    method: "flat_rate",
                    calculation_currency: "USD",
                    effective_from: "2026-01-01",
                  },
                },
                {
                  id: "legacy",
                  rule_key: "AE-SYNTHETIC-LEGACY",
                  version: 1,
                  state: "PUBLISHED",
                  body: {
                    framework: "IFRS",
                    method: "flat_rate",
                    effective_from: "2026-01-01",
                  },
                },
                {
                  id: "pension",
                  rule_key: "AE-SYNTHETIC-PENSION",
                  version: 1,
                  state: "PUBLISHED",
                  body: {
                    framework: "IFRS",
                    method: "pension_profile",
                    effective_from: "2026-01-01",
                  },
                },
                {
                  id: "check",
                  rule_key: "AE-SYNTHETIC-CHECK",
                  version: 1,
                  state: "PUBLISHED",
                  body: {
                    framework: "IFRS",
                    method: "checklist",
                    effective_from: "2026-01-01",
                  },
                },
              ]
            : [],
        },
    error: null,
  })),
  useAction: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
}));

describe("regulatory rule currency", () => {
  it("loads rules for the selected engagement country instead of the global country", () => {
    context.country = "IN";
    render(<RegulatoryAssessmentPanel eid="india-engagement" />);
    expect(
      vi
        .mocked(useAPI)
        .mock.calls.some(
          ([path]) => path === "regulatory/rules?country=IN&limit=100",
        ),
    ).toBe(true);
    expect(
      vi
        .mocked(useAPI)
        .mock.calls.some(
          ([path]) => path === "regulatory/rules?country=AE&limit=100",
        ),
    ).toBe(false);
  });
  it("shows each declared currency and requires review of legacy unspecified rates", () => {
    render(<RegulatoryAssessmentPanel eid="engagement" />);
    expect(
      screen.getByRole("option", { name: /AE-SYNTHETIC-AED.*AED$/ }),
    ).toBeEnabled();
    expect(
      screen.getByRole("option", { name: /AE-SYNTHETIC-USD.*USD$/ }),
    ).toBeEnabled();
    expect(
      screen.getByRole("option", {
        name: /AE-SYNTHETIC-LEGACY.*currency review required/,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("option", {
        name: /AE-SYNTHETIC-PENSION.*use pension contribution review/,
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("option", { name: /AE-SYNTHETIC-CHECK/ }),
    ).toBeEnabled();
    expect(
      screen.getByText(/functional currency and reporting dates come from/),
    ).toBeVisible();
  });
});

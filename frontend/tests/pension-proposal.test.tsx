import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { RegulatoryLibrary } from "@/features/regulatory-library";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (
    select?: (scope: { country: string; tenant: string }) => unknown,
  ) =>
    select
      ? select({ country: "AE", tenant: "firm" })
      : { country: "AE", tenant: "firm" },
}));
vi.mock("@/hooks/use-api", () => ({
  useDirectory: () => ({
    clients: { data: [] },
    entities: { data: [] },
    periods: { data: [] },
  }),
  useAPI: (_path: string, enabled = true) => ({
    data: enabled ? { items: [] } : undefined,
    error: null,
  }),
  useCan: () => true,
  useAction: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

it("exposes separate optional eligibility and salary-cap parameters without seeding legal values", () => {
  render(<RegulatoryLibrary />);
  fireEvent.click(
    screen.getByRole("button", { name: "Propose UAE pension profile" }),
  );
  const proposal = JSON.parse(
    (
      screen.getByLabelText(
        "Versioned rule configuration",
      ) as HTMLTextAreaElement
    ).value,
  );
  expect(proposal.pension_parameters).toMatchObject({
    exclusive_eligibility_ceiling: null,
    salary_cap: null,
    rate: null,
    authority: "",
    scheme: "",
    membership_cohort: "",
  });
  expect(proposal.professional_review_status).toBe("PENDING");
  expect(proposal.validation_status).toBe("AWAITING_VALIDATION");
});

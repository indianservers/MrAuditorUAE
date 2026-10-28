import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({ mutate: vi.fn(), country: "IN" }));
const roles = {
  assessments: "msme-supplier-assessments",
  invoices: "msme-invoices",
  bank: "transactions",
  allocations: "item-allocations",
};
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (s: { tenant: string }) => unknown) =>
    select({ tenant: "tenant" }),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: {
      items: Object.entries(roles).flatMap(([role, table_type]) =>
        [true, false].map((reviewed) => ({
          id: role + (reviewed ? "-reviewed" : "-unreviewed"),
          label: role + (reviewed ? " reviewed" : " unreviewed"),
          table_type,
          kind: "workflow-source",
          freshness: "CURRENT",
          review_status: reviewed ? "REVIEWED" : "UNVERIFIED",
          version: 1,
        })),
      ),
    },
    error: null,
    hasOlder: false,
  }),
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
  useAPI: (path: string) => ({
    data: path.endsWith("country-workflows")
      ? {
          country: state.country,
          items: [
            {
              id: "india-msme-payment-timing",
              title: "India MSE payment timing",
              available: state.country === "IN",
              roles,
            },
          ],
          source_contracts: {},
          source_formats: [],
          check_templates: {},
          scenarios: [],
        }
      : path.endsWith("inputs")
        ? { evidence: [], snapshots: [] }
        : path.endsWith("jobs")
          ? { items: [] }
          : undefined,
    error: null,
  }),
}));

beforeEach(() => {
  state.country = "IN";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
});

it("requires explicit buyer and bank/calendar scope, and offers only reviewed role sources", async () => {
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Workflow"), {
    target: { value: "india-msme-payment-timing" },
  });
  for (const role of Object.keys(roles)) {
    const picker = screen.getByLabelText(`${role} source`);
    expect(
      within(picker).getByRole("option", {
        name: new RegExp(`^${role} reviewed`),
      }),
    ).toBeInTheDocument();
    expect(
      within(picker).queryByRole("option", {
        name: new RegExp(`^${role} unreviewed`),
      }),
    ).not.toBeInTheDocument();
    fireEvent.change(picker, { target: { value: role + "-reviewed" } });
  }
  for (const [label, value] of [
    ["Schedule title", "SYNTHETIC MSE review"],
    [
      "Scope and source rationale",
      "Explicit synthetic supplier and invoice acceptance assessment",
    ],
    ["Reconciliation date", "2026-04-30"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  expect(
    await screen.findByText(
      "Declare the MSE buyer identifier before calculating payment timing.",
    ),
  ).toBeVisible();
  expect(state.mutate).not.toHaveBeenCalled();
  for (const [label, value] of [
    ["Buyer identifier", "SYNTHETIC-BUYER"],
    ["First invoice month", "2026-04"],
    ["Last invoice month", "2026-04"],
    ["Bank settlement window starts", "2026-04-01"],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", "INR"],
    ["Bank payment sign", "debit-negative"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    workflow: "india-msme-payment-timing",
    msme_buyer_id: "SYNTHETIC-BUYER",
    account: "SYNTHETIC-ACCOUNT",
    currency: "INR",
    as_of: "2026-04-30",
    obligation_month_start: "2026-04",
    obligation_month_end: "2026-04",
    settlement_start: "2026-04-01",
    bank_payment_sign: "debit-negative",
    source_ids: Object.fromEntries(
      Object.keys(roles).map((role) => [role, role + "-reviewed"]),
    ),
  });
});

it("does not offer the India workflow for a UAE engagement", () => {
  state.country = "AE";
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  expect(
    within(screen.getByLabelText("Workflow")).queryByRole("option", {
      name: "India MSE payment timing",
    }),
  ).not.toBeInTheDocument();
});

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({ mutate: vi.fn(), country: "AE" }));
const roles = {
  books: "merchant-activity",
  processor: "merchant-settlements",
  bank: "transactions",
  allocations: "merchant-bank-allocations",
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
      items: [
        ...Object.entries(roles).map(([role, table_type]) => ({
          id: role,
          label: role + " reviewed",
          kind: "workflow-source",
          table_type,
          freshness: "CURRENT",
          review_status: "REVIEWED",
          version: 1,
        })),
        {
          id: "account-current",
          label: "SYNTHETIC reviewed account",
          kind: "country-workflow",
          workflow: "bank-account-evidence",
          review_status: "REVIEWED",
          freshness: "CURRENT",
          version: 2,
          as_of: "2026-06-30",
          bank_account_scope: {
            account: "ACCT",
            currency: state.country === "AE" ? "AED" : "INR",
          },
        },
      ],
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
              id: "merchant-settlement-bridge",
              title: "Merchant gross to bank",
              available: true,
              roles,
            },
          ],
          source_contracts: Object.fromEntries(
            Object.values(roles).map((kind) => [kind, {}]),
          ),
          source_formats: [],
          check_templates: {},
          scenarios: [],
        }
      : path.endsWith("inputs")
        ? {
            evidence: [
              {
                id: "csv",
                label: "SYNTHETIC processor CSV",
                scan_status: "CLEAN",
              },
            ],
            snapshots: [],
          }
        : path.includes("/events/merchant-result")
          ? {
              id: "merchant-result",
              version: 1,
              kind: "country-workflow",
              freshness: "CURRENT",
              body: {
                title: "SYNTHETIC merchant result",
                workflow: "merchant-settlement-bridge",
                review_status: "UNVERIFIED",
                rows: [
                  {
                    id: "PAYOUT",
                    kind: "MERCHANT_SETTLEMENT",
                    merchant: "SHOP",
                    processor: "PSP",
                    batch: "BATCH-1",
                    currency: "AED",
                    sales: "1000",
                    refunds: "100",
                    chargebacks: "20",
                    fees: "30",
                    fee_tax: "2",
                    withholding: "3",
                    reserve_held: "50",
                    reserve_released: "5",
                    amount: "800",
                    expected_net: "800",
                    bank_allocated: "800",
                    bank_difference: "0",
                    state: "MATCHED",
                  },
                ],
                limitations: [],
                professional_conclusion: "NOT_DETERMINED",
              },
            }
          : { items: [] },
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));
beforeEach(() => {
  state.country = "AE";
  state.mutate
    .mockReset()
    .mockResolvedValue({ id: "queued", status: "queued" });
});

it.each([
  ["AE", "AED"],
  ["IN", "INR"],
])(
  "submits explicit %s bank scope and four independent sources",
  async (country, currency) => {
    state.country = country;
    render(<CountryWorkflows eid="eng" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "merchant-settlement-bridge" },
    });
    for (const role of Object.keys(roles))
      fireEvent.change(screen.getByLabelText(role + " source"), {
        target: { value: role },
      });
    for (const [label, value] of [
      ["Schedule title", "SYNTHETIC settlement"],
      [
        "Scope and source rationale",
        "Independent gross sales and bank allocation evidence",
      ],
      ["Reconciliation date", "2026-06-30"],
      ["Reporting period start", "2026-06-01"],
      ["Bank account identifier", "ACCT"],
      ["Settlement currency", currency],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    expect(
      screen.getByText(/UAE VAT and India GST are assessed fee-tax components/),
    ).toBeVisible();
    fireEvent.change(
      screen.getByLabelText("Reviewed bank account evidence (optional)"),
      { target: { value: "account-current" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    expect(
      await screen.findByText(
        "Assess the linked bank account, original bank identifier and complete review window before calculation.",
      ),
    ).toBeVisible();
    expect(state.mutate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Linked account scope assessment"), {
      target: {
        value:
          "SYNTHETIC original bank number and full June ownership scope assessed",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "merchant-settlement-bridge",
      source_ids: Object.fromEntries(
        Object.keys(roles).map((role) => [role, role]),
      ),
      period_start: "2026-06-01",
      account: "ACCT",
      currency,
      bank_account_review_id: "account-current",
      bank_account_scope_assessment:
        "SYNTHETIC original bank number and full June ownership scope assessed",
    });
  },
);

it("requires independent processor component totals alongside net totals", async () => {
  render(<CountryWorkflows eid="eng" mode="workflow-source" />);
  for (const [label, value] of [
    ["Source table type", "merchant-settlements"],
    ["Clean retained evidence", "csv"],
    ["Schedule title", "SYNTHETIC processor"],
    ["Expected data rows", "1"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const totals = {
    AED: {
      sales: "1000",
      refunds: "100",
      chargebacks: "20",
      fees: "30",
      fee_tax: "2",
      withholding: "3",
      reserve_held: "50",
      reserve_released: "5",
      amount: "800",
    },
  };
  fireEvent.change(
    screen.getByLabelText("Independent merchant component controls (JSON)"),
    { target: { value: JSON.stringify(totals) } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(
    state.mutate.mock.calls[0][0].body.payload.merchant_component_controls,
  ).toEqual(totals);
});

it("shows gross-to-net components and the bank residual separately", () => {
  render(
    <CountryWorkflows
      eid="eng"
      mode="country-workflow"
      initialEvent="merchant-result"
    />,
  );
  for (const label of ["expected net", "bank allocated", "bank difference"])
    expect(screen.getByRole("columnheader", { name: label })).toBeVisible();
  const details = screen.getByRole("region", {
    name: "Merchant settlement components",
  });
  fireEvent.click(
    within(details).getByText("Batch BATCH-1 · SHOP · PSP · AED"),
  );
  expect(within(details).getByText("Gross sales")).toBeVisible();
  expect(within(details).getByText("Less refunds")).toBeVisible();
  expect(within(details).getByText("Less assessed fee tax")).toBeVisible();
});

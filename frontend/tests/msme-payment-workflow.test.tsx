import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  country: "IN",
  freshness: "CURRENT",
}));
const roles = {
  assessments: "msme-supplier-assessments",
  invoices: "msme-invoices",
  bank: "transactions",
  allocations: "item-allocations",
};

const interestRoles = {
  ...roles,
  interest_policies: "msme-interest-policies",
  bank_rates: "msme-bank-rates",
  principal_changes: "msme-principal-changes",
  interest_allocations: "msme-interest-allocations",
  reported: "msme-reported-interest",
};

const taxRoles = {
  ...roles,
  tax_bases: "msme-tax-bases",
  tax_settlements: "msme-tax-settlements",
  interest_pnl: "msme-interest-pnl",
  reported: "msme-tax-reported",
};
const historyRoles = [
  ...Object.entries(interestRoles),
  ...Object.entries(taxRoles)
    .filter(([, type]) => !Object.values(interestRoles).includes(type))
    .map(([role, type]) => [role + "-tax", type]),
];

it.each(["CURRENT", "STALE"])(
  "describes retained document verification honestly for a %s result",
  (freshness) => {
    state.freshness = freshness;
    render(
      <CountryWorkflows
        eid="eng"
        mode="country-workflow"
        initialEvent="msme-result"
      />,
    );
    const scope = screen.getByRole("region", {
      name: "MSE payment-timing scope",
    });
    if (freshness === "STALE") {
      expect(
        within(scope).getByText(/This MSE calculation is not current/),
      ).toBeVisible();
      expect(
        within(scope).queryByText(/retained versions were verified/),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Independent approval" }),
      ).toBeDisabled();
    } else {
      expect(
        within(scope).getByText(
          /retained versions were verified for this calculation/,
        ),
      ).toBeVisible();
      expect(
        within(scope).queryByText(/This MSE calculation is not current/),
      ).not.toBeInTheDocument();
    }
  },
);
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
      items: historyRoles.flatMap(([role, table_type]) =>
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
              id: "india-msme-annual-tax",
              title: "India annual MSE tax",
              available: state.country === "IN",
              roles: taxRoles,
            },
            {
              id: "india-msme-interest",
              title: "India assessed MSE interest",
              available: state.country === "IN",
              roles: interestRoles,
            },
            {
              id: "india-msme-payment-timing",
              title: "India MSE payment timing",
              available: state.country === "IN",
              roles,
            },
          ],
          source_contracts:
            state.country === "IN"
              ? {
                  ...Object.fromEntries(
                    [
                      ...Object.values(interestRoles),
                      ...Object.values(taxRoles),
                    ].map((type) => [type, {}]),
                  ),
                  "msme-supplier-assessments": {},
                  "msme-invoices": {},
                }
              : { transactions: {} },
          source_formats: [],
          check_templates: {},
          scenarios: [],
        }
      : path.endsWith("inputs")
        ? {
            evidence: [
              { id: "csv", label: "SYNTHETIC MSE CSV", scan_status: "CLEAN" },
              {
                id: "packet",
                label: "SYNTHETIC retained context",
                scan_status: "CLEAN",
              },
              {
                id: "unsafe",
                label: "Quarantined packet",
                scan_status: "PENDING",
              },
            ],
            snapshots: [],
          }
        : path.endsWith("jobs")
          ? { items: [] }
          : path.includes("/events/msme-result")
            ? {
                id: "msme-result",
                version: 1,
                kind: "country-workflow",
                freshness: state.freshness,
                body: {
                  title: "SYNTHETIC retained MSE result",
                  workflow: "india-msme-payment-timing",
                  review_status: "REVIEWED",
                  msme_document_binding: "RETAINED_DOCUMENT_BYTES_VERIFIED",
                  rows: [],
                },
              }
            : undefined,
    error: null,
  }),
}));

beforeEach(() => {
  state.country = "IN";
  state.freshness = "CURRENT";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
});

it("queues eight reviewed tax sources with separate annual and post-year observation scope", async () => {
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Workflow"), {
    target: { value: "india-msme-annual-tax" },
  });
  for (const role of Object.keys(taxRoles)) {
    const picker = screen.getByLabelText(`${role} source`);
    const key = role in roles ? role : role + "-tax";
    expect(
      within(picker).queryByRole("option", {
        name: new RegExp(`^${key} unreviewed`),
      }),
    ).not.toBeInTheDocument();
    fireEvent.change(picker, { target: { value: key + "-reviewed" } });
  }
  for (const [label, value] of [
    ["Schedule title", "SYNTHETIC annual tax"],
    [
      "Scope and source rationale",
      "Separate current P&L and previous tax balances with original bank observations",
    ],
    ["Reconciliation date", "2027-03-31"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  expect(
    await screen.findByText(
      "Declare the annual tax-year start and the settlement observation cutoff.",
    ),
  ).toBeVisible();
  expect(state.mutate).not.toHaveBeenCalled();
  for (const [label, value] of [
    ["Annual tax year starts (April 1)", "2026-04-01"],
    ["Settlement observations through", "2027-04-05"],
    ["Buyer identifier", "SYNTHETIC-BUYER"],
    ["First invoice month", "2026-03"],
    ["Last invoice month", "2027-03"],
    ["Bank settlement window starts", "2026-03-01"],
    ["Bank account identifier", "SYNTHETIC-ACCOUNT"],
    ["Account currency", "INR"],
    ["Bank payment sign", "debit-negative"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    workflow: "india-msme-annual-tax",
    tax_year_start: "2026-04-01",
    as_of: "2027-03-31",
    tax_observed_through: "2027-04-05",
    currency: "INR",
    msme_buyer_id: "SYNTHETIC-BUYER",
    source_ids: Object.fromEntries(
      Object.keys(taxRoles).map((role) => [
        role,
        (role in roles ? role : role + "-tax") + "-reviewed",
      ]),
    ),
  });
});

it.each([
  "msme-interest-policies",
  "msme-bank-rates",
  "msme-tax-bases",
  "msme-interest-pnl",
])("binds a clean retained supporting document for %s", async (tableType) => {
  const documentLabel = ["msme-tax-bases", "msme-interest-pnl"].includes(
    tableType,
  )
    ? "MSE annual tax supporting document (optional shared document)"
    : "MSE interest supporting document (optional shared document)";
  render(<CountryWorkflows eid="eng" mode="workflow-source" />);
  for (const [label, value] of [
    ["Source table type", tableType],
    ["Clean retained evidence", "csv"],
    ["Schedule title", "SYNTHETIC assessed interest source"],
    ["Expected data rows", "1"],
    [documentLabel, "packet"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  if (tableType !== "msme-bank-rates")
    fireEvent.change(screen.getByLabelText("Independent totals by currency"), {
      target: { value: "INR=36500" },
    });
  const document = screen.getByLabelText(documentLabel);
  expect(
    within(document).queryByRole("option", { name: "Quarantined packet" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    table_type: tableType,
    evidence_version_id: "csv",
    rule_document_version_id: "packet",
  });
});

it.each(["india-msme-payment-timing", "india-msme-interest"])(
  "requires explicit buyer and bank/calendar scope, with reviewed sources for %s",
  async (workflow) => {
    const selectedRoles =
      workflow === "india-msme-interest" ? interestRoles : roles;
    render(<CountryWorkflows eid="eng" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: workflow },
    });
    expect(
      screen.queryByLabelText(/Compare arrears only/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Tax-year start (for form guidance)"),
    ).not.toBeInTheDocument();
    for (const role of Object.keys(selectedRoles)) {
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
      workflow,
      msme_buyer_id: "SYNTHETIC-BUYER",
      account: "SYNTHETIC-ACCOUNT",
      currency: "INR",
      as_of: "2026-04-30",
      obligation_month_start: "2026-04",
      obligation_month_end: "2026-04",
      settlement_start: "2026-04-01",
      bank_payment_sign: "debit-negative",
      source_ids: Object.fromEntries(
        Object.keys(selectedRoles).map((role) => [role, role + "-reviewed"]),
      ),
    });
  },
);

it("does not offer the India workflow for a UAE engagement", () => {
  state.country = "AE";
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  expect(
    within(screen.getByLabelText("Workflow")).queryByRole("option", {
      name: /India.*MSE/,
    }),
  ).not.toBeInTheDocument();
});

it("selects a distinct clean MSE context and requires a document-scope assessment without manual IDs", async () => {
  render(<CountryWorkflows eid="eng" mode="workflow-source" />);
  for (const [label, value] of [
    ["Source table type", "msme-supplier-assessments"],
    ["Clean retained evidence", "csv"],
    ["Schedule title", "SYNTHETIC supplier evidence"],
    ["Expected data rows", "1"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const context = screen.getByLabelText("MSE context document");
  expect(
    within(context).queryByRole("option", { name: "SYNTHETIC MSE CSV" }),
  ).not.toBeInTheDocument();
  expect(
    within(context).queryByRole("option", { name: "Quarantined packet" }),
  ).not.toBeInTheDocument();
  fireEvent.change(context, { target: { value: "packet" } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  expect(
    await screen.findByText(
      "Assess which supplier or invoice facts the retained MSE context document supports.",
    ),
  ).toBeVisible();
  expect(state.mutate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("MSE context scope assessment"), {
    target: {
      value:
        "Synthetic retained supplier registration and eligibility packet scope",
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    evidence_version_id: "csv",
    table_type: "msme-supplier-assessments",
    msme_context_evidence_version_id: "packet",
    msme_context_assessment:
      "Synthetic retained supplier registration and eligibility packet scope",
  });
  fireEvent.change(screen.getByLabelText("Source table type"), {
    target: { value: "msme-invoices" },
  });
  expect(screen.getByLabelText("MSE context document")).toHaveValue("");
});

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({
  country: "IN",
  tenant: "synthetic",
  currency: "INR" as string | null,
  loaded: true,
  mutate: vi.fn().mockResolvedValue({ id: "job" }),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
  LineageDetail: () => null,
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select?: (value: { tenant: string }) => unknown) => {
    const scope = {
      tenant: state.tenant,
      country: state.country,
      client: "",
      entity: "",
      period: "",
    };
    return select ? select(scope) : scope;
  },
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: {
      items: [
        ...["books", "statement"].map((id) => ({
          id,
          kind: "workflow-source",
          label: id,
          freshness: "CURRENT",
          body: { table_type: "transactions", review_status: "REVIEWED" },
        })),
        ...["tax-book", "tax-return"].map((id) => ({
          id,
          kind: "workflow-source",
          label: id,
          freshness: "CURRENT",
          body: { table_type: "tax-documents", review_status: "REVIEWED" },
        })),
      ],
    },
    hasOlder: false,
  }),
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAction: () => ({ mutateAsync: state.mutate, isPending: false }),
  useAPI: (path: string) => ({
    data: path.endsWith("country-workflows")
      ? state.loaded
        ? {
            country: state.country,
            default_currency: state.currency,
            items: [
              {
                id: "bank-brs",
                title: "Bank",
                roles: { books: "transactions", statement: "transactions" },
              },
              {
                id: "india-gst",
                title: "GST",
                roles: { books: "tax-documents", return: "tax-documents" },
              },
              {
                id: "india-invoice-register",
                title: "Original invoices",
                roles: { books: "tax-documents", invoices: "tax-documents" },
              },
              {
                id: "uae-vat",
                title: "VAT",
                roles: { books: "tax-documents", return: "tax-documents" },
              },
            ].map((item) => ({ ...item, available: true })),
            check_templates: {},
            scenarios: [],
            source_contracts: {},
          }
        : undefined
      : path.includes("/events/")
        ? undefined
        : { items: [], evidence: [], snapshots: [], samples: [] },
  }),
}));
beforeEach(() => {
  state.country = "IN";
  state.tenant = "synthetic";
  state.currency = "INR";
  state.loaded = true;
  state.mutate.mockClear();
});

it.each([
  ["IN", "INR"],
  ["AE", "AED"],
  ["IN", "USD"],
  ["AE", "EUR"],
])(
  "uses the entity currency for a fresh %s common workflow (%s)",
  (country, currency) => {
    state.country = country;
    state.currency = currency;
    render(<CountryWorkflows eid="eng" mode="country-workflow" />);
    expect(
      screen.getByRole("textbox", { name: "Account currency" }),
    ).toHaveValue(currency);
  },
);

it("adapts to delayed metadata, preserves an explicit foreign choice on refresh, and scopes it to the engagement", () => {
  state.loaded = false;
  const view = render(<CountryWorkflows eid="first" mode="country-workflow" />);
  state.loaded = true;
  view.rerender(<CountryWorkflows eid="first" mode="country-workflow" />);
  const input = screen.getByRole("textbox", {
    name: "Account currency",
  });
  expect(input).toHaveValue("INR");
  fireEvent.change(input, { target: { value: "USD" } });
  state.currency = "EUR";
  view.rerender(<CountryWorkflows eid="first" mode="country-workflow" />);
  expect(input).toHaveValue("USD");
  view.rerender(<CountryWorkflows eid="second" mode="country-workflow" />);
  expect(input).toHaveValue("EUR");
  fireEvent.change(input, { target: { value: "GBP" } });
  state.tenant = "other-synthetic";
  state.currency = "CAD";
  view.rerender(<CountryWorkflows eid="second" mode="country-workflow" />);
  expect(input).toHaveValue("CAD");
});

it("uses fixed reporting currency for GST and VAT while preserving an explicit common-account currency", () => {
  state.currency = "USD";
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  const input = () =>
    screen.getByRole("textbox", {
      name: "Account currency",
    });
  fireEvent.change(input(), { target: { value: "EUR" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Workflow" }), {
    target: { value: "india-gst" },
  });
  expect(
    screen.getByRole("textbox", { name: "Reporting currency" }),
  ).toHaveValue("INR");
  expect(
    screen.getByRole("textbox", { name: "Reporting currency" }),
  ).toHaveAttribute("readonly");
  fireEvent.change(screen.getByRole("combobox", { name: "Workflow" }), {
    target: { value: "uae-vat" },
  });
  expect(
    screen.getByRole("textbox", { name: "Reporting currency" }),
  ).toHaveValue("AED");
  fireEvent.change(screen.getByRole("combobox", { name: "Workflow" }), {
    target: { value: "bank-brs" },
  });
  expect(input()).toHaveValue("EUR");
  expect(input()).not.toHaveAttribute("readonly");
});

it("queues the explicit original-invoice currency rather than substituting INR", async () => {
  state.currency = "INR";
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  fireEvent.change(screen.getByRole("combobox", { name: "Workflow" }), {
    target: { value: "india-invoice-register" },
  });
  fireEvent.change(
    screen.getByRole("textbox", {
      name: "Invoice comparison currency",
    }),
    { target: { value: "USD" } },
  );
  fireEvent.change(
    screen.getByRole("combobox", {
      name: "Invoice comparison direction",
    }),
    { target: { value: "purchase" } },
  );
  fireEvent.change(screen.getByRole("combobox", { name: "books source" }), {
    target: { value: "tax-book" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "invoices source" }), {
    target: { value: "tax-return" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Schedule title" }), {
    target: { value: "SYNTHETIC original invoice USD" },
  });
  fireEvent.change(screen.getByLabelText("Reconciliation date"), {
    target: { value: "2026-06-30" },
  });
  fireEvent.change(
    screen.getByRole("textbox", {
      name: "Scope and source rationale",
    }),
    {
      target: { value: "SYNTHETIC original USD amounts without FX conversion" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await vi.waitFor(() =>
    expect(state.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          operation: "country-workflow",
          payload: expect.objectContaining({
            currency: "USD",
            invoice_direction: "purchase",
          }),
        },
      }),
    ),
  );
});

it("keeps a missing configured currency blank instead of inventing AED", () => {
  state.country = "GB";
  state.currency = null;
  render(<CountryWorkflows eid="eng" mode="country-workflow" />);
  expect(screen.getByRole("textbox", { name: "Account currency" })).toHaveValue(
    "",
  );
});

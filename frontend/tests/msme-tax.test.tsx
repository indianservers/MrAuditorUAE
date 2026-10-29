import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MSMETaxDetails, type MSMETaxBody } from "@/features/msme-tax";

const state = vi.hoisted(() => ({
  freshness: "CURRENT",
  paths: [] as string[],
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => {
    state.paths.push(path);
    const last = path.includes("tax_invoice_offset=10");
    return {
      error: null,
      data: {
        freshness: state.freshness,
        collection_totals: { invoice_tax_details: 11 },
        body: {
          invoice_tax_details: Array.from(
            { length: last ? 1 : 10 },
            (_, i) => ({
              id: `I-${last ? 10 : i}`,
              reference: `INV-${last ? 10 : i}`,
              closing_disallowed_carry: "50",
              tax_basis: {
                amount: "100",
                opening_paid_basis: "0",
                opening_disallowed_basis: "50",
                opening_previously_allowed_unpaid: "50",
                otherwise_allowable: true,
              },
              tax_settlements: [
                {
                  id: "ADVANCE",
                  mode: "ASSESSED_BANK_ADVANCE_APPLICATION",
                  payment_day: "2027-03-31",
                  original_bank_allocation: {
                    payment_date: "2026-03-15",
                    amount: "100",
                  },
                  amount: "100",
                },
              ],
            }),
          ),
        },
      },
    };
  },
}));
beforeEach(() => {
  state.paths = [];
  state.freshness = "CURRENT";
});
const body: MSMETaxBody = {
  tax_year_start: "2026-04-01",
  as_of: "2027-03-31",
  tax_observed_through: "2027-04-05",
  timing_observed_through: "2027-04-05",
  tax_reference: "2025:37(2)(g)",
  net_expected_tax_adjustment: "-35",
  principal_timing_exception_count: 2,
  msme_tax_document_binding: "RETAINED_DOCUMENT_BYTES_VERIFIED",
  tax_totals: {
    INTEREST_PNL_DISALLOWANCE: {
      expected_amount: "15",
      expected_complete: true,
      reported_amount: "15",
      reported_complete: true,
    },
    CURRENT_PRINCIPAL_DISALLOWANCE: {
      expected_amount: "100",
      expected_complete: true,
      reported_amount: "100",
      reported_complete: true,
    },
    PRIOR_PRINCIPAL_RELEASE: {
      expected_amount: "150",
      expected_complete: true,
      reported_amount: "150",
      reported_complete: true,
    },
  },
  form26_targets: {
    INTEREST_PNL_DISALLOWANCE: "33(a)",
    CURRENT_PRINCIPAL_DISALLOWANCE: "33(b)",
    PRIOR_PRINCIPAL_RELEASE: "33(c)",
  },
};

it("keeps three adjustments, annual cutoff and observation date separate", () => {
  render(
    <MSMETaxDetails eid="eng" eventId="event" tenant="tenant" body={body} />,
  );
  expect(screen.getByText(/year-end cutoff 2027-03-31/)).toHaveTextContent(
    "Settlement observations through 2027-04-05",
  );
  expect(screen.getByText(/Net expected adjustment/)).toHaveTextContent(
    "INR -35",
  );
  expect(
    screen.getByText(/Principal timing exceptions at 2027-04-05/),
  ).toHaveTextContent("2");
  expect(
    screen.getByRole("table", { name: "Separate MSE tax adjustments" }),
  ).toHaveTextContent("Form 26 33(c)");
  expect(
    screen.getByText(/Closing accrued interest is not a P&L charge/),
  ).toBeVisible();
});

it("pages invoice evidence independently and preserves original advance cash and assessed application dates", () => {
  render(
    <MSMETaxDetails eid="eng" eventId="event" tenant="tenant" body={body} />,
  );
  const invoice = screen.getByText(/INV-0 —/).closest("details")!;
  fireEvent.click(within(invoice).getByText(/INV-0 —/));
  fireEvent.click(
    within(invoice).getByText("Tax settlements and original bank links (1)"),
  );
  const table = within(invoice).getByRole("table", {
    name: "Tax settlements and original bank links",
  });
  expect(table).toHaveTextContent("2027-03-31");
  expect(table).toHaveTextContent("2026-03-15");
  fireEvent.click(screen.getByRole("button", { name: "Next invoices" }));
  expect(screen.getByText(/INV-10 —/)).toBeVisible();
  expect(screen.queryByText(/INV-0 —/)).not.toBeInTheDocument();
  expect(state.paths.at(-1)).toContain(
    "limit=1&tax_invoice_offset=10&tax_invoice_limit=10",
  );
  expect(screen.getByRole("button", { name: "Next invoices" })).toBeDisabled();
});

it("labels partial totals and unresolved net without losing financial precision or stale status", () => {
  state.freshness = "STALE";
  const exact = "999999999999999999.12345678";
  render(
    <MSMETaxDetails
      eid="eng"
      eventId="event"
      tenant="tenant"
      body={{
        ...body,
        net_expected_tax_adjustment: null,
        tax_totals: {
          CURRENT_PRINCIPAL_DISALLOWANCE: {
            expected_amount: exact,
            expected_complete: false,
            reported_amount: "0",
            reported_complete: false,
          },
        },
      }}
    />,
  );
  expect(screen.getByText(/Net expected adjustment/)).toHaveTextContent(
    "INR Unresolved",
  );
  const amounts = screen.getByRole("table", {
    name: "Separate MSE tax adjustments",
  });
  expect(within(amounts).getByText("Partial subtotal: " + exact)).toBeVisible();
  expect(
    screen.getByText(/saved tax calculation is not current/),
  ).toBeVisible();
});

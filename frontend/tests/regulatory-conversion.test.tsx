import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RegulatoryAssessmentPanel } from "@/features/regulatory-assessment";

const state = vi.hoisted(() => ({ mutate: vi.fn(), older: vi.fn() }));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (s: { country: string }) => unknown) =>
    select({ country: "AE" }),
}));
vi.mock("@/hooks/use-event-history", () => ({
  useEventHistory: () => ({
    data: {
      items: [
        {
          id: "lead",
          kind: "lead",
          label: "Reviewed source",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
        {
          id: "rates",
          kind: "workflow-source",
          table_type: "fx-rates",
          label: "Reviewed quotes",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
        {
          id: "conversion",
          kind: "regulatory-conversion",
          label: "Reviewed conversion",
          review_status: "REVIEWED",
          freshness: "CURRENT",
        },
        {
          id: "unverified",
          kind: "regulatory-conversion",
          label: "Unverified conversion",
          review_status: "UNVERIFIED",
          freshness: "CURRENT",
        },
      ],
    },
    error: null,
    hasOlder: true,
    loadingOlder: false,
    loadOlder: state.older,
  }),
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: path.endsWith("country-workflows")
      ? { country: "AE" }
      : path.startsWith("regulatory/rules")
        ? {
            items: [
              {
                id: "rule",
                rule_key: "AE-SYNTHETIC",
                version: 1,
                state: "PUBLISHED",
                body: {
                  method: "flat_rate",
                  calculation_currency: "AED",
                  framework: "IFRS",
                  effective_from: "2026-01-01",
                },
              },
            ],
          }
        : {
            collection_totals: { rows: 101 },
            body: {
              rows: [
                {
                  id: path.endsWith("offset=100") ? "FX101" : "FX1",
                  source_currency: "USD",
                  target_currency: "AED",
                  rate: "4",
                  method: "period-average",
                  rate_date: "2026-12-31",
                },
              ],
            },
          },
    error: null,
    isFetching: false,
  }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => {
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "prepared" });
  state.older.mockReset();
});

it("requires explicit rounding and preserves the selected quote across rate pages", async () => {
  render(<RegulatoryAssessmentPanel eid="engagement" />);
  fireEvent.click(
    screen.getByText("Prepare explicit source currency conversion"),
  );
  const button = screen.getByRole("button", {
    name: "Prepare currency conversion for review",
  });
  expect(button).toBeDisabled();
  fireEvent.change(
    screen.getByLabelText("Reviewed source schedule (required for arithmetic)"),
    { target: { value: "lead" } },
  );
  fireEvent.change(screen.getByLabelText("Reviewed exchange rate source"), {
    target: { value: "rates" },
  });
  fireEvent.change(screen.getByLabelText("Exchange rate row"), {
    target: { value: "FX1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Next rate rows" }));
  expect(screen.getByLabelText("Exchange rate row")).toHaveValue("FX1");
  for (const [label, value] of [
    ["Currency conversion title", "Reviewed reporting-base conversion"],
    ["Conversion decimal places", "2"],
    ["Conversion rounding", "half-up"],
    ["Independent converted amount", "400.80"],
    [
      "Conversion basis and rounding assessment",
      "Retained direct quote and explicit rounding assessed independently",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(button);
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0]).toMatchObject({
    path: "regulatory/engagements/engagement/conversions",
    body: {
      source_event_id: "lead",
      rate_source_id: "rates",
      rate_row_id: "FX1",
      decimal_places: 2,
      rounding: "half-up",
      target_amount: "400.80",
    },
  });
  expect(
    await screen.findByRole("link", {
      name: "Review prepared currency conversion",
    }),
  ).toHaveAttribute("href", "/intelligence/engagement/lead?event=prepared");
});

it("uses only independently reviewed conversions and retains older-source access", async () => {
  render(<RegulatoryAssessmentPanel eid="engagement" />);
  expect(
    screen.queryByRole("option", { name: "Unverified conversion" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Published rule versions"), {
    target: { value: "rule" },
  });
  fireEvent.change(
    screen.getByLabelText("Reviewed source schedule (required for arithmetic)"),
    { target: { value: "lead" } },
  );
  fireEvent.change(
    screen.getByLabelText("Reviewed currency conversion (optional)"),
    { target: { value: "conversion" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Load older source schedules" }),
  );
  expect(state.older).toHaveBeenCalledOnce();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Evaluate current rules and retain receipt",
    }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body).toMatchObject({
    source_event_id: "lead",
    conversion_event_id: "conversion",
    rule_ids: ["rule"],
  });
});

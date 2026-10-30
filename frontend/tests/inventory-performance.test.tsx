import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  InventoryPerformance,
  InventoryPerformanceEvidence,
} from "@/features/inventory-performance";

const state = vi.hoisted(() => ({ currency: "AED", mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
  useAPI: (path: string) => ({
    isFetching: false,
    error: null,
    data: path.includes("inventory-performance-options")
      ? {
          currency: state.currency,
          current: [{ id: "current", label: "Current source" }],
          prior: [{ id: "prior", label: "Earlier source" }],
          truncated: {},
        }
      : path.includes("inventory_performance_offset=20")
        ? {
            body: {
              inventory_performance_links: [
                { account_code: "LAST", normalized_amount: "0" },
              ],
            },
          }
        : path.includes("/accounts?")
          ? {
              items: path.includes("search=extra")
                ? [
                    {
                      id: "current-extra",
                      code: "EXTRA",
                      name: "Extra inventory",
                    },
                  ]
                : ["inventory", "revenue", "cost_of_sales"].map((metric) => ({
                    id: `${path.includes("snapshot_id=prior") ? "prior" : "current"}-${metric}`,
                    code: metric,
                    name: metric,
                  })),
            }
          : undefined,
  }),
}));

beforeEach(() => {
  state.currency = "AED";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "generated" });
});

function fill() {
  fireEvent.click(
    screen.getByText(
      "Review stock and gross-profit trends from committed accounts",
    ),
  );
  for (const side of ["current", "prior"]) {
    fireEvent.change(screen.getByLabelText(`${side} stock/GP snapshot`), {
      target: { value: side },
    });
    for (const metric of ["inventory", "revenue", "cost_of_sales"]) {
      const name = `${side} ${metric.replaceAll("_", " ")}`;
      fireEvent.change(
        screen.getByLabelText(`${name} accounts`, { exact: true }),
        { target: { value: `${side}-${metric}` } },
      );
      fireEvent.change(
        screen.getByLabelText(`Independent ${name} account count`),
        { target: { value: "1" } },
      );
      fireEvent.change(screen.getByLabelText(`Independent ${name} amount`), {
        target: { value: "100.12345678" },
      });
      fireEvent.change(
        screen.getByLabelText(`${name} account scope assessment`),
        {
          target: {
            value:
              "Independent source account classification and completeness assessment",
          },
        },
      );
    }
  }
  for (const [label, value] of [
    ["Stock/GP periods assessed comparable", "yes"],
    [
      "Stock/GP period comparability assessment",
      "Independent policy and period comparability assessment",
    ],
    ["Stock-change review threshold (%)", "10"],
    ["Gross-profit margin change threshold (percentage points)", "3"],
    ["Stock/GP display decimal places", "2"],
    ["Stock/GP display rounding", "HALF_UP"],
    ["Stock/GP review title", "Synthetic comparison"],
    [
      "Stock/GP source rationale",
      "Independent selected accounts and separate source controls",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("committed stock and gross-profit scope", () => {
  it.each(["AED", "INR", "USD"])(
    "retains the entity functional currency %s without legal or account defaults",
    async (currency) => {
      state.currency = currency;
      const created = vi.fn();
      render(<InventoryPerformance eid="E" onCreated={created} />);
      expect(
        screen.getByRole("button", { name: "Prepare stock and GP review" }),
      ).toBeDisabled();
      fill();
      fireEvent.click(
        screen.getByRole("button", { name: "Prepare stock and GP review" }),
      );
      await waitFor(() => expect(created).toHaveBeenCalledWith("generated"));
      const request = state.mutate.mock.calls[0][0];
      expect(request.path).toBe(
        "intelligence/engagements/E/inventory-performance",
      );
      expect(request.body).toMatchObject({
        currency,
        periods_comparable: true,
        gp_change_threshold_pp: "3",
        rounding_places: 2,
        current: {
          snapshot_id: "current",
          inventory: {
            account_ids: ["current-inventory"],
            expected_accounts: 1,
            expected_amount: "100.12345678",
          },
        },
        prior: { snapshot_id: "prior" },
      });
    },
  );

  it("retains selected accounts outside the search and clears scopes on snapshot change", () => {
    render(<InventoryPerformance eid="E" onCreated={vi.fn()} />);
    fill();
    fireEvent.change(screen.getByLabelText("Find current inventory accounts"), {
      target: { value: "extra" },
    });
    fireEvent.change(
      screen.getByLabelText("current inventory accounts", { exact: true }),
      { target: { value: "current-extra" } },
    );
    expect(
      screen.getByText(
        "2 selected, including selections outside the current search.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Prepare stock and GP review" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("current stock/GP snapshot"), {
      target: { value: "" },
    });
    expect(
      screen.getByLabelText("Independent current inventory amount"),
    ).toHaveValue("");
    expect(
      screen.getByLabelText("Independent current inventory account count"),
    ).toHaveValue("");
  });

  it("requires an explicit zero inventory assessment before accepting a zero control", () => {
    render(<InventoryPerformance eid="E" onCreated={vi.fn()} />);
    fill();
    fireEvent.change(
      screen.getByLabelText("Independent current inventory amount"),
      { target: { value: "0.00" } },
    );
    expect(
      screen.getByRole("button", { name: "Prepare stock and GP review" }),
    ).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText(
        "current zero inventory assessment (required for zero)",
      ),
      {
        target: {
          value:
            "Independent zero ledger balance assessment; no physical conclusion",
        },
      },
    );
    expect(
      screen.getByRole("button", { name: "Prepare stock and GP review" }),
    ).toBeEnabled();
  });

  it("pages complete account lineage without hiding zero or changing controls", () => {
    render(
      <InventoryPerformanceEvidence
        prefix="/audit"
        selected="R"
        initial={[{ account_code: "FIRST", normalized_amount: "1" }]}
        total={21}
        controls={[
          { metric: "inventory", expected_amount: "0", calculated_amount: "0" },
        ]}
        scope={{
          currency: "INR",
          periods_comparable: true,
          comparability_assessment: "Independently assessed",
        }}
        observation="Source-supported arithmetic observation"
      />,
    );
    fireEvent.click(screen.getByText("Stock/GP account lineage · 21"));
    fireEvent.click(
      screen.getByRole("button", { name: "Next stock/GP account links" }),
    );
    expect(screen.getByRole("cell", { name: "LAST" })).toBeVisible();
    expect(
      within(
        screen.getByRole("table", { name: "Stock/GP account lineage" }),
      ).getByRole("cell", { name: "0" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next stock/GP account links" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Previous stock/GP account links" }),
    );
    expect(screen.getByRole("cell", { name: "FIRST" })).toBeVisible();
  });
});

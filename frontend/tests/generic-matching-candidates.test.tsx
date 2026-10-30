import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AccountingIntelligence } from "@/features/accounting-intelligence";

const state = vi.hoisted(() => ({
  kind: "reconciliation",
  freshness: "CURRENT",
  reviewed: false,
  workflow: "",
  stockContract: "",
  detailId: "result",
  detailStatus: "ready",
  refetch: vi.fn(),
  legacy: false,
  unmatched: 1,
  findings: 0,
  binding: false,
  mutate: vi.fn().mockResolvedValue({ id: "job" }),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("event=result"),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: () => ({ tenant: "synthetic" }),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
  LineageDetail: () => null,
}));
vi.mock("@xyflow/react", () => ({
  ReactFlow: () => null,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));
vi.mock("@/features/country-workflows", () => ({
  CountryWorkflows: () => null,
}));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutate: state.mutate,
    mutateAsync: state.mutate,
    isPending: false,
  }),
  useAPI: (path: string) => {
    const params = new URL(path, "http://synthetic.invalid").searchParams;
    if (path.includes("/bank-candidates?")) {
      const offset = Number(params.get("offset"));
      return {
        data: {
          left: {
            id: params.get("left_id"),
            reference: "GL-REFERENCE",
            counterparty: "",
            amount: "1",
            currency: "AED",
            date: "2026-06-01",
          },
          items: Array.from({ length: Math.min(25, 121 - offset) }, (_, i) => ({
            id: `R${offset + i}`,
            reference: `ORIGINAL-${offset + i}`,
            counterparty: "شركة ألف",
            amount: "1",
            currency: "AED",
            date: "2026-06-01",
          })),
          total: 121,
        },
      };
    }
    if (path.includes("events/result?")) {
      if (state.detailStatus !== "ready")
        return {
          data: undefined,
          isLoading: state.detailStatus === "loading",
          error:
            state.detailStatus === "error"
              ? new Error("Synthetic detail request failed")
              : null,
          refetch: state.refetch,
        };
      const offset = Number(params.get("ambiguity_offset") || 0);
      return {
        data: {
          id: state.detailId,
          kind: state.kind,
          version: 1,
          freshness: state.freshness,
          body: {
            review_status: state.reviewed ? "REVIEWED" : "UNVERIFIED",
            workflow: state.workflow || undefined,
            quantity_coverage_contract: state.stockContract || undefined,
            bank_account_binding: state.binding
              ? {
                  matching_account_code: "100",
                  original_account_code: "00000123",
                  assessment:
                    "Reviewed single original account mapped to the GL",
                }
              : undefined,
            review_decision_summary: {
              proposed_matches: 0,
              accepted_matches: 0,
              unmatched_transactions: state.unmatched,
              unmatched_with_findings: state.findings,
            },
            matching_contract: state.legacy
              ? undefined
              : "indexed-transaction-candidates/1",
            ambiguous: Array.from(
              { length: Math.min(25, 121 - offset) },
              (_, i) => ({
                left_id: `L${offset + i}`,
                candidate_count: 121,
                candidate_ids: ["R0"],
              }),
            ),
            matches: [],
            unmatched_left: [{ id: "L0", amount: "1" }],
            unmatched_right: [],
          },
          collection_totals: {
            ambiguous: 121,
            unmatched_left: state.unmatched,
            unmatched_right: 0,
            matches: 0,
          },
        },
      };
    }
    if (path.endsWith("inputs"))
      return {
        data: {
          snapshots: [],
          evidence: [
            {
              id: "source-original",
              label: "Synthetic original bank file",
              scan_status: "CLEAN",
            },
          ],
          samples: [],
        },
      };
    if (path.includes("capabilities")) return { data: { lead_sections: [] } };
    return { data: { items: [], total: 0 } };
  },
}));
beforeEach(() => {
  state.kind = "reconciliation";
  state.freshness = "CURRENT";
  state.reviewed = false;
  state.workflow = "";
  state.stockContract = "";
  state.detailId = "result";
  state.detailStatus = "ready";
  state.refetch.mockClear();
  state.legacy = false;
  state.unmatched = 1;
  state.findings = 0;
  state.binding = false;
  state.mutate.mockClear();
});
it("connects complete generic reconciliation candidates with independent item and candidate pagination", () => {
  render(<AccountingIntelligence eid="e" area="reconciliation" />);
  const viewer = screen.getByRole("region", {
    name: "Transaction matching candidates",
  });
  for (let i = 0; i < 4; i++)
    fireEvent.click(
      within(viewer).getByRole("button", { name: "Next ambiguous items" }),
    );
  fireEvent.click(
    within(viewer).getByRole("button", {
      name: "Inspect L120 · 121 candidates",
    }),
  );
  for (let i = 0; i < 4; i++)
    fireEvent.click(
      within(viewer).getByRole("button", { name: "Next candidates" }),
    );
  expect(
    within(viewer).getByRole("cell", { name: "R120" }),
  ).toBeInTheDocument();
  expect(
    within(viewer).getByRole("cell", { name: "ORIGINAL-120" }),
  ).toBeInTheDocument();
  expect(
    within(viewer).getByRole("button", { name: "Next candidates" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next 100" })).toBeDisabled();
  expect(state.mutate).not.toHaveBeenCalled();
});
it("shows recalculation guidance for historical generic results with incomplete candidates", () => {
  state.legacy = true;
  render(<AccountingIntelligence eid="e" area="reconciliation" />);
  expect(screen.getByRole("note")).toHaveTextContent(
    "Recalculate this historical matching result",
  );
  expect(
    screen.queryByRole("button", { name: /Inspect L/ }),
  ).not.toBeInTheDocument();
});
it("does not interpret another result kind as a reconciliation candidate population", () => {
  state.kind = "lead";
  render(<AccountingIntelligence eid="e" area="lead" />);
  expect(
    screen.queryByRole("region", { name: "Transaction matching candidates" }),
  ).not.toBeInTheDocument();
});

vi.mock("@/hooks/use-event-history", async () => {
  const { useAPI } = await import("@/hooks/use-api");
  return {
    useEventHistory: (prefix: string) => ({
      ...useAPI(`${prefix}/events?limit=100&newest=true`),
      hasOlder: false,
      loadingOlder: false,
      loadOlder: vi.fn(),
    }),
  };
});

it("shows full-population review counts even when a result page contains fewer rows", () => {
  state.unmatched = 242;
  state.findings = 17;
  render(<AccountingIntelligence eid="e" area="reconciliation" />);
  expect(
    screen.getByRole("complementary", {
      name: "Reconciliation review decisions",
    }),
  ).toHaveTextContent("17 of 242");
  expect(screen.getByRole("button", { name: "Next 100" })).toBeEnabled();
});

it("retains the original account identity and mapping assessment in source review", () => {
  state.kind = "source-table";
  state.binding = true;
  render(<AccountingIntelligence eid="e" area="source-table" />);
  const scope = screen.getByRole("complementary", {
    name: "Bank account matching scope",
  });
  expect(scope).toHaveTextContent("00000123");
  expect(scope).toHaveTextContent("Matching GL account: 100");
  expect(scope).toHaveTextContent("Reviewed single original account");
  expect(
    within(scope).getByRole("link", { name: "Bank balance reconciliation" }),
  ).toHaveAttribute("href", "/intelligence/e/country-workflow");
});
it("queues an explicit source account declaration without changing the original file", async () => {
  state.kind = "source-table";
  render(<AccountingIntelligence eid="e" area="source-table" />);
  fireEvent.change(screen.getByLabelText("Evidence version"), {
    target: { value: "source-original" },
  });
  fireEvent.change(
    screen.getByLabelText("Bank matching GL account label (optional)"),
    { target: { value: "100" } },
  );
  fireEvent.change(screen.getByLabelText("Bank account mapping assessment"), {
    target: {
      value:
        "Reviewed the single original statement account against this GL code",
    },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Queue supporting tables" }),
  );
  await vi.waitFor(() =>
    expect(state.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          operation: "source-table",
          payload: expect.objectContaining({
            evidence_version_id: "source-original",
            bank_account_label: "100",
            bank_account_mapping_rationale:
              "Reviewed the single original statement account against this GL code",
          }),
        },
      }),
    ),
  );
  fireEvent.change(
    screen.getByLabelText("Bank matching GL account label (optional)"),
    { target: { value: "" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Queue supporting tables" }),
  );
  await vi.waitFor(() =>
    expect(state.mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        body: {
          operation: "source-table",
          payload: expect.objectContaining({
            bank_account_label: "",
            bank_account_mapping_rationale:
              "Reviewed the single original statement account against this GL code",
          }),
        },
      }),
    ),
  );
});

it.each([
  ["CURRENT", true, "", "", true],
  ["STALE", true, "", "", false],
  ["CURRENT", false, "", "", false],
  ["CURRENT", true, "stock-audit", "", false],
  ["CURRENT", true, "stock-audit", "stock-declared-count-coverage/1", true],
])(
  "gates new papers by freshness, review and stock coverage (%s/%s/%s/%s)",
  (freshness, reviewed, workflow, contract, enabled) => {
    state.freshness = String(freshness);
    state.reviewed = Boolean(reviewed);
    state.workflow = String(workflow);
    state.stockContract = String(contract);
    render(<AccountingIntelligence eid="e" area="lead" />);
    const button = screen.getByRole("button", {
      name: "Create connected working-paper draft",
    });
    if (enabled) expect(button).toBeEnabled();
    else {
      expect(button).toBeDisabled();
      fireEvent.click(button);
      expect(state.mutate).not.toHaveBeenCalled();
    }
  },
);

it("retains a directly opened stale report in its result selector without enabling approval", () => {
  state.kind = "statutory-report";
  state.freshness = "STALE";
  render(<AccountingIntelligence eid="e" area="lead" />);
  const select = screen.getByRole("combobox", { name: "Result version" });
  expect(select).toHaveValue("result");
  expect(
    within(select).getByRole("option", {
      name: /Selected retained result.*STALE/,
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Record independent approval" }),
  ).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "This saved report is STALE",
  );
  expect(state.mutate).not.toHaveBeenCalled();
});

it("does not name a different result as the selected historical event", () => {
  state.detailId = "different-result";
  render(<AccountingIntelligence eid="e" area="lead" />);
  const select = screen.getByRole("combobox", { name: "Result version" });
  expect(
    within(select).queryByRole("option", { name: /Selected retained result/ }),
  ).not.toBeInTheDocument();
  expect(state.mutate).not.toHaveBeenCalled();
});

it("retains the requested ID while report detail loads and then shows the authorized stale result", () => {
  state.kind = "statutory-report";
  state.freshness = "STALE";
  state.detailStatus = "loading";
  const view = render(<AccountingIntelligence eid="e" area="lead" />);
  const select = screen.getByRole("combobox", { name: "Result version" });
  expect(select).toHaveValue("result");
  expect(
    within(select).getByRole("option", { name: "Loading selected result…" }),
  ).toBeDisabled();
  expect(screen.getByText("Loading authorized records…")).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Select a result" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Record independent approval" }),
  ).not.toBeInTheDocument();
  state.detailStatus = "ready";
  view.rerender(<AccountingIntelligence eid="e" area="lead" />);
  expect(select).toHaveValue("result");
  expect(
    screen.queryByText("Loading authorized records…"),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Record independent approval" }),
  ).toBeDisabled();
  expect(state.mutate).not.toHaveBeenCalled();
});

it("shows a failed detail request and retries that request without treating it as an empty selection", () => {
  state.detailStatus = "error";
  render(<AccountingIntelligence eid="e" area="lead" />);
  const select = screen.getByRole("combobox", { name: "Result version" });
  expect(select).toHaveValue("result");
  expect(
    within(select).getByRole("option", { name: "Selected result unavailable" }),
  ).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Synthetic detail request failed",
  );
  expect(
    screen.queryByRole("heading", { name: "Select a result" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Retry selected result" }),
  );
  expect(state.refetch).toHaveBeenCalledOnce();
  expect(state.mutate).not.toHaveBeenCalled();
});

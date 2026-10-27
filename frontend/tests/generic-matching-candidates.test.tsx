import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AccountingIntelligence } from "@/features/accounting-intelligence";

const state = vi.hoisted(() => ({
  kind: "reconciliation",
  legacy: false,
  unmatched: 1,
  findings: 0,
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
      const offset = Number(params.get("ambiguity_offset") || 0);
      return {
        data: {
          id: "result",
          kind: state.kind,
          version: 1,
          freshness: "CURRENT",
          body: {
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
      return { data: { snapshots: [], evidence: [], samples: [] } };
    if (path.includes("capabilities")) return { data: { lead_sections: [] } };
    return { data: { items: [], total: 0 } };
  },
}));
beforeEach(() => {
  state.kind = "reconciliation";
  state.legacy = false;
  state.unmatched = 1;
  state.findings = 0;
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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AccountingIntelligence } from "@/features/accounting-intelligence";

const state = vi.hoisted(() => ({
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
  useAPI: (path: string) => ({
    data: path.endsWith("foundation-status")
      ? {
          runtime: "available",
          professional_correctness: "not_assessed",
          period: { state: "OPEN", version: 1 },
          job_counts: { failed: 1 },
        }
      : path.endsWith("inputs")
        ? {
            snapshots: [{ id: "snapshot", label: "Synthetic GL" }],
            evidence: [],
            samples: [],
          }
        : path.includes("events/result?")
          ? {
              id: "result",
              kind: "foundation-validation",
              version: 1,
              freshness: "CURRENT",
              body: {
                execution_status: "succeeded",
                completeness: "partial",
                review_status: "UNVERIFIED",
                issues: [
                  {
                    code: "missing_evidence",
                    reason: "Missing independently reviewed extraction",
                    blocking: true,
                    remediation: "Review document fields",
                    url: "/intelligence/e/ocr",
                  },
                ],
              },
            }
          : path.includes("events?")
            ? { items: [] }
            : path.endsWith("jobs")
              ? { items: [] }
              : path.includes("capabilities")
                ? { lead_sections: [] }
                : { items: [], total: 0 },
  }),
}));

describe("foundation validation workspace", () => {
  it("shows independent control states and navigable blockers, and queues the actual operation", async () => {
    render(<AccountingIntelligence eid="e" area="foundation-validation" />);
    expect(
      screen.getByRole("heading", { name: "Foundation validation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Blocker: Missing independently reviewed extraction/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open affected workspace" }),
    ).toHaveAttribute("href", "/intelligence/e/ocr");
    expect(
      screen.getByText(/Professional correctness: not assessed/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Committed snapshot"), {
      target: { value: "snapshot" },
    });
    fireEvent.change(
      screen.getByLabelText("Auditor rationale / review comments"),
      { target: { value: "Synthetic review scope and rationale" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Queue foundation validation" }),
    );
    await waitFor(() =>
      expect(state.mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          path: "intelligence/engagements/e/jobs",
          body: {
            operation: "foundation-validation",
            payload: {
              snapshot_id: "snapshot",
              extraction_ids: [],
              assessment_ids: [],
              document_links: [],
              rationale: "Synthetic review scope and rationale",
            },
          },
        }),
      ),
    );
  });
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

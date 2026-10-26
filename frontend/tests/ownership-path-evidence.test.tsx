import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { OwnershipPathEvidence } from "@/features/ownership-path-evidence";

vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: path.includes("ownership_path_offset=100")
      ? {
          body: {
            ownership_paths: [
              {
                path_id: "PATH-LAST",
                person_id: "PERSON-LAST",
                kind: "natural-person",
                economic_fraction: "0.25",
                source_graph_complete: false,
              },
            ],
          },
        }
      : path.includes("ownership_step_offset=100")
        ? {
            body: {
              ownership_path_steps: [
                {
                  path_id: "PATH-LAST",
                  edge_source_id: "EDGE-LAST",
                  evidence_reference: "SOURCE-PAGE-9",
                },
              ],
            },
          }
        : undefined,
    error: null,
    isFetching: false,
  }),
}));

describe("retained ownership path evidence", () => {
  it("pages complete source steps independently from calculated paths", () => {
    render(
      <OwnershipPathEvidence
        prefix="/audit"
        selected="result"
        scope={{
          country: "AE",
          as_of: "2026-06-30",
          threshold: "0.25",
          comparison: "greater-than",
          policy_evidence_reference: "SYN-REVIEWED-POLICY",
        }}
        paths={Array.from({ length: 100 }, (_, i) => ({
          path_id: `PATH-${i}`,
          person_id: `P-${i}`,
        }))}
        steps={Array.from({ length: 100 }, (_, i) => ({
          edge_source_id: `EDGE-${i}`,
        }))}
        pathTotal={101}
        stepTotal={101}
      />,
    );
    expect(screen.getByText(/Policy country: AE/)).toBeVisible();
    fireEvent.click(
      screen.getByText("Ownership calculation paths · 101 records"),
    );
    fireEvent.click(
      screen.getByText("Ownership source edge steps · 101 records"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Next ownership paths" }),
    );
    expect(screen.getByText("PERSON-LAST")).toBeVisible();
    expect(screen.getByText("EDGE-0")).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Next ownership steps" }),
    );
    expect(screen.getByText("SOURCE-PAGE-9")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next ownership steps" }),
    ).toBeDisabled();
  });
  it("retains exact fractions and explicit unknown person identities on graph gaps", () => {
    render(
      <OwnershipPathEvidence
        prefix="/audit"
        selected="result"
        scope={{ country: "IN" }}
        paths={[
          {
            path_id: "GAP",
            kind: "graph-gap",
            economic_fraction: null,
            gap_reason: "CORPORATE_OWNER_EVIDENCE_MISSING",
            company_owner_chain: ["A, one", "B"],
            source_graph_complete: false,
          },
        ]}
        steps={[]}
        pathTotal={1}
        stepTotal={0}
      />,
    );
    fireEvent.click(
      screen.getByText("Ownership calculation paths · 1 records"),
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("CORPORATE_OWNER_EVIDENCE_MISSING")).toBeVisible();
    expect(screen.getByText('["A, one","B"]')).toBeVisible();
    expect(screen.getByText("false")).toBeVisible();
  });
});

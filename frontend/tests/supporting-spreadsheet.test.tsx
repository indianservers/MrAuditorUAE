import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AccountingIntelligence } from "@/features/accounting-intelligence";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: () => ({ tenant: "tenant" }),
}));
vi.mock("@xyflow/react", () => ({
  ReactFlow: () => null,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));
vi.mock("@/features/shared", () => ({
  PageHeader: () => null,
  LineageDetail: () => null,
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string, enabled = true) => ({
    data: !enabled
      ? undefined
      : path.endsWith("inputs")
        ? {
            snapshots: [],
            samples: [],
            evidence: [
              {
                id: "xlsx-original",
                label: "Synthetic schedule.xlsx",
                scan_status: "CLEAN",
              },
            ],
          }
        : path.endsWith("capabilities")
          ? { lead_sections: [] }
          : { items: [] },
    error: null,
  }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
  useCan: () => true,
}));

beforeEach(() => {
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
});
it("submits an explicit XLSX worksheet with the supporting-table conventions", async () => {
  render(<AccountingIntelligence eid="engagement" area="source-table" />);
  fireEvent.change(screen.getByLabelText("Evidence version"), {
    target: { value: "xlsx-original" },
  });
  fireEvent.change(screen.getByLabelText(/Worksheet name/), {
    target: { value: "Selected schedule" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Queue supporting tables" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body).toMatchObject({
    operation: "source-table",
    payload: {
      evidence_version_id: "xlsx-original",
      worksheet: "Selected schedule",
      table_kind: "bank",
      decimal_separator: ".",
      date_format: "iso",
    },
  });
});

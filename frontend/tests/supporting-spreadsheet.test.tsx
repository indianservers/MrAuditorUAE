import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AccountingIntelligence } from "@/features/accounting-intelligence";
import { validPDFDraft } from "./pdf-grid-fixtures";

const state = vi.hoisted(() => ({ mutate: vi.fn(), result: null as unknown }));
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
      : path.includes("/events/result")
        ? state.result
        : path.endsWith("inputs")
          ? {
              snapshots: [],
              samples: [],
              evidence: [
                {
                  id: "pdf-original",
                  label: "Synthetic statement.pdf",
                  scan_status: "CLEAN",
                },
                {
                  id: "xlsx-original",
                  label: "Synthetic schedule.xlsx",
                  scan_status: "CLEAN",
                },
              ],
            }
          : path.endsWith("capabilities")
            ? { lead_sections: [] }
            : {
                items: state.result
                  ? [
                      {
                        id: "result",
                        kind: "source-table",
                        label: "Prepared PDF table",
                        version: 1,
                        freshness: "CURRENT",
                      },
                    ]
                  : [],
              },
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
  state.result = null;
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
});
it("shows supporting-table amounts before expanded PDF provenance", () => {
  state.result = {
    id: "result",
    kind: "source-table",
    version: 1,
    freshness: "CURRENT",
    body: {
      table_kind: "bank",
      rows: [
        {
          id: "row-1",
          reference: "REF-1",
          date: "2026-06-30",
          account_code: "BANK-1",
          currency: "AED",
          amount: "100.25",
          source_page: 1,
          source_pdf_cells: { credit: "100.25" },
        },
      ],
    },
  };
  render(<AccountingIntelligence eid="engagement" area="source-table" />);
  fireEvent.change(screen.getByLabelText("Result version"), {
    target: { value: "result" },
  });
  expect(screen.getByRole("columnheader", { name: "amount" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "100.25" })).toBeVisible();
  expect(
    screen.queryByRole("columnheader", { name: "source_pdf_cells" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByLabelText("Show all supporting-table provenance"),
  );
  expect(
    screen.getByRole("columnheader", { name: "source_pdf_cells" }),
  ).toBeVisible();
});
it("queues PDF geometry with header scope and clears worksheet-only configuration", async () => {
  render(<AccountingIntelligence eid="engagement" area="source-table" />);
  fireEvent.change(screen.getByLabelText("Evidence version"), {
    target: { value: "pdf-original" },
  });
  fireEvent.change(screen.getByLabelText(/Worksheet name/), {
    target: { value: "Not for PDF" },
  });
  fireEvent.click(screen.getByLabelText("Map a PDF bank text grid"));
  const draft = validPDFDraft();
  const change = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  change("PDF account header", draft.account);
  change("PDF statement currency", draft.currency);
  change("PDF amount convention", draft.amount_basis);
  for (const [field, bounds] of Object.entries(draft.columns)) {
    if (!bounds.left) continue;
    change(`PDF ${field} column left (%)`, bounds.left);
    change(`PDF ${field} column right (%)`, bounds.right);
  }
  for (const field of ["top", "row_height", "row_count"] as const)
    change(`PDF grid 1 ${field.replaceAll("_", " ")}`, draft.pages[0][field]);
  for (const header of ["account_header", "currency_header"] as const)
    for (const field of ["left", "right", "top", "bottom"] as const)
      change(
        `PDF grid 1 ${header.replaceAll("_", " ")} ${field} (%)`,
        draft.pages[0][header][field],
      );
  change("PDF scope and excluded-column assessment", draft.scope_assessment);
  fireEvent.click(
    screen.getByRole("button", { name: "Queue supporting tables" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  const payload = state.mutate.mock.calls[0][0].body.payload;
  expect(payload).not.toHaveProperty("worksheet");
  expect(payload.pdf_layout).toMatchObject({
    account: "BANK-1",
    amount_basis: "credit-positive",
    columns: { credit: { left: 54, right: 69 } },
  });
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
it("keeps selected VAT coverage visible in workpaper actions and does not mix exclusion paging with result paging", () => {
  state.result = {
    id: "result",
    kind: "country-workflow",
    version: 1,
    freshness: "CURRENT",
    collection_totals: { rows: 2, excluded_box_rows: 101 },
    body: {
      review_status: "REVIEWED",
      workflow: "uae-vat-return",
      box_comparison_scope: {
        mode: "SELECTED_REQUIRED_BOXES",
        required_boxes: ["6", "7"],
        assessment: "Only import boxes are assessed",
      },
      rows: [
        { id: "six", box: "6", state: "MATCHED" },
        { id: "seven", box: "7", state: "MATCHED" },
      ],
    },
  };
  render(<AccountingIntelligence eid="engagement" area="lead" />);
  fireEvent.change(screen.getByLabelText("Result version"), {
    target: { value: "result" },
  });
  expect(
    screen.getByText(/Whole-return completeness is not determined/),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Next 100" })).toBeDisabled();
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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
const mock = vi.hoisted(() => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  useAPI: vi.fn(),
}));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ ...mock, isPending: false, error: null }),
  useAPI: mock.useAPI,
  useDebounced: (v: string) => v,
}));
vi.mock("@/components/grids/financial-data-grid", () => ({
  FinancialDataGrid: () => <div>Grid</div>,
  column: () => ({}),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
import { AuditEditor, AuditStudio } from "@/features/audit-studio";
import { ClientPortal } from "@/features/audit-administration";
beforeEach(() => {
  mock.mutate.mockReset();
  mock.mutateAsync.mockReset();
  mock.useAPI.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
  });
});
describe("structured audit editor", () => {
  it("rescans only the latest quarantined original and preserves its version ID", () => {
    mock.useAPI.mockReturnValue({
      data: {
        items: [
          {
            id: "latest",
            number: 2,
            filename: "invoice.pdf",
            scan_status: "QUARANTINED",
          },
          {
            id: "older",
            number: 1,
            filename: "invoice.pdf",
            scan_status: "QUARANTINED",
          },
        ],
      },
    });
    render(
      <AuditEditor
        base="engagements/E/audit"
        area="evidence"
        schema={{ properties: {} }}
        onSaved={() => {}}
        record={{
          id: "R",
          reference: "EV-1",
          title: "Invoice",
          status: "DRAFT",
          version: 2,
          kind: "evidence",
          body: {},
        }}
      />,
    );
    const buttons = screen.getAllByRole("button", {
      name: "Rescan retained original",
    });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(mock.mutate).toHaveBeenCalledWith({
      path: "engagements/E/audit/evidence-files/R/latest/rescan",
      body: {},
    });
  });
  it.each(["APPROVED", "LOCKED", "REVIEW_REQUIRED"])(
    "does not rescan a %s record",
    (status) => {
      mock.useAPI.mockReturnValue({
        data: {
          items: [
            {
              id: "latest",
              number: 1,
              filename: "invoice.pdf",
              scan_status: "QUARANTINED",
            },
          ],
        },
      });
      render(
        <AuditEditor
          base="engagements/E/audit"
          area="evidence"
          schema={{ properties: {} }}
          onSaved={() => {}}
          record={{
            id: "R",
            reference: "EV-1",
            title: "Invoice",
            status,
            version: 2,
            kind: "evidence",
            body: {},
          }}
        />,
      );
      expect(
        screen.queryByRole("button", { name: "Rescan retained original" }),
      ).not.toBeInTheDocument();
    },
  );
  it("saves structured sections and preserves source references", async () => {
    mock.mutateAsync.mockResolvedValue({ reference: "WP-01" });
    render(
      <AuditEditor
        base="engagements/E/audit"
        area="working-papers"
        record={null}
        onSaved={() => {}}
        schema={{
          properties: {
            sections: { type: "array" },
            sources: { type: "array" },
          },
          required: ["sections"],
        }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Reference"), {
      target: { value: "WP-01" },
    });
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Cash test" },
    });
    fireEvent.change(screen.getByLabelText("Section 1 text"), {
      target: { value: "Actual work performed" },
    });
    fireEvent.change(screen.getByLabelText("sources"), {
      target: { value: '[{"kind":"record","id":"source-id"}]' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    await waitFor(() => expect(mock.mutateAsync).toHaveBeenCalled());
    const body = mock.mutateAsync.mock.calls[0][0].body.body;
    expect(body.sections[0].text).toBe("Actual work performed");
    expect(body.sources[0].id).toBe("source-id");
  });
  it("rejects malformed source JSON before sending a request", async () => {
    render(
      <AuditEditor
        base="audit"
        area="risks"
        record={null}
        onSaved={() => {}}
        schema={{ properties: { sources: { type: "array" } } }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Reference"), {
      target: { value: "R-1" },
    });
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Risk" },
    });
    fireEvent.change(screen.getByLabelText("sources"), {
      target: { value: "[bad json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(mock.mutateAsync).not.toHaveBeenCalled();
  });
  it("shows backend permission denial without an editor", () => {
    mock.useAPI.mockReturnValue({
      error: new Error("Engagement permission denied"),
    });
    render(<AuditStudio id="restricted" area="risks" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Engagement permission denied",
    );
    expect(screen.queryByText("Save version")).not.toBeInTheDocument();
  });
  it("client portal exposes only the request workspace", () => {
    mock.useAPI.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      error: null,
    });
    render(<ClientPortal />);
    expect(
      screen.getByRole("heading", { name: "Document Request Portal" }),
    ).toBeVisible();
    expect(
      screen.queryByText("Risk & Assertions Matrix"),
    ).not.toBeInTheDocument();
  });
});

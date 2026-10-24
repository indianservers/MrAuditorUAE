import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  result: null as unknown,
  country: "AE",
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAPI: (path: string) => ({
    data: path.endsWith("country-workflows")
      ? {
          country: state.country,
          source_formats: [
            {
              id: "india-epfo-ecr",
              label: "India EPFO monthly ECR text",
              available: state.country === "IN",
              table_type: "obligations",
            },
            {
              id: "canonical-csv",
              label: "Controlled canonical CSV",
              available: true,
              table_type: null,
            },
            {
              id: "india-inv01-json",
              label: "India INV-01 JSON",
              available: state.country === "IN",
              table_type: "tax-documents",
            },
          ],
          check_templates: { controls: ["access-review"] },
          scenarios: [
            { id: "RW-001", title: "Bank receipt", workflow: "bank-brs" },
          ],
          items: [
            {
              id: "bank-brs",
              title: "Bank reconciliation",
              available: true,
              roles: { books: "transactions", statement: "transactions" },
            },
            {
              id: "india-gst",
              title: "India GST",
              available: false,
              roles: { books: "tax-documents", return: "tax-documents" },
            },
          ],
          source_contracts: {
            obligations: {
              id: { required: true, type: "str" },
              amount: { required: true, type: "Decimal" },
            },
            "tax-documents": {
              id: { required: true, type: "str" },
              tax: { required: true, type: "Decimal" },
            },
            transactions: {
              id: { required: true, type: "str" },
              amount: { required: true, type: "Decimal" },
            },
          },
        }
      : path.endsWith("inputs")
        ? {
            snapshots: [{ id: "snapshot", label: "Committed GL snapshot" }],
            evidence: [
              { id: "clean", label: "Clean statement", scan_status: "CLEAN" },
              {
                id: "quarantine",
                label: "Pending scan",
                scan_status: "QUARANTINED",
              },
            ],
          }
        : path.includes("/events/result")
          ? state.result
          : path.includes("/events?")
            ? {
                items: [
                  {
                    id: "books",
                    kind: "workflow-source",
                    table_type: "transactions",
                    label: "Books",
                    freshness: "CURRENT",
                    version: 1,
                    review_status: "REVIEWED",
                  },
                  {
                    id: "statement",
                    kind: "workflow-source",
                    table_type: "transactions",
                    label: "Bank",
                    freshness: "CURRENT",
                    version: 1,
                    review_status: "REVIEWED",
                  },
                  {
                    id: "wrong",
                    kind: "workflow-source",
                    table_type: "tax-documents",
                    label: "Wrong source type",
                    freshness: "CURRENT",
                    version: 1,
                    review_status: "REVIEWED",
                  },
                  {
                    id: "result",
                    kind: "country-workflow",
                    label: "Saved reconciliation",
                    freshness: "CURRENT",
                    version: 1,
                    review_status: "UNVERIFIED",
                  },
                ],
              }
            : path.includes("/accounts?")
              ? { items: [{ id: "cash", code: "100", name: "Bank GL" }] }
              : { items: [] },
    error: null,
  }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (s: { tenant: string }) => unknown) =>
    select({ tenant: "tenant" }),
}));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

beforeEach(() => {
  state.country = "AE";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
  state.result = null;
});
describe("country workflows", () => {
  it("prepares ECR with declared establishment, wage month, members and amounts", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source file format"), {
      target: { value: "india-epfo-ecr" },
    });
    for (const [label, value] of [
      ["Schedule title", "ECR June review"],
      ["EPFO establishment registration", "SYNTHETIC-EPFO-001"],
      ["ECR wage month", "2026-06"],
      ["Independent ECR member count", "2"],
      ["Clean retained evidence", "clean"],
      ["Expected data rows", "7"],
      ["Independent totals by currency", "INR=6100"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      file_format: "india-epfo-ecr",
      table_type: "obligations",
      employer_registration: "SYNTHETIC-EPFO-001",
      obligation_period: "2026-06",
      expected_members: 2,
      expected_rows: 7,
      control_totals: { INR: "6100" },
    });
  });
  it("queues an India invoice with explicit GSTIN, direction, month and component controls", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source file format"), {
      target: { value: "india-inv01-json" },
    });
    for (const [label, value] of [
      ["Schedule title", "India native invoices"],
      ["Entity GSTIN", "27ABCDE5678G1Z8"],
      ["Invoice direction", "purchase"],
      ["Reporting month", "2026-06"],
      ["Clean retained evidence", "clean"],
      ["Expected data rows", "5"],
      ["Independent totals by currency", "INR=18"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    expect(screen.getByLabelText("Source table type")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      file_format: "india-inv01-json",
      table_type: "tax-documents",
      gst_registration: "27ABCDE5678G1Z8",
      gst_direction: "purchase",
      gst_period: "2026-06",
      expected_rows: 5,
      control_totals: { INR: "18" },
    });
  });
  it("queues a credit-normal payable GL control without a movement date", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source origin"), {
      target: { value: "ledger" },
    });
    fireEvent.change(screen.getByLabelText("Ledger source type"), {
      target: { value: "balance-controls" },
    });
    fireEvent.change(screen.getByLabelText("Subledger side"), {
      target: { value: "payable" },
    });
    for (const [label, value] of [
      ["Schedule title", "Payable control"],
      ["Committed ledger snapshot", "snapshot"],
      ["Bank ledger account", "cash"],
      ["Bank account identifier", "AP"],
      ["Ledger through date", "2026-12-31"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    expect(
      screen.queryByLabelText("Ledger from date (optional)"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      source_kind: "balance-controls",
      balance_side: "payable",
      bank_account: "AP",
    });
    expect(state.mutate.mock.calls[0][0].body.payload).not.toHaveProperty(
      "from_date",
    );
  });
  it("queues a committed account selection without asking for an exported copy", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source origin"), {
      target: { value: "ledger" },
    });
    for (const [label, value] of [
      ["Schedule title", "Committed bank source"],
      ["Committed ledger snapshot", "snapshot"],
      ["Bank ledger account", "cash"],
      ["Bank account identifier", "BANK-1"],
      ["Ledger through date", "2026-06-30"],
      ["Ledger from date (optional)", "2026-06-01"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body).toEqual({
      operation: "workflow-ledger",
      payload: {
        snapshot_id: "snapshot",
        account_ids: ["cash"],
        bank_account: "BANK-1",
        currency: "AED",
        label: "Committed bank source",
        as_of: "2026-06-30",
        from_date: "2026-06-01",
      },
    });
  });
  it("filters unavailable country workflows and wrong source types", () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    expect(
      screen.queryByRole("option", { name: "India GST" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("books source")).not.toHaveTextContent(
      "Wrong source type",
    );
  });
  it("queues the selected independent bank sources and exact balances", async () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    for (const [label, value] of [
      ["Schedule title", "June bank reconciliation"],
      ["Reconciliation date", "2026-06-30"],
      ["books source", "books"],
      ["statement source", "statement"],
      ["Bank account identifier", "BANK-1"],
      ["book opening", "0"],
      ["book closing", "100"],
      ["statement opening", "0"],
      ["statement closing", "100"],
      ["Scope and source rationale", "Independent monthly source populations"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    const request = state.mutate.mock.calls[0][0];
    expect(request.body.operation).toBe("country-workflow");
    expect(request.body.payload.source_ids).toEqual({
      books: "books",
      statement: "statement",
    });
    expect(request.body.payload.book_closing).toBe("100");
    expect(request.headers["Idempotency-Key"]).toBeTruthy();
  });
  it("keeps quarantined evidence disabled and rejects malformed currency controls", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    expect(screen.getByRole("option", { name: /Pending scan/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Independent totals by currency"), {
      target: { value: "AED=10,AED=20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "unique currency totals",
    );
    expect(state.mutate).not.toHaveBeenCalled();
  });
  it("shows missing evidence as a blocker and disables approval", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Missing licence evidence",
        review_status: "UNVERIFIED",
        blocked: true,
        exception_count: 1,
        population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
        rows: [{ id: "check-1", state: "MISSING" }],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Approval blocked");
    expect(
      screen.getByRole("button", { name: "Independent approval" }),
    ).toBeDisabled();
  });
});

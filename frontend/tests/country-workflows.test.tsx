import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  result: null as unknown,
  country: "AE",
  jobs: [] as {
    id: string;
    operation: string;
    status: string;
    result_id: string;
  }[],
}));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => true,
  useAPI: (path: string) => ({
    data: path.endsWith("country-workflows")
      ? {
          country: state.country,
          source_formats: [
            {
              id: "india-gstr2b-json",
              label: "India GSTR-2B document JSON",
              available: state.country === "IN",
              table_type: "tax-documents",
            },
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
              id: "india-withholding-liability",
              title: "India withholding liability",
              available: state.country === "IN",
              roles: {
                expected: "withholding-records",
                withheld: "withholding-records",
                reported: "withholding-records",
                deposited: "withholding-records",
              },
            },
            {
              id: "india-withholding-credit",
              title: "India withholding credit",
              available: state.country === "IN",
              roles: {
                books: "withholding-records",
                statement: "withholding-records",
                certificate: "withholding-records",
              },
            },
            {
              id: "credit-note-applications",
              title: "Credit-note applications",
              available: true,
              roles: {
                items: "audit-open-items",
                controls: "balance-controls",
                applications: "credit-applications",
              },
            },
            {
              id: "payroll-settlement",
              title: "Payroll settlement",
              available: true,
              roles: {
                payroll: "obligations",
                channel: "obligations",
                bank: "obligations",
              },
            },
            {
              id: "india-payroll-rules",
              title: "India payroll contribution rules review",
              available: state.country === "IN",
              roles: {
                bases: "payroll-bases",
                rules: "payroll-rules",
                reported: "obligations",
              },
            },
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
            "withholding-records": { id: { required: true, type: "str" } },
            "benefit-rules": { id: { required: true, type: "str" } },
            "payroll-rules": { id: { required: true, type: "str" } },
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
          : path.endsWith("/jobs")
            ? { items: state.jobs }
            : path.includes("/events?")
              ? {
                  items: [
                    {
                      id: "supporting-items",
                      kind: "source-table",
                      table_kind: "open-items",
                      label: "Reviewed payable population",
                      evidence_version_id: "original-items",
                      version: 2,
                      freshness: "CURRENT",
                      review_status: "REVIEWED",
                    },
                    {
                      id: "supporting-bank",
                      kind: "source-table",
                      table_kind: "bank",
                      label: "Reviewed supporting statement",
                      evidence_version_id: "original-bank",
                      version: 2,
                      freshness: "CURRENT",
                      review_status: "REVIEWED",
                    },
                    {
                      id: "unreviewed-bank",
                      kind: "source-table",
                      table_kind: "bank",
                      label: "Unreviewed supporting statement",
                      evidence_version_id: "original-unreviewed",
                      version: 1,
                      freshness: "CURRENT",
                      review_status: "UNVERIFIED",
                    },
                    ...[
                      {
                        id: "wps",
                        table_type: "obligations",
                        label: "WPS instructions",
                        native_format: "uae-wps-sif",
                        review_status: "REVIEWED",
                      },
                      {
                        id: "ecr",
                        table_type: "obligations",
                        label: "Native ECR return",
                        native_format: "india-epfo-ecr",
                        review_status: "REVIEWED",
                      },
                      {
                        id: "bases",
                        table_type: "payroll-bases",
                        label: "Payroll component bases",
                        review_status: "REVIEWED",
                      },
                      {
                        id: "rules",
                        table_type: "payroll-rules",
                        label: "Reviewed contribution rules",
                        review_status: "REVIEWED",
                      },
                      {
                        id: "unreviewed-rules",
                        table_type: "payroll-rules",
                        label: "Unreviewed contribution rules",
                        review_status: "UNVERIFIED",
                      },
                      {
                        id: "reported",
                        table_type: "obligations",
                        label: "Reported ECR",
                        review_status: "UNVERIFIED",
                      },
                    ].map((source) => ({
                      ...source,
                      kind: "workflow-source",
                      freshness: "CURRENT",
                      version: 1,
                    })),
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
  state.jobs = [];
  state.country = "AE";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
  state.result = null;
});
describe("country workflows", () => {
  it("binds a selected retained assessment document when preparing withholding records", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source table type"), {
      target: { value: "withholding-records" },
    });
    fireEvent.change(
      screen.getByLabelText(
        "Withholding assessment document (optional shared document)",
      ),
      { target: { value: "clean" } },
    );
    fireEvent.change(screen.getByLabelText("Clean retained evidence"), {
      target: { value: "clean" },
    });
    fireEvent.change(screen.getByLabelText("Schedule title"), {
      target: { value: "Synthetic assessed withholding source" },
    });
    fireEvent.change(screen.getByLabelText("Independent totals by currency"), {
      target: { value: "INR=100" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      table_type: "withholding-records",
      rule_document_version_id: "clean",
      control_totals: { INR: "100" },
    });
  });
  it("shows unsupported assessment scope even when the numerical comparison matches", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Unsupported certificate scope",
        workflow: "india-withholding-credit",
        blocked: true,
        rows: [
          {
            id: "withholding-1",
            state: "ASSESSMENT_NOT_SUPPORTED",
            comparison_state: "MATCHED",
            assessment_issues: ["CERTIFICATE_SHARED_AMOUNT_LIMIT_EXCEEDED"],
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.getByText("certificate shared amount limit exceeded"),
    ).toBeVisible();
    expect(screen.getByRole("cell", { name: "MATCHED" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Independent approval" }),
    ).toBeDisabled();
  });
  it("renders withholding amounts as labelled values with readable differences", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Withholding result",
        workflow: "india-withholding-liability",
        review_status: "UNVERIFIED",
        rows: [
          {
            id: "withholding-1",
            legal_role: "deductor",
            amounts: {
              expected: "100",
              reported: "90",
              withheld: "100",
              deposited: "100",
            },
            differences_from_expected: {
              reported: "-10",
              withheld: "0",
              deposited: "0",
            },
            state: "VARIANCE",
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(screen.getByText("expected: 100")).toBeVisible();
    expect(screen.getByText("reported: 90")).toBeVisible();
    expect(screen.getByText("reported: -10")).toBeVisible();
  });
  it("keeps liability and credit role choices separate and requires explicit assessment", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "india-withholding-liability" },
    });
    const role = screen.getByLabelText("Organization legal withholding role");
    expect(role).toHaveTextContent("TDS deductor");
    expect(role).not.toHaveTextContent("TDS deductee");
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    expect(
      await screen.findByText(
        "Select the organization’s legal withholding role before comparing sources.",
      ),
    ).toBeVisible();
    expect(state.mutate).not.toHaveBeenCalled();
    fireEvent.change(role, { target: { value: "collector" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "india-withholding-liability",
      withholding_role: "collector",
      currency: "INR",
    });
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "india-withholding-credit" },
    });
    expect(
      screen.getByLabelText("Organization legal withholding role"),
    ).toHaveValue("");
    expect(
      screen.getByLabelText("Organization legal withholding role"),
    ).toHaveTextContent("TCS collectee");
    expect(
      screen.getByLabelText("Organization legal withholding role"),
    ).not.toHaveTextContent("TCS collector");
  });
  it("keeps credit residual balances visible before expanding application provenance", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Credit application result",
        workflow: "credit-note-applications",
        review_status: "UNVERIFIED",
        rows: [
          {
            id: "item:CN1",
            kind: "open_item",
            item_id: "CN1",
            currency: "AED",
            original_balance: "-40",
            applied: "25",
            remaining_balance: "-15",
            state: "UNAPPLIED_CREDIT",
            application_ids: ["A1"],
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.getByRole("columnheader", { name: "remaining balance" }),
    ).toBeVisible();
    expect(screen.getByRole("cell", { name: "-15" })).toBeVisible();
    expect(
      screen.queryByRole("columnheader", { name: "application ids" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByLabelText("Show source provenance and all columns"),
    );
    expect(
      screen.getByRole("columnheader", { name: "application ids" }),
    ).toBeVisible();
  });
  it("requires a pre-application balance confirmation for credit applications", async () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "credit-note-applications" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    expect(
      await screen.findByText(
        "Confirm that balances are before the listed credit applications.",
      ),
    ).toBeVisible();
    expect(state.mutate).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByLabelText(
        "Balances are before the listed credit applications; these applications have not already been deducted.",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "credit-note-applications",
      allocation_basis: "pre_application_balances",
    });
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "bank-brs" },
    });
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "credit-note-applications" },
    });
    expect(
      screen.getByRole("checkbox", { name: /Balances are before/ }),
    ).not.toBeChecked();
  });
  it("shows open-item balances first while retaining every provenance column", () => {
    state.result = {
      id: "result",
      kind: "workflow-source",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Reviewed payable schedule",
        table_type: "audit-open-items",
        review_status: "UNVERIFIED",
        population_completeness:
          "REVIEWED_SUPPORTING_TABLE_WITH_INDEPENDENT_CONTROLS",
        rows: [
          {
            id: "row-2",
            reference: "INV-1",
            side: "payable",
            currency: "AED",
            amount: "100",
            supporting_source_worksheet: "Selected",
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(screen.getByRole("cell", { name: "INV-1" })).toBeVisible();
    expect(
      screen.queryByRole("columnheader", {
        name: "supporting source worksheet",
      }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByLabelText("Show source provenance and all columns"),
    );
    expect(
      screen.getByRole("columnheader", { name: "supporting source worksheet" }),
    ).toBeVisible();
  });
  it("keeps recent job results accessible without expanding the entire history", () => {
    state.jobs = Array.from({ length: 7 }, (_, i) => ({
      id: `job-${i}`,
      operation: "workflow-source",
      status: "completed",
      result_id: `result-${i}`,
    }));
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    expect(
      screen.getAllByRole("button", { name: /^Open result$/ }),
    ).toHaveLength(5);
    fireEvent.click(
      screen.getByRole("button", { name: "Show full recent job history" }),
    );
    expect(
      screen.getAllByRole("button", { name: /^Open result$/ }),
    ).toHaveLength(7);
    fireEvent.click(
      screen.getByRole("button", { name: "Show latest five jobs" }),
    );
    expect(
      screen.getAllByRole("button", { name: /^Open result$/ }),
    ).toHaveLength(5);
  });
  it("queues reviewed open items with explicit payable sign and reporting-date scope", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source origin"), {
      target: { value: "supporting-items" },
    });
    expect(
      screen.getByLabelText("Reviewed supporting open-item table"),
    ).not.toHaveTextContent("Reviewed supporting statement");
    for (const [label, value] of [
      ["Reviewed supporting open-item table", "supporting-items"],
      ["Control account identifier", "AP-1"],
      [
        "Supporting open-item scope assessment",
        "Reviewed supplier population and credit-negative source basis",
      ],
      ["Open-item subledger side", "payable"],
      ["Open-item balance date", "2026-06-30"],
      ["Open-item source sign", "reverse-sign"],
      ["Expected data rows", "2"],
      ["Independent totals by currency", "AED=80"],
      ["Schedule title", "Reviewed payables"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      table_type: "audit-open-items",
      supporting_table_id: "supporting-items",
      evidence_version_id: "original-items",
      supporting_side: "payable",
      supporting_balance_date: "2026-06-30",
      supporting_amount_sign: "reverse-sign",
      control_totals: { AED: "80" },
    });
  });
  it("queues reviewed bank-table reuse with its original evidence and independent controls", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source origin"), {
      target: { value: "supporting" },
    });
    expect(
      screen.getByLabelText("Reviewed supporting bank table"),
    ).not.toHaveTextContent("Unreviewed supporting statement");
    for (const [label, value] of [
      ["Reviewed supporting bank table", "supporting-bank"],
      ["Bank account identifier", "BANK-1"],
      [
        "Supporting bank account scope assessment",
        "Reviewed original bank population and account identity evidence",
      ],
      ["Expected data rows", "2"],
      ["Independent totals by currency", "AED=95.25"],
      ["Schedule title", "Reused bank population"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      supporting_table_id: "supporting-bank",
      evidence_version_id: "original-bank",
      account_identifier: "BANK-1",
      expected_rows: 2,
      control_totals: { AED: "95.25" },
      table_type: "transactions",
      file_format: "canonical-csv",
    });
  });
  it("queues the explicitly selected bank debit/credit convention", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.click(screen.getByLabelText("Map original CSV columns"));
    for (const [label, value] of [
      ["Transaction amount columns", "credit-positive"],
      ["Original debit column", "Withdrawal"],
      ["Original credit column", "Deposit"],
      ["Clean retained evidence", "clean"],
      ["Schedule title", "Mapped bank movements"],
      [
        "Column mapping and exclusion assessment",
        "Reviewed bank credit means inflow in this export",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    expect(
      screen.queryByLabelText("CSV column for amount"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      amount_derivation: "credit-positive",
      debit_column: "Withdrawal",
      credit_column: "Deposit",
    });
  });
  it("submits explicit original CSV headings and exclusions without changing values", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.click(screen.getByLabelText("Map original CSV columns"));
    for (const [label, value] of [
      ["CSV column for id", "Original row"],
      ["CSV column for amount", "Signed amount"],
      ["CSV separator", ";"],
      ["Excluded CSV columns, one exact heading per line", "Memo"],
      [
        "Column mapping and exclusion assessment",
        "Reviewed export columns and explicit memo exclusion",
      ],
      ["Clean retained evidence", "clean"],
      ["Schedule title", "Original bank export"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      column_mapping: { id: "Original row", amount: "Signed amount" },
      ignored_columns: ["Memo"],
      delimiter: ";",
    });
  });
  it("queues GSTR-2B with the recipient, return month and separate document control", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source file format"), {
      target: { value: "india-gstr2b-json" },
    });
    for (const [label, value] of [
      ["Schedule title", "June GSTR-2B"],
      ["Recipient GSTIN", "27ABCDE5678G1Z8"],
      ["GSTR-2B return month", "2026-06"],
      ["Independent GSTR-2B document count", "1"],
      ["Clean retained evidence", "clean"],
      ["Independent totals by currency", "INR=18"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(screen.getByLabelText("Expected data rows")).toHaveValue(4);
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      file_format: "india-gstr2b-json",
      gst_registration: "27ABCDE5678G1Z8",
      gst_period: "2026-06",
      expected_documents: 1,
      expected_rows: 4,
      control_totals: { INR: "18" },
    });
  });
  it("shows payroll amounts first and reveals rule references on request", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        workflow: "india-payroll-rules",
        title: "Partial payroll expectation",
        review_status: "UNVERIFIED",
        population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
        expected_total: "1800",
        reported_total: "1700",
        expected_total_complete: false,
        rows: [
          {
            id: "PF-1",
            subject: "SYNTHETIC-MEMBER",
            component: "PF:EMPLOYEE",
            currency: "INR",
            expected_amount: "1800",
            reported_amount: "1700",
            state: "CONTRIBUTION_DIFFERENCE",
            rule_document_sha256: "f".repeat(64),
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(screen.getByText(/Partial expected total: INR 1800/)).toBeVisible();
    expect(
      screen.queryByRole("columnheader", { name: "rule document sha256" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByLabelText("Show rule provenance and source references"),
    );
    expect(
      screen.getByRole("columnheader", { name: "rule document sha256" }),
    ).toBeVisible();
  });
  it.each([
    ["payroll-rules", "Payroll"],
    ["benefit-rules", "Benefit"],
  ])(
    "binds %s imports to a selected clean retained document",
    async (table, name) => {
      state.country = "IN";
      render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
      fireEvent.change(screen.getByLabelText("Source table type"), {
        target: { value: table },
      });
      fireEvent.change(
        screen.getByLabelText(
          `${name} rule source document (optional shared document)`,
        ),
        { target: { value: "clean" } },
      );
      fireEvent.change(screen.getByLabelText("Clean retained evidence"), {
        target: { value: "clean" },
      });
      fireEvent.change(screen.getByLabelText("Schedule title"), {
        target: { value: "Source-bound rules" },
      });
      fireEvent.click(
        screen.getByRole("button", { name: "Queue calculation" }),
      );
      await waitFor(() => expect(state.mutate).toHaveBeenCalled());
      expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
        table_type: table,
        rule_document_version_id: "clean",
      });
    },
  );
  it("queues INR payroll calculations using only independently reviewed rule sources", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "india-payroll-rules" },
    });
    expect(screen.getByLabelText("rules source")).not.toHaveTextContent(
      "Unreviewed contribution rules",
    );
    for (const [label, value] of [
      ["Schedule title", "PF June calculation"],
      ["Reconciliation date", "2026-06-30"],
      ["bases source", "bases"],
      ["rules source", "rules"],
      ["reported source", "reported"],
      [
        "Scope and source rationale",
        "Sourced wage and rule assessment against reported ECR",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "india-payroll-rules",
      currency: "INR",
      source_ids: { bases: "bases", rules: "rules", reported: "reported" },
    });
  });
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
  it("offers native instructions only for the channel role, keeping independent schedules selectable", () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "payroll-settlement" },
    });
    for (const role of ["payroll", "bank"]) {
      const picker = screen.getByLabelText(`${role} source`);
      expect(picker).not.toHaveTextContent("WPS instructions");
      expect(picker).not.toHaveTextContent("Native ECR return");
      expect(picker).toHaveTextContent("Reported ECR");
    }
    const channel = screen.getByLabelText("channel source");
    expect(channel).toHaveTextContent("WPS instructions");
    expect(channel).toHaveTextContent("Native ECR return");
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

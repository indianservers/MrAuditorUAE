import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CountryWorkflows } from "@/features/country-workflows";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  result: null as unknown,
  excludedPage: null as unknown,
  postingPage: null as unknown,
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
    data: path.includes("excluded_offset=100")
      ? state.excludedPage
      : path.endsWith("country-workflows")
        ? {
            country: state.country,
            vat201_layouts:
              state.country === "AE"
                ? {
                    "aggregate-14": {
                      label: "Aggregate Box 1 - fourteen rows",
                      boxes: Array.from({ length: 14 }, (_, index) =>
                        String(index + 1),
                      ),
                    },
                    "emirate-20": {
                      label: "Box 1a-1g by emirate - twenty rows",
                      boxes: [..."abcdefg"]
                        .map((letter) => "1" + letter)
                        .concat(
                          Array.from({ length: 13 }, (_, index) =>
                            String(index + 2),
                          ),
                        ),
                    },
                  }
                : {},
            source_formats: [
              {
                id: "india-epfo-arrear-ecr-v2",
                label: "India EPFO arrears eight-field text",
                available: state.country === "IN",
                table_type: "obligations",
              },
              {
                id: "uae-wps-sif-evp",
                label: "UAE WPS EDR EVP SCR",
                available: state.country === "AE",
                table_type: "obligations",
              },
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
                id: "payroll-ledger-rollforward",
                title: "Payroll accounting bridge",
                available: true,
                roles: {
                  opening: "payroll-account-balances",
                  payroll: "payroll-ledger-lines",
                  posted: "payroll-ledger-lines",
                  closing: "payroll-account-balances",
                },
              },
              {
                id: "statutory-dues",
                title: "Statutory dues",
                available: true,
                roles: {
                  expected: "obligations",
                  return: "obligations",
                  payment: "obligations",
                },
              },
              {
                id: "inventory-count-bridge",
                title: "Inventory count bridge",
                available: true,
                roles: {
                  books: "stock",
                  counts: "stock",
                  movements: "stock-movements",
                },
              },
              {
                id: "obligation-bank-allocations",
                title: "Obligation bank allocations",
                available: true,
                roles: {
                  expected: "obligations",
                  reported: "obligations",
                  bank: "transactions",
                  allocations: "obligation-allocations",
                },
              },
              {
                id: "bank-subsequent-clearance",
                title: "Subsequent bank clearance",
                available: true,
                roles: {
                  outstanding: "bank-outstanding",
                  statement: "transactions",
                  allocations: "bank-clearances",
                },
              },
              {
                id: "uae-vat-return",
                title: "UAE VAT201 box comparison",
                available: state.country === "AE",
                roles: { books: "return-boxes", return: "return-boxes" },
              },
              {
                id: "uae-import-vat",
                title: "UAE import VAT review",
                available: state.country === "AE",
                roles: {
                  customs: "import-vat-lines",
                  portal: "import-vat-lines",
                  books: "import-vat-lines",
                },
              },
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
                id: "uae-pension-review",
                title: "UAE pension contribution review",
                available: state.country === "AE",
                roles: {
                  bases: "pension-bases",
                  rules: "pension-rules",
                  reported: "pension-reported",
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
              "payroll-account-balances": {
                id: { required: true, type: "str" },
                amount: { required: true, type: "Decimal" },
              },
              "payroll-ledger-lines": {
                id: { required: true, type: "str" },
                amount: { required: true, type: "Decimal" },
              },
              stock: {
                id: { required: true, type: "str" },
                quantity: { required: true, type: "Decimal" },
                lot: { required: false, type: "str" },
              },
              "stock-movements": {
                id: { required: true, type: "str" },
                quantity: { required: true, type: "Decimal" },
              },
              "fx-rates": { id: { required: true, type: "str" } },
              "import-vat-lines": {
                id: { required: true, type: "str" },
                tax: { required: true, type: "Decimal" },
              },
              "withholding-records": { id: { required: true, type: "str" } },
              "benefit-rules": { id: { required: true, type: "str" } },
              "payroll-rules": { id: { required: true, type: "str" } },
              "pension-rules": { id: { required: true, type: "str" } },
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
                {
                  id: "clean",
                  label: "Clean statement",
                  scan_status: "CLEAN",
                },
                {
                  id: "context-clean",
                  label: "Clean arrear context",
                  scan_status: "CLEAN",
                },
                {
                  id: "quarantine",
                  label: "Pending scan",
                  scan_status: "QUARANTINED",
                },
              ],
            }
          : path.includes("/events/result")
            ? path.includes("posting_offset=100")
              ? state.postingPage
              : state.result
            : path.endsWith("/jobs")
              ? { items: state.jobs }
              : path.includes("/events?")
                ? {
                    items: [
                      ...["opening", "payroll", "posted", "closing"].map(
                        (role) => ({
                          id: "ledger-" + role,
                          label: "Reviewed ledger " + role,
                          kind: "workflow-source",
                          table_type: ["opening", "closing"].includes(role)
                            ? "payroll-account-balances"
                            : "payroll-ledger-lines",
                          freshness: "CURRENT",
                          review_status: "REVIEWED",
                          version: 1,
                        }),
                      ),
                      {
                        id: "unreviewed-ledger",
                        label: "Unreviewed payroll ledger",
                        kind: "workflow-source",
                        table_type: "payroll-ledger-lines",
                        freshness: "CURRENT",
                        review_status: "UNVERIFIED",
                        version: 1,
                      },
                      ...["expected", "return", "payment"].map((role) => ({
                        id: "arrear-" + role,
                        label: "Reviewed arrear " + role,
                        kind: "workflow-source",
                        table_type: "obligations",
                        freshness: "CURRENT",
                        review_status: "REVIEWED",
                        version: 1,
                        obligation_populations: ["arrears"],
                        native_format:
                          role === "return"
                            ? "india-epfo-arrear-ecr-v2"
                            : undefined,
                        allowed_source_roles:
                          role === "return"
                            ? ["return", "reported"]
                            : undefined,
                      })),
                      {
                        id: "regular-payment",
                        label: "Regular monthly payment",
                        kind: "workflow-source",
                        table_type: "obligations",
                        freshness: "CURRENT",
                        review_status: "REVIEWED",
                        version: 1,
                        obligation_populations: ["regular"],
                      },
                      ...["books", "counts", "movements"].map((role) => ({
                        id: "inventory-" + role,
                        label: "Controlled inventory " + role,
                        kind: "workflow-source",
                        table_type:
                          role === "movements" ? "stock-movements" : "stock",
                        freshness: "CURRENT",
                        version: 1,
                        review_status: "REVIEWED",
                        inventory_controls_verified: true,
                      })),
                      {
                        id: "uncontrolled-stock",
                        label: "Uncontrolled stock",
                        kind: "workflow-source",
                        table_type: "stock",
                        freshness: "CURRENT",
                        version: 1,
                        review_status: "REVIEWED",
                        inventory_controls_verified: false,
                      },
                      ...[
                        "pension-bases",
                        "pension-rules",
                        "pension-reported",
                      ].flatMap((table_type) => [
                        {
                          id: table_type,
                          kind: "workflow-source",
                          table_type,
                          label: `Reviewed ${table_type}`,
                          freshness: "CURRENT",
                          version: 1,
                          review_status: "REVIEWED",
                        },
                        {
                          id: `unreviewed-${table_type}`,
                          kind: "workflow-source",
                          table_type,
                          label: `Unreviewed ${table_type}`,
                          freshness: "CURRENT",
                          version: 1,
                          review_status: "UNVERIFIED",
                        },
                      ]),
                      {
                        id: "vat-books",
                        kind: "workflow-source",
                        table_type: "return-boxes",
                        label: "Assessed import boxes",
                        freshness: "CURRENT",
                        version: 1,
                        review_status: "REVIEWED",
                      },
                      {
                        id: "vat-filed",
                        kind: "workflow-source",
                        table_type: "return-boxes",
                        label: "Full filed VAT201 source",
                        freshness: "CURRENT",
                        version: 1,
                        review_status: "REVIEWED",
                      },
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
                          id: "expected-dues",
                          table_type: "obligations",
                          label: "Reviewed expected dues",
                          allowed_source_roles: ["expected"],
                          review_status: "REVIEWED",
                        },
                        {
                          id: "dues-links",
                          table_type: "obligation-allocations",
                          label: "Reviewed bank allocations",
                          review_status: "REVIEWED",
                        },
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
                        id: "outstanding",
                        kind: "workflow-source",
                        table_type: "bank-outstanding",
                        label: "Outstanding cheques",
                        freshness: "CURRENT",
                        version: 1,
                        review_status: "REVIEWED",
                      },
                      {
                        id: "clearances",
                        kind: "workflow-source",
                        table_type: "bank-clearances",
                        label: "Clearance allocations",
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
  state.excludedPage = null;
  state.postingPage = null;
  state.jobs = [];
  state.country = "AE";
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "queued" });
  state.result = null;
});
describe("country workflows", () => {
  it("keeps obligation, reported and bank amounts readable without changing retained provenance", () => {
    const retained = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Allocated dues",
        workflow: "obligation-bank-allocations",
        review_status: "UNVERIFIED",
        allocation_controls: {
          expected_amount: "180",
          allocated_amount: "150",
          outstanding_expected: "30",
        },
        rows: [
          {
            id: "obligation:E1",
            kind: "obligation",
            subject: "EMP-1",
            period: "2026-06",
            component: "SALARY",
            currency: "AED",
            expected_amount: "100",
            bank_settled: "70",
            outstanding_amount: "30",
            state: "PARTIALLY_SETTLED",
            payment_allocations: [{ transaction_id: "BANK-1", amount: "70" }],
          },
          {
            id: "bank:B1",
            kind: "bank",
            reference: "PAY-001",
            currency: "AED",
            bank_amount: "-150",
            allocated: "150",
            unallocated_bank_amount: "0",
            state: "MATCHED",
          },
        ],
      },
    };
    const original = JSON.stringify(retained);
    state.result = retained;
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.getByRole("columnheader", { name: "source amount" }),
    ).toBeVisible();
    expect(screen.getByRole("cell", { name: "-150" })).toBeVisible();
    expect(
      screen.queryByRole("columnheader", { name: "payment allocations" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Obligation allocation controls" }),
    ).toHaveTextContent("outstanding expected30");
    fireEvent.click(
      screen.getByLabelText("Show source provenance and all columns"),
    );
    expect(
      screen.getByRole("columnheader", { name: "payment allocations" }),
    ).toBeVisible();
    expect(JSON.stringify(retained)).toBe(original);
  });
  it("requires explicit settlement choices and independently reviewed obligation sources", async () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "obligation-bank-allocations" },
    });
    expect(screen.getByLabelText("Bank payment sign")).toHaveValue("");
    expect(screen.getByLabelText("expected source")).not.toHaveTextContent(
      "WPS instructions",
    );
    expect(screen.getByLabelText("reported source")).toHaveTextContent(
      "WPS instructions",
    );
    expect(screen.getByLabelText("reported source")).not.toHaveTextContent(
      "Reported ECR",
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    expect(
      await screen.findByText(
        "Declare obligation months, bank account, settlement window and payment sign before allocating.",
      ),
    ).toBeVisible();
    expect(state.mutate).not.toHaveBeenCalled();
    for (const [label, value] of [
      ["First obligation month", "2026-05"],
      ["Last obligation month", "2026-06"],
      ["Bank settlement window starts", "2026-06-01"],
      ["Bank account identifier", "BANK-1"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.change(screen.getByLabelText("Bank payment sign"), {
      target: { value: "debit-negative" },
    });
    for (const [label, value] of [
      ["expected source", "expected-dues"],
      ["reported source", "wps"],
      ["bank source", "statement"],
      ["allocations source", "dues-links"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "obligation-bank-allocations",
      obligation_month_start: "2026-05",
      obligation_month_end: "2026-06",
      settlement_start: "2026-06-01",
      bank_payment_sign: "debit-negative",
      account: "BANK-1",
      source_ids: {
        expected: "expected-dues",
        reported: "wps",
        bank: "statement",
        allocations: "dues-links",
      },
    });
  });
  it("shows readable CAMT page controls and retains the complete page provenance", () => {
    state.result = {
      id: "result",
      kind: "workflow-source",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Synthetic paginated statement",
        table_type: "transactions",
        review_status: "UNVERIFIED",
        rows: [],
        native_metadata: {
          page_count: 2,
          page_controls: [
            {
              page_number: 1,
              source_statement_position: 1,
              electronic_sequence: "27",
              currency: "AED",
              opening: "0.00",
              closing: "100.00",
              entry_count: 1,
              entry_total: "100.00",
              last_page: false,
              closing_subtype: "INTM",
            },
            {
              page_number: 2,
              source_statement_position: 2,
              electronic_sequence: "27",
              currency: "AED",
              opening: "100.00",
              closing: "95.00",
              entry_count: 1,
              entry_total: "-5.00",
              last_page: true,
            },
          ],
        },
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    fireEvent.click(
      screen.getByText("Original source controls and calculation basis"),
    );
    expect(
      screen.getByRole("table", { name: "CAMT statement page controls" }),
    ).toHaveTextContent("95.00");
    expect(
      screen.getByRole("table", { name: "CAMT statement page controls" }),
    ).toHaveTextContent("-5.00");
    fireEvent.click(
      screen.getByText("All retained statement page control fields"),
    );
    expect(screen.getByText(/"closing_subtype": "INTM"/)).toBeVisible();
  });
  it("prepares only explicitly selected reviewed BRS book exceptions with independent controls", async () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        title: "Reviewed BRS",
        workflow: "bank-brs",
        review_status: "REVIEWED",
        blocked: false,
        rows: [
          {
            id: "books:B1",
            side: "books",
            reference: "SYN-CHEQUE",
            currency: "AED",
            amount: "-100",
            state: "EXCEPTION",
          },
          {
            id: "statement:S1",
            side: "statement",
            reference: "SYN-FEE",
            currency: "AED",
            amount: "-5",
            state: "EXCEPTION",
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    fireEvent.click(
      screen.getByText(
        "Prepare selected outstanding items for subsequent clearance",
      ),
    );
    const prepare = screen.getByRole("button", {
      name: "Prepare outstanding source",
    });
    expect(prepare).toBeDisabled();
    expect(
      screen.queryByRole("checkbox", { name: /statement:S1/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /books:B1/ }));
    for (const [label, value] of [
      ["Outstanding source title", "Selected outstanding cheque"],
      ["Independent outstanding row count", "1"],
      ["Independent outstanding signed total", "-100"],
      [
        "Outstanding population assessment",
        "Original BRS cheque selected for independently evidenced subsequent clearing",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(prepare);
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "intelligence/engagements/engagement/events/result/bank-outstanding-source",
      body: {
        exception_ids: ["books:B1"],
        expected_rows: 1,
        signed_total: "-100",
      },
    });
  });
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
  it("binds the selected retained quote while preparing an exchange rate source", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    for (const [label, value] of [
      ["Source table type", "fx-rates"],
      ["Retained exchange-rate quote (optional shared document)", "clean"],
      ["Clean retained evidence", "clean"],
      ["Schedule title", "Synthetic assessed direct quote"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      table_type: "fx-rates",
      rule_document_version_id: "clean",
      control_totals: {},
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
  it("shows pension amounts in AED with the authority and membership cohort", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      body: {
        workflow: "uae-pension-review",
        title: "Pension review",
        currency: "AED",
        review_status: "UNVERIFIED",
        population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
        expected_total: "1500.00",
        reported_total: "1500.00",
        expected_total_complete: true,
        rows: [
          {
            id: "PENSION-1",
            subject: "MEMBER",
            component: "PENSION:EMPLOYER",
            authority: "SYNTHETIC-AUTHORITY",
            scheme: "SYNTHETIC-SCHEME",
            membership_cohort: "CONTINUING-MEMBER",
            expected_amount: "1500.00",
            reported_amount: "1500.00",
            state: "MATCHED",
            rule_document_sha256: "f".repeat(64),
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.getByText(/Expected contributions: AED 1500.00/),
    ).toBeVisible();
    expect(
      screen.getByRole("columnheader", { name: "authority" }),
    ).toBeVisible();
    expect(screen.getByText("CONTINUING-MEMBER")).toBeVisible();
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

  it("queues AED pension review using only independently reviewed sources", async () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "uae-pension-review" },
    });
    for (const role of ["bases", "rules", "reported"])
      expect(screen.getByLabelText(`${role} source`)).not.toHaveTextContent(
        "Unreviewed",
      );
    for (const [label, value] of [
      ["Schedule title", "Pension June comparison"],
      ["Reconciliation date", "2026-06-30"],
      ["bases source", "pension-bases"],
      ["rules source", "pension-rules"],
      ["reported source", "pension-reported"],
      [
        "Scope and source rationale",
        "Reviewed pension salary, membership and authority assessment",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      workflow: "uae-pension-review",
      currency: "AED",
      source_ids: {
        bases: "pension-bases",
        rules: "pension-rules",
        reported: "pension-reported",
      },
    });
  });

  it("does not offer UAE pension review for an India engagement", () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    expect(
      screen.queryByRole("option", { name: "UAE pension contribution review" }),
    ).not.toBeInTheDocument();
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
        currency: "INR",
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
    ["pension-rules", "Pension"],
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
  it("keeps derived expected dues out of the independent return role", () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "obligation-bank-allocations" },
    });
    expect(screen.getByLabelText("expected source")).toHaveTextContent(
      "Reviewed expected dues",
    );
    expect(screen.getByLabelText("reported source")).not.toHaveTextContent(
      "Reviewed expected dues",
    );
  });

  it("queues original numbered GSTR-2B files with independent per-file controls", async () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source file format"), {
      target: { value: "india-gstr2b-json" },
    });
    fireEvent.click(screen.getByLabelText("Assemble numbered GSTR-2B files"));
    const parts = [1, 2].map((file_number) => ({
      file_number,
      evidence_version_id: `part-${file_number}`,
      expected_documents: 1,
      tax_total: file_number === 1 ? "18" : "9",
      request_reference: `REQUEST-${file_number}`,
    }));
    for (const [label, value] of [
      ["Schedule title", "Complete split GSTR-2B"],
      ["Clean retained evidence", "clean"],
      ["Recipient GSTIN", "27ABCDE5678G1Z8"],
      ["GSTR-2B return month", "2026-06"],
      ["Independent GSTR-2B document count", "2"],
      ["Independent totals by currency", "INR=27"],
      ["Independent GSTR-2B file count", "2"],
      [
        "Original response parts and independent controls (JSON)",
        JSON.stringify(parts),
      ],
      [
        "GSTR-2B retrieval batch assessment",
        "Independent original numbered requests and generation manifest reviewed",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      file_format: "india-gstr2b-json",
      expected_documents: 2,
      expected_rows: 8,
      control_totals: { INR: "27" },
      gstr2b_expected_files: 2,
      gstr2b_parts: parts,
    });
  });

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
  it.each(["AED", "INR"])(
    "queues subsequent bank clearance with an explicit window and %s scope",
    async (currency) => {
      render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
      fireEvent.change(screen.getByLabelText("Workflow"), {
        target: { value: "bank-subsequent-clearance" },
      });
      for (const [label, value] of [
        ["Schedule title", "Subsequent cheque clearance"],
        ["Reconciliation date", "2026-06-30"],
        ["Review through date", "2026-07-31"],
        ["Bank account identifier", "BANK-1"],
        ["Account currency", currency],
        ["outstanding source", "outstanding"],
        ["statement source", "statement"],
        ["allocations source", "clearances"],
        [
          "Scope and source rationale",
          "Retained original BRS items and subsequent clearing evidence",
        ],
      ])
        fireEvent.change(screen.getByLabelText(label), { target: { value } });
      expect(screen.queryByLabelText("book closing")).not.toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Queue calculation" }),
      );
      await waitFor(() => expect(state.mutate).toHaveBeenCalled());
      expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
        workflow: "bank-subsequent-clearance",
        account: "BANK-1",
        currency,
        as_of: "2026-06-30",
        review_through: "2026-07-31",
        source_ids: {
          outstanding: "outstanding",
          statement: "statement",
          allocations: "clearances",
        },
      });
    },
  );
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
describe("UAE import VAT review", () => {
  it("submits an explicit selected-box scope rather than silently filtering a full return", async () => {
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Workflow"), {
      target: { value: "uae-vat-return" },
    });
    for (const [label, value] of [
      ["Schedule title", "Selected import review"],
      ["Reconciliation date", "2026-06-30"],
      [
        "Scope and source rationale",
        "Independent assessed import books compared to the complete retained filed source",
      ],
      ["Required VAT201 boxes, comma separated", "6,7"],
      ["books source", "vat-books"],
      ["return source", "vat-filed"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(
      screen.getByLabelText("Compare only the required VAT201 boxes"),
    );
    fireEvent.change(
      screen.getByLabelText("Selected VAT201 box scope assessment"),
      {
        target: {
          value:
            "Only imports are assessed; all other retained VAT boxes remain outside this comparison",
        },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      restrict_to_required_boxes: true,
      required_boxes: ["6", "7"],
      box_scope_assessment:
        "Only imports are assessed; all other retained VAT boxes remain outside this comparison",
    });
  });

  it("pages excluded rows without changing the selected comparison rows", () => {
    const excluded = Array.from({ length: 101 }, (_, index) => ({
      source_role: "return",
      source_row_id: `EXCLUDED-${index + 1}`,
      box: "1",
      currency: "AED",
      taxable_amount: "1",
      tax: "0.05",
      adjustment: "0",
    }));
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      collection_totals: { rows: 2, excluded_box_rows: 101 },
      body: {
        workflow: "uae-vat-return",
        title: "Selected import boxes",
        review_status: "UNVERIFIED",
        rows: [
          { id: "selected-six", box: "6", state: "MATCHED" },
          { id: "selected-seven", box: "7", state: "MATCHED" },
        ],
        excluded_box_rows: excluded.slice(0, 100),
        box_comparison_scope: {
          mode: "SELECTED_REQUIRED_BOXES",
          required_boxes: ["6", "7"],
          assessment: "Imports only; retain all excluded rows",
          excluded_rows: { books: 0, return: 101 },
          whole_return_completeness: "NOT_DETERMINED",
        },
        population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
      },
    };
    state.excludedPage = { body: { excluded_box_rows: excluded.slice(100) } };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.getByText(/Whole-return completeness is not determined/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("Review 101 excluded VAT box rows"));
    expect(screen.getByRole("cell", { name: "EXCLUDED-1" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next excluded rows" }));
    expect(screen.getByRole("cell", { name: "EXCLUDED-101" })).toBeVisible();
    fireEvent.click(
      screen.getByLabelText("Show source versions and review details"),
    );
    expect(screen.getByRole("cell", { name: "selected-six" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "selected-seven" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Next rows" })).toBeDisabled();
  });
  it("prepares selected boxes only from a current independently reviewed import result", async () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 2,
      freshness: "CURRENT",
      body: {
        workflow: "uae-import-vat",
        title: "Reviewed imports",
        review_status: "REVIEWED",
        rows: [],
        exception_count: 0,
        population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    fireEvent.click(
      screen.getByText("Prepare selected import boxes for VAT201 comparison"),
    );
    fireEvent.change(screen.getByLabelText("Import box source title"), {
      target: { value: "Assessed book import boxes" },
    });
    fireEvent.change(screen.getByLabelText("Assessed import source role"), {
      target: { value: "books" },
    });
    fireEvent.click(screen.getByLabelText("Include import Box 7"));
    for (const [label, value] of [
      ["Box 6 expected detail rows", "1"],
      ["Box 6 taxable amount (AED)", "1000"],
      ["Box 6 tax (AED)", "50"],
      [
        "Import box scope assessment",
        "Independent book role and declaration controls assessed for selected Box 6 only",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(
      screen.getByRole("button", { name: "Prepare import box source" }),
    );
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "intelligence/engagements/engagement/events/result/import-vat-box-source",
      body: {
        source_role: "books",
        boxes: { "6": { expected_rows: 1, taxable_amount: "1000", tax: "50" } },
      },
    });
    expect(state.mutate.mock.calls[0][0].body.boxes).not.toHaveProperty("7");
  });

  it.each(["unreviewed", "stale", "blocked"])(
    "does not offer an import bridge for %s results",
    (status) => {
      state.result = {
        id: "result",
        kind: "country-workflow",
        version: 1,
        freshness: status === "stale" ? "STALE" : "CURRENT",
        body: {
          workflow: "uae-import-vat",
          title: "Import review",
          review_status: status === "unreviewed" ? "UNVERIFIED" : "REVIEWED",
          blocked: status === "blocked",
          rows: [],
          population_completeness: "UPLOADED_FILE_CONTROLS_ONLY",
        },
      };
      render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
      fireEvent.change(screen.getByLabelText("Saved source or result"), {
        target: { value: "result" },
      });
      expect(
        screen.queryByText(
          "Prepare selected import boxes for VAT201 comparison",
        ),
      ).not.toBeInTheDocument();
    },
  );
  it("requires separate source tax and taxable-base controls", async () => {
    render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
    fireEvent.change(screen.getByLabelText("Source table type"), {
      target: { value: "import-vat-lines" },
    });
    fireEvent.change(screen.getByLabelText("Clean retained evidence"), {
      target: { value: "clean" },
    });
    fireEvent.change(screen.getByLabelText("Expected data rows"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Independent totals by currency"), {
      target: { value: "AED=45" },
    });
    fireEvent.change(
      screen.getByLabelText(/Independent import taxable-base total/),
      { target: { value: "900" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
      table_type: "import-vat-lines",
      control_totals: { AED: "45" },
      import_taxable_base_control: "900",
    });
  });

  it("does not offer a domestic UAE import review in India", () => {
    state.country = "IN";
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    expect(
      screen.queryByRole("option", { name: "UAE import VAT review" }),
    ).not.toBeInTheDocument();
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

it("shows VAT201 monetary differences first and preserves original provenance", () => {
  state.result = {
    id: "result",
    kind: "country-workflow",
    version: 1,
    freshness: "CURRENT",
    body: {
      title: "VAT201 comparison",
      workflow: "uae-vat-return",
      review_status: "UNVERIFIED",
      rows: [
        {
          id: "box-1",
          box: "6",
          registration: "100000000000001",
          period_start: "2026-04-01",
          period_end: "2026-06-30",
          currency: "AED",
          differences: { taxable_amount: "10", tax: "0.50", adjustment: "0" },
          book_source_ids: ["composed-box-6"],
          return_source_id: "filed-6",
          state: "VARIANCE",
        },
      ],
    },
  };
  render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Saved source or result"), {
    target: { value: "result" },
  });
  expect(
    screen.getByRole("columnheader", { name: "taxable difference" }),
  ).toBeVisible();
  expect(screen.getByRole("cell", { name: /^0\.50$/ })).toBeVisible();
  expect(
    screen.queryByRole("columnheader", { name: "book source ids" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByLabelText("Show source versions and review details"),
  );
  expect(
    screen.getByRole("columnheader", { name: "book source ids" }),
  ).toBeVisible();
  expect(screen.getByText('["composed-box-6"]')).toBeVisible();
});

it("queues the explicit WPS EVP profile with separate employee and component controls", async () => {
  render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
  fireEvent.change(screen.getByLabelText("Source file format"), {
    target: { value: "uae-wps-sif-evp" },
  });
  const totals = {
    housing_allowance: "40",
    conveyance_allowance: "10",
    medical_allowance: "5",
    annual_passage_allowance: "15",
    overtime_allowance: "20",
    other_allowances: "8",
    leave_encashment: "2",
  };
  for (const [label, value] of [
    ["Schedule title", "EVP source"],
    ["Clean retained evidence", "clean"],
    ["Expected data rows", "2"],
    ["Independent totals by currency", "AED=1500"],
    ["Independent EVP record count", "1"],
    ["Independent EVP component totals (AED, JSON)", JSON.stringify(totals)],
    ["Employer registration cross-check (optional)", "1234567890123"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    file_format: "uae-wps-sif-evp",
    table_type: "obligations",
    expected_rows: 2,
    control_totals: { AED: "1500" },
    wps_variable_pay_count: 1,
    wps_variable_pay_totals: totals,
    employer_registration: "1234567890123",
  });
});

it("submits independently declared inventory partition controls with the retained CSV", async () => {
  render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
  fireEvent.change(screen.getByLabelText("Source table type"), {
    target: { value: "stock-movements" },
  });
  fireEvent.click(
    screen.getByLabelText("Declare independent inventory quantity controls"),
  );
  const controls = [
    {
      site: "WH-1",
      sku: "SKU-1",
      lot: "A",
      uom: "EA",
      currency: "AED",
      expected_rows: 2,
      positive_quantity: "4",
      negative_quantity: "-1",
    },
  ];
  for (const [label, value] of [
    ["Schedule title", "Inventory movements"],
    ["Clean retained evidence", "clean"],
    ["Expected data rows", "2"],
    ["Independent inventory partitions (JSON)", JSON.stringify(controls)],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    table_type: "stock-movements",
    inventory_quantity_controls: controls,
    control_totals: {},
  });
});

it("uses only reviewed quantity-controlled inventory sources in bidirectional mode", async () => {
  render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Workflow"), {
    target: { value: "inventory-count-bridge" },
  });
  fireEvent.click(
    screen.getByLabelText("Use controlled counts before or after reporting"),
  );
  expect(screen.getByLabelText("books source")).not.toHaveTextContent(
    "Uncontrolled stock",
  );
  for (const [label, value] of [
    ["Schedule title", "Reviewed inventory bridge"],
    ["Reconciliation date", "2026-06-30"],
    ["Inventory evidence review through", "2026-07-03"],
    [
      "Inventory day-end cutoff assessment",
      "Independent exclusive earlier and inclusive later day-end movement populations assessed",
    ],
    ["books source", "inventory-books"],
    ["counts source", "inventory-counts"],
    ["movements source", "inventory-movements"],
    [
      "Scope and source rationale",
      "Original retained count and complete signed movement populations by lot",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    stock_bridge_mode: "bidirectional-controlled",
    review_through: "2026-07-03",
    stock_cutoff_assessment:
      "Independent exclusive earlier and inclusive later day-end movement populations assessed",
    source_ids: {
      books: "inventory-books",
      counts: "inventory-counts",
      movements: "inventory-movements",
    },
  });
});

it("queues the separate arrear profile with retained context and six independent controls", async () => {
  state.country = "IN";
  render(<CountryWorkflows eid="engagement" mode="workflow-source" />);
  fireEvent.change(screen.getByLabelText("Source file format"), {
    target: { value: "india-epfo-arrear-ecr-v2" },
  });
  fireEvent.change(screen.getByLabelText("Clean retained evidence"), {
    target: { value: "clean" },
  });
  const controls = {
    epf_wages: "1500",
    eps_wages: "1000",
    edli_wages: "1500",
    employee_pf: "180",
    employer_pf: "97",
    employer_eps: "83",
  };
  for (const [label, value] of [
    ["Schedule title", "Arrear source"],
    ["EPFO establishment registration", "SYNTHETIC-EPFO-001"],
    ["ECR wage month", "2026-06"],
    ["Independent ECR member count", "2"],
    ["Expected data rows", "6"],
    ["Retained arrear month/disbursement context", "context-clean"],
    ["Salary arrear disbursement date", "2026-07-10"],
    [
      "Independent arrear wage and contribution totals (INR, JSON)",
      JSON.stringify(controls),
    ],
    [
      "Arrear wage-month attribution assessment",
      "Independent retained context and member wage-month attribution assessed",
    ],
    ["Independent totals by currency", "INR=360"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    file_format: "india-epfo-arrear-ecr-v2",
    obligation_period: "2026-06",
    employer_registration: "SYNTHETIC-EPFO-001",
    expected_members: 2,
    expected_rows: 6,
    ecr_arrear_controls: controls,
    arrear_context_evidence_version_id: "context-clean",
    arrear_disbursement_date: "2026-07-10",
  });
});

it("keeps regular payments out of an explicitly arrear-only comparison", async () => {
  state.country = "IN";
  render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Workflow"), {
    target: { value: "statutory-dues" },
  });
  fireEvent.click(
    screen.getByLabelText(
      "Compare arrears only, separately from regular monthly dues",
    ),
  );
  expect(screen.getByLabelText("payment source")).not.toHaveTextContent(
    "Regular monthly payment",
  );
  for (const [label, value] of [
    ["Schedule title", "Arrear-only comparison"],
    ["Arrear comparison currency", "INR"],
    ["Reconciliation date", "2026-07-31"],
    [
      "Scope and source rationale",
      "Independent arrear populations compared separately from monthly regular dues",
    ],
    ["expected source", "arrear-expected"],
    ["return source", "arrear-return"],
    ["payment source", "arrear-payment"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
    arrear_only: true,
    source_ids: {
      expected: "arrear-expected",
      return: "arrear-return",
      payment: "arrear-payment",
    },
  });
});

describe("reviewed bank residual carry-forward", () => {
  function result(review = "REVIEWED", freshness = "CURRENT") {
    return {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness,
      body: {
        title: "Partial bank clearance",
        workflow: "bank-subsequent-clearance",
        review_status: review,
        rows: [
          {
            id: "outstanding:O1",
            kind: "outstanding",
            remaining_after_review: "-60",
            state: "PARTIALLY_CLEARED",
          },
        ],
      },
    };
  }
  it("requires independent directional controls before carrying the full residual population", async () => {
    state.result = result();
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    fireEvent.click(
      screen.getByText(
        "Carry reviewed bank residuals into the next clearance window",
      ),
    );
    const prepare = screen.getByRole("button", {
      name: "Prepare carried bank residuals",
    });
    expect(prepare).toBeDisabled();
    expect(screen.getByLabelText("Independent residual row count")).toHaveValue(
      null,
    );
    expect(
      screen.getByLabelText("Independent negative residual total"),
    ).toHaveValue("");
    for (const [label, value] of [
      ["Carry-forward source title", "Reviewed carried cheque"],
      ["Independent residual row count", "1"],
      ["Independent positive residual total", "0"],
      ["Independent negative residual total", "-60"],
      [
        "Carry-forward window and reversal assessment",
        "Retained bank window and unresolved reversal evidence assessed",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(prepare);
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "intelligence/engagements/engagement/events/result/bank-carryforward-source",
      body: {
        expected_rows: 1,
        positive_total: "0",
        negative_total: "-60",
        label: "Reviewed carried cheque",
      },
    });
  });
  it.each([
    ["UNVERIFIED", "CURRENT"],
    ["REVIEWED", "STALE"],
  ])("hides carry-forward for %s / %s", (review, freshness) => {
    state.result = result(review, freshness);
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    expect(
      screen.queryByText(
        "Carry reviewed bank residuals into the next clearance window",
      ),
    ).not.toBeInTheDocument();
  });
});

describe("payroll accounting bridge", () => {
  it.each(["AE", "IN"])(
    "queues a scoped accounting window with reviewed sources for %s",
    async (country) => {
      state.country = country;
      render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
      fireEvent.change(screen.getByLabelText("Workflow", { exact: true }), {
        target: { value: "payroll-ledger-rollforward" },
      });
      expect(
        screen.getByLabelText("payroll source", { exact: true }),
      ).not.toHaveTextContent("Unreviewed payroll ledger");
      for (const [label, value] of [
        ["Schedule title", "Payroll GL June"],
        ["Reconciliation date", "2026-06-30"],
        ["Reporting period start", "2026-06-01"],
        [
          "Scope and source rationale",
          "Independent debit/credit normal signs and wage-month allocation assessed",
        ],
      ])
        fireEvent.change(screen.getByLabelText(label, { exact: true }), {
          target: { value },
        });
      for (const role of ["opening", "payroll", "posted", "closing"])
        fireEvent.change(
          screen.getByLabelText(`${role} source`, { exact: true }),
          { target: { value: "ledger-" + role } },
        );
      fireEvent.click(
        screen.getByRole("button", { name: "Queue calculation" }),
      );
      await waitFor(() => expect(state.mutate).toHaveBeenCalled());
      expect(state.mutate.mock.calls[0][0].body.payload).toMatchObject({
        workflow: "payroll-ledger-rollforward",
        period_start: "2026-06-01",
        as_of: "2026-06-30",
        source_ids: {
          opening: "ledger-opening",
          payroll: "ledger-payroll",
          posted: "ledger-posted",
          closing: "ledger-closing",
        },
      });
    },
  );
  it("pages individual posting links independently of the comparison rows", () => {
    state.result = {
      id: "result",
      kind: "country-workflow",
      version: 1,
      freshness: "CURRENT",
      collection_totals: { payroll_posting_links: 101 },
      body: {
        title: "Payroll GL comparison",
        workflow: "payroll-ledger-rollforward",
        review_status: "UNVERIFIED",
        rows: [
          {
            id: "COMP",
            kind: "posting-comparison",
            account: "SALARY",
            state: "MATCHED",
          },
        ],
        payroll_posting_links: Array.from({ length: 100 }, (_, index) => ({
          source_row_id: "PAY-" + index,
          source_role: "payroll",
          comparison_row_id: "COMP",
          account: "SALARY",
          currency: "AED",
          amount: "1",
        })),
      },
    };
    state.postingPage = {
      body: {
        payroll_posting_links: [
          {
            source_row_id: "PAY-100",
            source_role: "posted",
            comparison_row_id: "COMP",
            account: "SALARY",
            currency: "AED",
            amount: "1",
          },
        ],
      },
    };
    render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
    fireEvent.change(screen.getByLabelText("Saved source or result"), {
      target: { value: "result" },
    });
    fireEvent.click(screen.getByText(/Payroll posting source links/));
    fireEvent.click(screen.getByRole("button", { name: "Next posting links" }));
    expect(screen.getByRole("cell", { name: "PAY-100" })).toBeVisible();
    expect(
      screen.queryByRole("cell", { name: "PAY-0" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next posting links" }),
    ).toBeDisabled();
  });
});

it("requires all twenty explicit VAT201 boxes after selecting the emirate layout", async () => {
  render(<CountryWorkflows eid="engagement" mode="country-workflow" />);
  fireEvent.change(screen.getByLabelText("Workflow"), {
    target: { value: "uae-vat-return" },
  });
  fireEvent.change(screen.getByLabelText("VAT201 comparison layout"), {
    target: { value: "emirate-20" },
  });
  expect(
    screen.getByLabelText("Required VAT201 boxes, comma separated"),
  ).toBeDisabled();
  expect(
    screen.getByLabelText("Required VAT201 boxes, comma separated"),
  ).toHaveValue("1a,1b,1c,1d,1e,1f,1g,2,3,4,5,6,7,8,9,10,11,12,13,14");
  expect(
    screen.getByLabelText("Compare only the required VAT201 boxes"),
  ).toBeDisabled();
  for (const [label, value] of [
    ["Schedule title", "Emirate comparison"],
    ["Reconciliation date", "2026-06-30"],
    [
      "Scope and source rationale",
      "All seven geographic allocations independently assessed",
    ],
    ["books source", "vat-books"],
    ["return source", "vat-filed"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Queue calculation" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  const payload = state.mutate.mock.calls[0][0].body.payload;
  expect(payload.vat201_layout).toBe("emirate-20");
  expect(payload.required_boxes).toHaveLength(20);
  expect(payload.restrict_to_required_boxes).toBeUndefined();
});

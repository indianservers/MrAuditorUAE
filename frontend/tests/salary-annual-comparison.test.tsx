import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  SalaryAnnualComparison,
  SalaryAnnualLinks,
} from "@/features/salary-annual-comparison";

const mock = vi.hoisted(() => ({ mutate: vi.fn(), paths: [] as string[] }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: mock.mutate,
    isPending: false,
    error: null,
  }),
  useAPI: (path: string) => {
    mock.paths.push(path);
    return {
      data: {
        body: {
          salary_quarterly_links: Array.from(
            { length: path.includes("offset=100") ? 1 : 100 },
            (_, index) => ({
              annual_key: "SD/1/1",
              quarter: path.includes("offset=100") ? "Q4" : "Q1",
              party_key: `1/1/${index + 1}`,
              total_tax: "100.00",
            }),
          ),
          unassigned_quarterly_parties: [
            {
              quarter: "Q2",
              party_key: "1/1/2",
              native_section_code: "94P",
              total_tax: "25.00",
            },
          ],
        },
        collection_totals: {
          salary_quarterly_links: 101,
          unassigned_quarterly_parties: 1,
        },
      },
      isFetching: false,
      error: null,
    };
  },
}));

const source = (
  id: string,
  freshness = "CURRENT",
  review_status = "REVIEWED",
) => ({
  id,
  label: id,
  kind: "workflow-source",
  table_type: "withholding-records",
  freshness,
  review_status,
});
const evidence = [
  {
    id: "doc",
    label: "Independent annual employee mapping",
    scan_status: "CLEAN",
    sha256: "a".repeat(64),
  },
];
describe("Annual salary current-employer comparison", () => {
  beforeEach(() => {
    mock.mutate.mockReset();
    mock.mutate.mockResolvedValue({ id: "annual" });
    mock.paths.length = 0;
  });
  it("requires every quarter and explicit nil support, preserving full employee JSON", async () => {
    const created = vi.fn();
    render(
      <SalaryAnnualComparison
        eid="eng"
        sources={[
          source("q4"),
          source("stale", "STALE"),
          source("draft", "CURRENT", "UNVERIFIED"),
        ]}
        evidence={evidence}
        onCreated={created}
      />,
    );
    fireEvent.click(
      screen.getByText(
        "Compare four salary quarters with annual current-employer tax",
      ),
    );
    const button = screen.getByRole("button", {
      name: "Prepare annual salary comparison",
    });
    expect(button).toBeDisabled();
    expect(
      (screen.getByLabelText("Salary Q4 native source") as HTMLSelectElement)
        .options,
    ).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Annual salary comparison title"), {
      target: { value: "SYNTHETIC annual comparison" },
    });
    for (const q of ["Q1", "Q2", "Q3"]) {
      fireEvent.change(screen.getByLabelText(`Salary ${q} native source`), {
        target: { value: "NIL" },
      });
      fireEvent.change(screen.getByLabelText(`Salary ${q} nil assessment`), {
        target: {
          value: `SYNTHETIC independent ${q} nil population assessment`,
        },
      });
    }
    fireEvent.change(screen.getByLabelText("Salary Q4 native source"), {
      target: { value: "q4" },
    });
    fireEvent.change(
      screen.getByLabelText(
        "Independent annual employee and nil-quarter crosswalk",
      ),
      { target: { value: "doc" } },
    );
    const employees = [
      {
        annual_key: "SD/1/1",
        parties: [{ quarter: "Q4", party_key: "1/1/1" }],
        identity_status: "unresolved",
        assessment: "SYNTHETIC identity requires independent review",
      },
    ];
    fireEvent.change(
      screen.getByLabelText("Annual salary employee mapping (JSON)"),
      { target: { value: JSON.stringify(employees) } },
    );
    fireEvent.change(
      screen.getByLabelText("Annual salary full-population assessment"),
      {
        target: {
          value: "SYNTHETIC complete population and source assessment",
        },
      },
    );
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(created).toHaveBeenCalledWith("annual"));
    const request = mock.mutate.mock.calls[0][0];
    expect(request.path).toBe(
      "intelligence/engagements/eng/salary-annual-comparison",
    );
    expect(request.body.quarter_source_ids).toEqual({
      Q1: null,
      Q2: null,
      Q3: null,
      Q4: "q4",
    });
    expect(request.body.employees).toEqual(employees);
    expect(request.body.crosswalk_sha256).toBe("a".repeat(64));
    expect(Object.keys(request.body.nil_quarter_assessments)).toEqual([
      "Q1",
      "Q2",
      "Q3",
    ]);
  });
  it("pages full assigned coverage and keeps unassigned senior parties visible", () => {
    render(
      <SalaryAnnualLinks
        prefix="intelligence/engagements/eng"
        selected="annual"
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Next salary parties" }),
    );
    expect(mock.paths.at(-1)).toContain("salary_link_offset=100");
    expect(screen.getByRole("cell", { name: "Q4" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Salary party coverage view"), {
      target: { value: "unassigned_quarterly_parties" },
    });
    expect(mock.paths.at(-1)).toContain("salary_link_offset=0");
    expect(screen.getByRole("cell", { name: "94P" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next salary parties" }),
    ).toBeDisabled();
  });
});

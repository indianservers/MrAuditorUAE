import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatutoryReportPreview } from "@/features/statutory-report-preview";

function fixture(count = 877) {
  return {
    title: "SYNTHETIC retained report",
    category: "india-tax-audit",
    document_status: "DRAFT — NOT SIGNED OR FILED",
    template_id: "original-template",
    template_version: 2,
    template_sha256: "a".repeat(64),
    requirements_basis:
      "Synthetic declared control scope; no statutory qualification",
    tax_audit_scope: {
      form: "26",
      audit_report_part: "B",
      tax_period_start: "2026-04-01",
      tax_period_end: "2027-03-31",
      audited_under_other_law: false,
    },
    requirements_coverage: {
      source_validation: "CURRENT_REVIEWED_SOURCES_RECHECKED",
      requirements_pack: {
        id: "india-form26-index:B/2",
        fields: Array.from({ length: count }, (_, i) => ({
          key: `field.${i + 1}`,
          page: 17,
        })),
      },
      items: Array.from({ length: count }, (_, i) => ({
        key: `field.${i + 1}`,
        title: `Saved field ${i + 1}`,
        disposition: "REQUIRED",
        status: "COVERED",
        block_keys: [`block-${Math.floor(i / 100) + 1}`],
      })),
    },
    blocks: Array.from({ length: 9 }, (_, i) => ({
      key: `block-${i + 1}`,
      number: i + 1,
      title: `Saved block ${i + 1}`,
      kind: "working_paper_reference",
      source_kind: "record",
      source_id: `source-${i + 1}`,
      source_receipt: { id: `source-${i + 1}`, version: 4 },
      narrative_origin: "SOURCE_ONLY",
      data: {
        sections: [
          {
            heading: "Original procedure",
            text: "Retained original assessment",
          },
        ],
        conclusion: "Original source conclusion",
        financial_tables: [
          {
            title: "Exact source values",
            values: {
              amount: "0.12345678901234567890",
              quantity: "0",
              assessed: false,
            },
          },
        ],
      },
    })),
  };
}

describe("retained statutory report preview", () => {
  it("pages all fields and source blocks independently while preserving the full saved body", () => {
    const body = fixture();
    const original = JSON.stringify(body);
    render(
      <StatutoryReportPreview body={body} freshness="CURRENT" eid="eng" />,
    );
    const table = screen.getByRole("table", {
      name: "Saved requirement references and block coverage",
    });
    expect(within(table).getAllByRole("row")).toHaveLength(21);
    expect(
      within(table).queryByRole("cell", { name: "field.21" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Next saved requirements" }),
    );
    expect(
      within(table).getByRole("cell", { name: "field.21" }),
    ).toBeInTheDocument();
    fireEvent.change(
      screen.getByLabelText("Search saved report requirements"),
      { target: { value: "field.877" } },
    );
    expect(
      within(table).getByRole("cell", { name: "field.877" }),
    ).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "17" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "9. Saved block 9" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next saved blocks" }));
    expect(
      screen.getByRole("heading", { name: "9. Saved block 9" }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", { name: "field.877" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next saved blocks" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Other-law audit assessment: false/),
    ).toBeInTheDocument();
    expect(JSON.stringify(body)).toBe(original);
  });

  it("shows staleness without altering saved assertions and lazily exposes exact source values", async () => {
    const body = fixture(1);
    const original = JSON.stringify(body);
    render(<StatutoryReportPreview body={body} freshness="STALE" eid="eng" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This saved report is STALE",
    );
    expect(
      screen.getByText(
        /Declared coverage does not establish statutory completeness/,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("0.12345678901234567890")).toHaveLength(5);
    const summary = screen.getByText(
      "Complete retained source content for block-1",
    );
    const disclosure = summary.closest("details")!;
    expect(disclosure.querySelector("pre")).toBeNull();
    fireEvent.click(summary);
    await waitFor(() => expect(disclosure.querySelector("pre")).not.toBeNull());
    expect(disclosure.querySelector("pre")).toHaveTextContent(
      '"assessed": false',
    );
    expect(disclosure.querySelector("pre")).toHaveTextContent(
      '"quantity": "0"',
    );
    expect(disclosure.querySelector("pre")).toHaveTextContent(
      "0.12345678901234567890",
    );
    expect(JSON.stringify(body)).toBe(original);
  });

  it("supports a common UAE report without inventing tax scope or missing source metadata", () => {
    const body = {
      title: "SYNTHETIC UAE audit draft",
      category: "uae-ifrs",
      document_status: "DRAFT — NOT SIGNED OR FILED",
      blocks: [
        {
          key: "authored",
          number: 1,
          title: "Authored commentary",
          kind: "narrative",
          text: "Original user commentary",
          narrative_origin: "USER_AUTHORED",
        },
      ],
    };
    render(
      <StatutoryReportPreview body={body} freshness="CURRENT" eid="eng" />,
    );
    expect(
      screen.getByRole("heading", { name: body.title }),
    ).toBeInTheDocument();
    expect(screen.getByText("Original user commentary")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Saved tax audit scope" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("No saved requirements match this search."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Review saved block source" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Custom declared scope")).toBeInTheDocument();
  });
  it("retains late source columns and pages original rows independently of report requirements", () => {
    const originalRows = Array.from({ length: 21 }, (_, i) => ({
      reference: `ROW-${i + 1}`,
      amount: "100.00000000000000000001",
      quantity: 0,
      assessed: false,
      ...(i === 20 ? { late_column: "Retained last-row detail" } : {}),
    }));
    const body = {
      ...fixture(1),
      blocks: [
        {
          key: "finance",
          number: 1,
          title: "Saved financial source",
          kind: "financial_table",
          source_kind: "intelligence",
          source_id: "original-source",
          source_receipt: { version: 3, sha256: "b".repeat(64) },
          data: { rows: originalRows },
        },
      ],
    };
    const original = JSON.stringify(body);
    render(
      <StatutoryReportPreview body={body} freshness="CURRENT" eid="eng" />,
    );
    const region = screen.getByRole("region", {
      name: "Saved source rows for finance",
    });
    expect(
      within(region).getByRole("columnheader", { name: "late_column" }),
    ).toBeInTheDocument();
    expect(
      within(region).queryByText("Retained last-row detail"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(region).getByRole("button", { name: "Next source rows" }),
    );
    expect(
      within(region).getByText("Retained last-row detail"),
    ).toBeInTheDocument();
    expect(
      within(region).getByRole("cell", { name: "100.00000000000000000001" }),
    ).toBeInTheDocument();
    expect(within(region).getByRole("cell", { name: "0" })).toBeInTheDocument();
    expect(
      within(region).getByRole("cell", { name: "false" }),
    ).toBeInTheDocument();
    expect(
      within(region).getByRole("button", { name: "Next source rows" }),
    ).toBeDisabled();
    expect(JSON.stringify(body)).toBe(original);
  });
});

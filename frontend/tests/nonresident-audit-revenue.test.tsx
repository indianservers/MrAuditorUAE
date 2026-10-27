import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { NonresidentAuditRevenueEditor } from "@/features/nonresident-audit-revenue";
const state = vi.hoisted(() => ({
  paper: {
    id: "paper",
    reference: "Reviewed scope",
    status: "APPROVED",
    body: {
      financial_tables: [] as {
        title: string;
        values: Record<string, unknown>;
      }[],
    },
  },
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string, enabled = true) => ({
    data: !enabled
      ? undefined
      : path.includes("/records/")
        ? state.paper
        : { items: [], total: 0 },
  }),
}));
const facts = {
  amount: "0",
  currency: "AED",
  period_start: "2026-01-01",
  period_end: "2026-12-31",
  scope: "uae_pe_and_nexus",
  population_complete: false,
  assessment: "Synthetic reviewed incomplete population",
};
beforeEach(() => {
  state.paper.status = "APPROVED";
  state.paper.body.financial_tables = [
    { title: "UAE scope", values: { ...facts } },
    {
      title: "Second scope",
      values: { ...facts, amount: "50000000", population_complete: true },
    },
  ];
});
function Editor({ change }: { change: (value: unknown) => void }) {
  const [value, setValue] = useState<unknown>({
    ...facts,
    evidence_id: "paper",
    source_path: ["financial_tables", 0, "values"],
  });
  return (
    <NonresidentAuditRevenueEditor
      base="engagements/one/audit"
      value={value}
      onChange={(value) => {
        change(value);
        setValue(value);
      }}
    />
  );
}
describe("nonresident revenue scope adoption", () => {
  it("adopts exact zero and incomplete facts without defaulting completeness", () => {
    const change = vi.fn();
    render(<Editor change={change} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Adopt reviewed revenue scope" }),
    );
    expect(change).toHaveBeenLastCalledWith({
      ...facts,
      evidence_id: "paper",
      source_path: ["financial_tables", 0, "values"],
    });
    expect(
      screen.getByText(/incomplete; obligation remains unresolved/),
    ).toBeTruthy();
  });
  it("keeps the selected paper when switching a retained table and binds the new table", () => {
    const change = vi.fn();
    render(<Editor change={change} />);
    fireEvent.change(screen.getByLabelText("Retained revenue scope table"), {
      target: { value: "1" },
    });
    expect(screen.getByLabelText("Revenue scope working paper")).toHaveValue(
      "paper",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Adopt reviewed revenue scope" }),
    );
    expect(change).toHaveBeenLastCalledWith(
      expect.objectContaining({
        amount: "50000000",
        population_complete: true,
        evidence_id: "paper",
        source_path: ["financial_tables", 1, "values"],
      }),
    );
  });
  it("rejects unassessed string booleans rather than coercing them", () => {
    state.paper.body.financial_tables[0].values.population_complete = "false";
    const change = vi.fn();
    render(<Editor change={change} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Adopt reviewed revenue scope" }),
    );
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "explicit population-completeness decision",
    );
  });
  it("does not allow adoption from an unreviewed source", () => {
    state.paper.status = "DRAFT";
    render(<Editor change={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "Adopt reviewed revenue scope" }),
    ).toBeDisabled();
  });
});

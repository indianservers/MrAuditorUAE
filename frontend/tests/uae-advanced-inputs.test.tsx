import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { UAEAdvancedInputs } from "@/features/uae-advanced-inputs";
const mocks = vi.hoisted(() => ({ run: vi.fn(), allowed: true }));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => mocks.allowed,
  useAction: () => ({ mutateAsync: mocks.run, isPending: false }),
}));
const sources = [
  {
    id: "approved",
    reference: "APP",
    title: "Source",
    status: "APPROVED",
    kind: "working-papers",
    advanced_case_id: 52,
  },
  {
    id: "draft",
    reference: "DRAFT",
    title: "Draft",
    status: "IN_PROGRESS",
    kind: "working-papers",
  },
];
const contract = {
  name: "Residual VAT allocation",
  fields: [
    { name: "residual", type: "n" },
    { name: "supported", type: "b" },
  ],
  required_evidence: ["method"],
  limitation: "Reviewed method only",
};
describe("Advanced typed inputs", () => {
  beforeEach(() => {
    mocks.allowed = true;
    mocks.run.mockReset();
    mocks.run.mockResolvedValue({ id: "result" });
  });
  it("shows contextual facts, preserves unresolved booleans and excludes unapproved sources", () => {
    render(
      <UAEAdvancedInputs
        eid="e"
        caseId={52}
        contract={contract}
        sources={sources}
        onResult={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByText("Residual VAT allocation")).toBeVisible();
    expect(screen.getByLabelText("supported")).toHaveValue("");
    expect(
      screen.queryByRole("option", { name: /DRAFT/ }),
    ).not.toBeInTheDocument();
  });
  it("runs only the selected approved input and sends no rate/value overrides", async () => {
    render(
      <UAEAdvancedInputs
        eid="e"
        caseId={52}
        contract={contract}
        sources={sources}
        onResult={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    fireEvent.change(
      screen.getByLabelText("Approved case-specific input paper"),
      { target: { value: "approved" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Run structured review" }),
    );
    await waitFor(() => expect(mocks.run).toHaveBeenCalled());
    expect(mocks.run.mock.calls[0][0]).toMatchObject({
      path: "ai/engagements/e/use-cases/52/actions",
      body: { action: "advanced-review", record_id: "approved" },
    });
    expect(mocks.run.mock.calls[0][0].body.payload).toBeUndefined();
  });
  it("requires preparation permission and keeps workbook inspection separate", () => {
    mocks.allowed = false;
    render(
      <UAEAdvancedInputs
        eid="e"
        caseId={97}
        contract={contract}
        sources={sources}
        onResult={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", {
        name: "Save input paper for independent approval",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Inspect workbook formulas" }),
    ).toBeDisabled();
  });
});

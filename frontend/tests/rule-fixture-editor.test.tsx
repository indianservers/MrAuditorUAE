import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { RuleFixtureEditor } from "@/features/rule-fixture-editor";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: null, error: null }),
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
const vectors = JSON.stringify([
  {
    id: "CASE",
    kind: "flat_rate",
    expected_reference: "Independent synthetic oracle",
    period_start: "2026-01-01",
    period_end: "2026-12-31",
    facts: { tax_base: "100.01", tax_base_currency: "AED" },
    expected_applicability: "APPLICABLE",
    expected_amount: "12.50",
  },
]);
function FixtureForm({ initial = vectors }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return <RuleFixtureEditor id="rule" value={value} onChange={setValue} />;
}
beforeEach(() => state.mutate.mockReset());

it("refuses an empty fixture list without claiming validation", async () => {
  render(<FixtureForm initial="[]" />);
  fireEvent.click(
    screen.getByRole("button", { name: "Check supplied fixtures" }),
  );
  await waitFor(() =>
    expect(
      screen.getByText("Provide one to twenty fixture cases"),
    ).toBeVisible(),
  );
  expect(state.mutate).not.toHaveBeenCalled();
});

it("hides a previously passing receipt when its inputs or expected values change", async () => {
  state.mutate.mockResolvedValue({
    passed: true,
    case_count: 1,
    receipt_sha256: "a".repeat(64),
    outcomes: [],
  });
  render(<FixtureForm />);
  fireEvent.click(
    screen.getByRole("button", { name: "Check supplied fixtures" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("region", { name: "Fixture check result" }),
    ).toBeVisible(),
  );
  fireEvent.change(screen.getByLabelText("Validation fixture cases (JSON)"), {
    target: { value: vectors.replace("12.50", "12.50125") },
  });
  expect(
    screen.queryByRole("region", { name: "Fixture check result" }),
  ).not.toBeInTheDocument();
});

it("keeps independently entered expectations unchanged when the machine reports a mismatch", async () => {
  state.mutate.mockResolvedValue({
    passed: false,
    case_count: 1,
    receipt_sha256: "b".repeat(64),
    outcomes: [
      {
        expected: { amount: "12.50" },
        actual: { amount: "12.50125" },
        passed: false,
      },
    ],
  });
  render(<FixtureForm />);
  fireEvent.click(
    screen.getByRole("button", { name: "Check supplied fixtures" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "Fixture validation failed",
    ),
  );
  expect(screen.getByLabelText("Validation fixture cases (JSON)")).toHaveValue(
    vectors,
  );
  expect(
    screen.getByRole("region", { name: "Fixture check result" }),
  ).toHaveTextContent("12.50125");
  expect(state.mutate).toHaveBeenCalledWith({
    path: "regulatory/rules/rule/validate",
    body: { cases: JSON.parse(vectors) },
  });
});

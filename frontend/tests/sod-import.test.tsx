import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mock = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ ...mock, isPending: false, error: null }),
  useCan: () => true,
}));
import { SoDImport } from "@/features/grc-actions";
beforeEach(() => mock.mutate.mockReset());

function fill() {
  for (const [label, value] of [
    ["Access population reference", "SYN-ACCESS"],
    ["Access population title", "Synthetic access"],
    ["ERP system", "SYNTHETIC ERP"],
    ["Approved SoD rule reference", "rule-id"],
    ["Assessment date", "2026-12-31"],
    ["Approved CSV evidence reference", "csv-id"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.change(screen.getByLabelText("ERP access CSV"), {
    target: {
      files: [new File(["synthetic"], "access.csv", { type: "text/csv" })],
    },
  });
}
function submit() {
  fireEvent.submit(
    screen.getByRole("button", { name: "Import for review" }).closest("form")!,
  );
  return JSON.parse(mock.mutate.mock.calls[0][0].body.get("metadata")).body;
}
it("preserves the point-in-time default without invented history or controls", () => {
  render(<SoDImport base="/grc/E" />);
  fill();
  const body = submit();
  expect(body.population_basis).toBe("point-in-time-export");
  expect(body.period_start).toBeUndefined();
  expect(body.coverage_start).toBeUndefined();
  expect(body.expected_assignment_count).toBeUndefined();
});
it("sends explicit history coverage, analysis period and numeric independent counts", () => {
  render(<SoDImport base="/grc/E" />);
  fill();
  fireEvent.change(screen.getByLabelText("Population basis"), {
    target: { value: "validity-history" },
  });
  expect(screen.getByLabelText("Verified history coverage start")).toHaveValue(
    "",
  );
  for (const [label, value] of [
    [
      "Analysis period start (optional; otherwise assessment date)",
      "2026-04-01",
    ],
    ["Verified history coverage start", "2026-01-01"],
    ["Verified history coverage end", "2026-12-31"],
    [
      "History population scope assessment",
      "Full grant and revocation history independently assessed",
    ],
    ["Expected assignment count", "2"],
    ["Expected principal count", "1"],
    ["Approved population control evidence reference", "controls-id"],
    ["Population control memo reference", "Independent counts memo 1"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const body = submit();
  expect(body.period_start).toBe("2026-04-01");
  expect(body.coverage_start).toBe("2026-01-01");
  expect(body.expected_assignment_count).toBe(2);
  expect(body.expected_principal_count).toBe(1);
  expect(body.population_control_evidence_id).toBe("controls-id");
});

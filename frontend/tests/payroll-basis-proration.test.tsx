import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import {
  PayrollBasisSegments,
  ProratedPayrollSource,
} from "@/features/payroll-basis-proration";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => state.mutate.mockReset());

it("starts with blank independent count and amount controls", () => {
  render(
    <ProratedPayrollSource eid="eng" resultId="result" onCreated={vi.fn()} />,
  );
  expect(
    screen.getByLabelText("Independent PF component-basis row count"),
  ).toHaveValue("");
  expect(
    screen.getByLabelText(
      "Independent post-ceiling component-basis total (INR)",
    ),
  ).toHaveValue("");
  expect(screen.getByRole("button")).toBeDisabled();
  expect(
    screen.getByText(/not gross payroll or a contribution total/),
  ).toBeVisible();
});

it("posts exact typed control text and a whole-result identity", async () => {
  state.mutate.mockResolvedValue({ id: "derived" });
  const created = vi.fn();
  render(
    <ProratedPayrollSource eid="eng" resultId="result" onCreated={created} />,
  );
  for (const [label, value] of [
    ["Monthly basis source title", "Controlled monthly PF bases"],
    ["Independent PF component-basis row count", "9"],
    ["Independent post-ceiling component-basis total (INR)", "129333.31"],
    [
      "Monthly basis control assessment",
      "Independent original component schedule checked",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(created).toHaveBeenCalledWith("derived"));
  expect(state.mutate).toHaveBeenCalledWith({
    path: "intelligence/engagements/eng/prorated-payroll-basis-source",
    body: {
      result_id: "result",
      expected_rows: 9,
      control_total: "129333.31",
      label: "Controlled monthly PF bases",
      assessment: "Independent original component schedule checked",
    },
  });
});

it("does not accept a partial count or negative total", () => {
  render(
    <ProratedPayrollSource eid="eng" resultId="result" onCreated={vi.fn()} />,
  );
  fireEvent.change(
    screen.getByLabelText("Independent PF component-basis row count"),
    { target: { value: "2" } },
  );
  fireEvent.change(
    screen.getByLabelText(
      "Independent post-ceiling component-basis total (INR)",
    ),
    { target: { value: "-1" } },
  );
  expect(screen.getByRole("button")).toBeDisabled();
});

it("labels an explicit exclusion, unknown policy and the bounded preview", () => {
  const segments = Array.from({ length: 21 }, (_, i) => ({
    id: `s-${i}`,
    subject: "EMP",
    eligible: false,
    cap_rule_id: null,
    amount: "0.00",
    post_cap_segment_basis: "0.00",
  }));
  render(<PayrollBasisSegments rows={[{ segment_trace: segments }]} />);
  expect(screen.getByText(/21 segment records/)).toHaveTextContent(
    "Showing the first 20",
  );
  expect(screen.getAllByText("Assessed excluded")).toHaveLength(20);
  expect(screen.getAllByText("Not established").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("row")).toHaveLength(21);
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { BenefitSettlementSource } from "@/features/benefit-settlement-source";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => state.mutate.mockReset());
const row = {
  id: "E1",
  service_start: "2025-07-01",
  service_end: "2026-06-30",
  scheme: "gratuity",
  work_model: "full-time",
  regime: "ASSESSED",
  cohort: "ASSESSED",
  expected_benefit: "2100.00",
  paid_benefit: "999",
};
const evidence = [
  { id: "document", label: "Reviewed scope support", scan_status: "CLEAN" },
  { id: "bad", label: "Unclean support", scan_status: "INFECTED" },
];
function fill() {
  for (const [label, value] of [
    ["Gratuity expectation title", "Expected final gratuity"],
    ["Assessed employer registration", "ASSESSED-EMPLOYER"],
    ["Retained settlement scope and due-date evidence", "document"],
    ["Independent selected employee count", "1"],
    [
      "Employer, employee scope and due-date assessment",
      "Independently assessed service identities and retained due-date support",
    ],
  ])
    fireEvent.change(
      label === "Retained settlement scope and due-date evidence"
        ? screen.getByRole("combobox", { name: label })
        : screen.getByLabelText(label),
      { target: { value } },
    );
}
function select(id: string) {
  fireEvent.click(
    screen.getByRole("checkbox", { name: `Select gratuity ${id}` }),
  );
  expect(screen.getByLabelText(`Assessed due date for ${id}`)).toHaveValue("");
  fireEvent.change(screen.getByLabelText(`Assessed due date for ${id}`), {
    target: { value: "2026-07-14" },
  });
  fireEvent.change(
    screen.getByLabelText(`Due-date evidence reference for ${id}`),
    { target: { value: `SUPPORT-${id}` } },
  );
}

it("requires independent controls and explicit service selection without inferring due dates or paid cash", async () => {
  const created = vi.fn();
  state.mutate.mockResolvedValue({ id: "derived" });
  render(
    <BenefitSettlementSource
      eid="AE"
      resultId="reviewed"
      rows={[row]}
      evidence={evidence}
      onCreated={created}
    />,
  );
  const button = screen.getByRole("button", {
    name: "Prepare expected gratuity source",
  });
  expect(button).toBeDisabled();
  expect(
    screen.getByLabelText("Independent expected gratuity total (AED)"),
  ).toHaveValue("");
  expect(
    screen.queryByRole("option", { name: "Unclean support" }),
  ).not.toBeInTheDocument();
  fill();
  select("E1");
  expect(button).toBeDisabled();
  fireEvent.change(
    screen.getByLabelText("Independent expected gratuity total (AED)"),
    { target: { value: "2100" } },
  );
  fireEvent.change(
    screen.getByLabelText("Independent selected employee count"),
    { target: { value: "2" } },
  );
  expect(button).toBeDisabled();
  fireEvent.change(
    screen.getByLabelText("Independent selected employee count"),
    { target: { value: "1" } },
  );
  fireEvent.click(button);
  await waitFor(() => expect(created).toHaveBeenCalledWith("derived"));
  expect(state.mutate).toHaveBeenCalledWith({
    path: "intelligence/engagements/AE/benefit-settlement-source",
    body: {
      result_id: "reviewed",
      employer_registration: "ASSESSED-EMPLOYER",
      settlement_evidence_version_id: "document",
      selections: [
        {
          result_row_id: "E1",
          due_date: "2026-07-14",
          due_date_reference: "SUPPORT-E1",
        },
      ],
      expected_rows: 1,
      control_total: "2100",
      label: "Expected final gratuity",
      assessment:
        "Independently assessed service identities and retained due-date support",
    },
  });
});

it("keeps explicit selections across result pages without silently assuming whole-population coverage", async () => {
  state.mutate.mockResolvedValue({ id: "derived" });
  const props = {
    eid: "AE",
    resultId: "reviewed",
    evidence,
    onCreated: vi.fn(),
  };
  const { rerender } = render(
    <BenefitSettlementSource {...props} rows={[row]} />,
  );
  fill();
  select("E1");
  rerender(
    <BenefitSettlementSource
      {...props}
      rows={[
        {
          ...row,
          id: "E2",
          work_model: "part-time",
          expected_benefit: "1050.00",
        },
      ]}
    />,
  );
  select("E2");
  fireEvent.change(
    screen.getByLabelText("Independent selected employee count"),
    { target: { value: "2" } },
  );
  fireEvent.change(
    screen.getByLabelText("Independent expected gratuity total (AED)"),
    { target: { value: "3150" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare expected gratuity source" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(
    state.mutate.mock.calls[0][0].body.selections.map(
      (item: { result_row_id: string }) => item.result_row_id,
    ),
  ).toEqual(["E1", "E2"]);
  expect(screen.getByText(/Controls cover selected rows only/)).toBeVisible();
});

it("does not expose an undated legacy result as a selectable final settlement", () => {
  render(
    <BenefitSettlementSource
      eid="AE"
      resultId="old"
      rows={[{ id: "E1", expected_benefit: "2100" }]}
      evidence={evidence}
      onCreated={vi.fn()}
    />,
  );
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Prepare expected gratuity source" }),
  ).toBeDisabled();
  expect(
    screen.getByText(/Older results without service dates must be regenerated/),
  ).toBeVisible();
});

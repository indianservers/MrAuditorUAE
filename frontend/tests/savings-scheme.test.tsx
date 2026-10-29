import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import {
  SavingsContributionExpectations,
  SavingsEnrolmentDocument,
  SavingsFundReportedSource,
} from "@/features/savings-scheme";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => state.mutate.mockReset());
const evidence = [
  { id: "clean", label: "Retained assessment", scan_status: "CLEAN" },
  { id: "bad", label: "Quarantined", scan_status: "QUARANTINED" },
];
const first = { registration: "EMP", period: "2026-06", fund_id: "FUND-1" };
const second = { ...first, fund_id: "FUND-2" };
function fillGroup(fund: string, rows: string, total: string) {
  const name = `${fund} / EMP / 2026-06`;
  fireEvent.click(
    screen.getByRole("checkbox", { name: `Select savings group ${name}` }),
  );
  expect(
    screen.getByLabelText(`Independent participant count ${name}`),
  ).toHaveValue("");
  expect(
    screen.getByLabelText(`Independent expected total ${name}`),
  ).toHaveValue("");
  for (const [label, value] of [
    [`Independent participant count ${name}`, rows],
    [`Independent expected total ${name}`, total],
    [`Assessed due date ${name}`, "2026-07-15"],
    [`Due-date reference ${name}`, "SYN-ASSESSMENT"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

it("binds only clean retained enrolment documents and keeps registry limits visible", () => {
  const changed = vi.fn();
  render(
    <SavingsEnrolmentDocument
      value=""
      onChange={changed}
      evidence={evidence}
    />,
  );
  const field = screen.getByRole("combobox", {
    name: "Retained savings enrolment document (optional shared document)",
  });
  expect(field).toHaveValue("");
  expect(
    screen.queryByRole("option", { name: /Quarantined/ }),
  ).not.toBeInTheDocument();
  fireEvent.change(field, { target: { value: "clean" } });
  expect(changed).toHaveBeenCalledWith("clean");
  expect(
    screen.getByText(/does not verify a live fund registry/),
  ).toBeVisible();
});

it("preserves selected fund controls across result pages without pooling funds", async () => {
  state.mutate.mockResolvedValue({ id: "expected" });
  const created = vi.fn();
  const props = {
    eid: "eng",
    resultId: "result",
    evidence,
    onCreated: created,
  };
  const view = render(
    <SavingsContributionExpectations {...props} rows={[first]} />,
  );
  expect(screen.getByRole("button")).toBeDisabled();
  fillGroup("FUND-1", "3", "1166.00");
  view.rerender(<SavingsContributionExpectations {...props} rows={[second]} />);
  expect(
    screen.getByLabelText("Independent expected total FUND-1 / EMP / 2026-06"),
  ).toHaveValue("1166.00");
  fillGroup("FUND-2", "1", "249.90");
  for (const [label, value] of [
    ["Savings expectation title", "Expected basic contributions"],
    ["Retained savings remittance due-date evidence", "clean"],
    [
      "Savings remittance scope assessment",
      "Independent original fund-specific contributions and dates",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(created).toHaveBeenCalledWith("expected"));
  const posted = state.mutate.mock.calls[0][0];
  expect(posted.path).toBe(
    "intelligence/engagements/eng/contribution-obligation-source",
  );
  expect(posted.body.groups).toEqual([
    {
      ...first,
      component: "SAVINGS:EMPLOYER_BASIC",
      expected_rows: 3,
      amount: "1166.00",
      due_date: "2026-07-15",
      due_date_reference: "SYN-ASSESSMENT",
    },
    {
      ...second,
      component: "SAVINGS:EMPLOYER_BASIC",
      expected_rows: 1,
      amount: "249.90",
      due_date: "2026-07-15",
      due_date_reference: "SYN-ASSESSMENT",
    },
  ]);
  expect(posted.body).not.toHaveProperty("pension_scope");
});

it("never fills an independent fund-observation count or amount from a result", () => {
  render(
    <SavingsFundReportedSource
      eid="eng"
      sourceId="source"
      onCreated={vi.fn()}
    />,
  );
  expect(
    screen.getByLabelText("Independent original fund row count"),
  ).toHaveValue("");
  expect(
    screen.getByLabelText("Independent original fund contribution total (AED)"),
  ).toHaveValue("");
  expect(screen.getByRole("button")).toBeDisabled();
});

it("can request an explicitly controlled nil original population without manufacturing rows", async () => {
  state.mutate.mockResolvedValue({ id: "reported" });
  const created = vi.fn();
  render(
    <SavingsFundReportedSource
      eid="eng"
      sourceId="original-fund"
      onCreated={created}
    />,
  );
  for (const [label, value] of [
    ["Fund observation source title", "Original controlled fund observations"],
    ["Independent original fund row count", "0"],
    ["Independent original fund contribution total (AED)", "0.00"],
    [
      "Original fund population assessment",
      "Independent original nil fund population reviewed",
    ],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(created).toHaveBeenCalledWith("reported"));
  expect(state.mutate.mock.calls[0][0]).toEqual({
    path: "intelligence/engagements/eng/savings-reported-obligation-source",
    body: {
      source_id: "original-fund",
      expected_rows: 0,
      control_total: "0.00",
      label: "Original controlled fund observations",
      assessment: "Independent original nil fund population reviewed",
    },
  });
});

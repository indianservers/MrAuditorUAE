import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ContributionObligationSource } from "@/features/contribution-obligation-source";

const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => {
  state.mutate.mockReset();
});
const controls = [
  {
    registration: "REG",
    period: "2026-06",
    component: "PF:EMPLOYEE",
    expected_rows: 1,
    amount: "1800",
    due_date: "2026-07-15",
    due_date_reference: "SYNTHETIC-DATE",
  },
];

function fill() {
  fireEvent.change(screen.getByLabelText("Expected remittance source title"), {
    target: { value: "Reviewed PF remittances" },
  });
  fireEvent.change(
    screen.getByLabelText("Retained due-date evidence version"),
    { target: { value: "evidence" } },
  );
  fireEvent.change(
    screen.getByLabelText("Remittance scope and due-date assessment"),
    {
      target: {
        value:
          "Independent count, amount and statutory-date reference assessment",
      },
    },
  );
}

it("sends independent controls and the exact reviewed parent without pension scope for India", async () => {
  const created = vi.fn();
  state.mutate.mockResolvedValue({ id: "derived" });
  render(
    <ContributionObligationSource
      eid="india"
      resultId="approved-result"
      pension={false}
      evidence={[]}
      onCreated={created}
    />,
  );
  fill();
  fireEvent.change(
    screen.getByLabelText("Independent contribution group controls (JSON)"),
    { target: { value: JSON.stringify(controls) } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare expected remittance source" }),
  );
  await waitFor(() => expect(created).toHaveBeenCalledWith("derived"));
  expect(state.mutate.mock.calls[0][0]).toMatchObject({
    path: "intelligence/engagements/india/contribution-obligation-source",
    body: {
      result_id: "approved-result",
      due_date_evidence_version_id: "evidence",
      groups: controls,
      pension_scope: null,
    },
  });
});

it("leaves independent amounts blank in the format and rejects malformed controls", async () => {
  render(
    <ContributionObligationSource
      eid="uae"
      resultId="parent"
      pension
      evidence={[]}
      onCreated={vi.fn()}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Show contribution control format" }),
  );
  const value = JSON.parse(
    (
      screen.getByLabelText(
        "Independent contribution group controls (JSON)",
      ) as HTMLTextAreaElement
    ).value,
  );
  expect(value[0].amount).toBeNull();
  expect(value[0].expected_rows).toBeNull();
  expect(
    screen.getByText(/Government pension support is a separate payer/),
  ).toBeVisible();
  fill();
  fireEvent.change(
    screen.getByLabelText("Independent contribution group controls (JSON)"),
    { target: { value: "{}" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare expected remittance source" }),
  );
  await waitFor(() =>
    expect(screen.getByText(/one to one thousand independent/)).toBeVisible(),
  );
  expect(state.mutate).not.toHaveBeenCalled();
});

it("retains explicit pension scope and never infers due dates", async () => {
  state.mutate.mockResolvedValue({ id: "derived" });
  render(
    <ContributionObligationSource
      eid="uae"
      resultId="parent"
      pension
      evidence={[]}
      onCreated={vi.fn()}
    />,
  );
  fill();
  const scope = {
    authority: "EXPLICIT-AUTHORITY",
    scheme: "EXPLICIT-SCHEME",
    membership_cohort: "CONTINUING",
    pension_country: "AE",
    nationality: "AE",
    employment_sector: "private",
    jurisdiction: "AE-DU",
  };
  fireEvent.change(screen.getByLabelText("Assessed pension scope (JSON)"), {
    target: { value: JSON.stringify(scope) },
  });
  fireEvent.change(
    screen.getByLabelText("Independent contribution group controls (JSON)"),
    { target: { value: JSON.stringify(controls) } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare expected remittance source" }),
  );
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  expect(state.mutate.mock.calls[0][0].body.pension_scope).toEqual(scope);
  expect(state.mutate.mock.calls[0][0].body.groups[0].due_date).toBe(
    "2026-07-15",
  );
});

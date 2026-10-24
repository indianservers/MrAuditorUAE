import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Paper } from "@/features/grc-forms";

const mock = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({ mutate: mock.mutate, isPending: false }),
}));
import { ComplianceFiling } from "@/features/compliance-filing";

const paper: Paper = {
  kind: "grc-obligation",
  id: "record",
  version: 7,
  reference: "SYN-FILING",
  title: "Synthetic obligation",
  status: "APPROVED",
  body: { filing_stage: "approved_for_submission", deadline: null },
};
beforeEach(() => mock.mutate.mockClear());

it("requires actual submission evidence and retains the scoped version", () => {
  render(<ComplianceFiling base="grc/engagements/scoped" paper={paper} />);
  expect(screen.getByText(/Deadline: Unresolved/)).toBeVisible();
  const button = screen.getByRole("button", {
    name: "Record evidenced filing stage",
  });
  expect(button).toBeDisabled();
  const id = "11111111-1111-4111-8111-111111111111";
  fireEvent.change(
    screen.getByLabelText("Actual submission evidence record ID"),
    { target: { value: id } },
  );
  fireEvent.click(button);
  expect(mock.mutate).toHaveBeenCalledWith({
    path: "grc/engagements/scoped/obligations/record/filing-stage",
    body: { version: 7, stage: "submitted", submission_evidence_id: id },
  });
});

it("keeps acknowledgment evidence separate from a submission", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, body: { filing_stage: "submitted" } }}
    />,
  );
  expect(
    screen.getByLabelText("Separate acknowledgment evidence record ID"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

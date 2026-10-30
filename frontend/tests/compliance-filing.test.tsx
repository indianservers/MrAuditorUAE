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

it("returns an approved filing to preparing without replacing retained receipts", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "acknowledged",
          jurisdiction: "AE",
          submission_evidence_id: "saved-submission",
          acknowledgment_evidence_id: "saved-ack",
        },
      }}
    />,
  );
  expect(screen.getByText(/Jurisdiction: AE/)).toBeVisible();
  expect(screen.getByText("saved-submission")).toBeVisible();
  expect(screen.getByText("saved-ack")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  );
  expect(mock.mutate).toHaveBeenCalledWith({
    path: "grc/engagements/scoped/obligations/record/filing-stage",
    body: { version: 7, stage: "preparing" },
  });
});

it("requires reopening locked records and does not offer an enabled transition", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, status: "LOCKED" }}
    />,
  );
  expect(screen.getByText(/Reopen the locked record/)).toBeVisible();
  expect(screen.getByLabelText("Next filing stage")).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("rejects a 36-character non-UUID receipt", () => {
  render(<ComplianceFiling base="grc/engagements/scoped" paper={paper} />);
  fireEvent.change(
    screen.getByLabelText("Actual submission evidence record ID"),
    { target: { value: "-".repeat(36) } },
  );
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("requires the stage-specific permission for approval and management", () => {
  const { rerender } = render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{ ...paper, body: { filing_stage: "under_review" } }}
      canApprove={false}
      canManage
    />,
  );
  expect(screen.getByText(/filing approval permission/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeEnabled();
  rerender(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={paper}
      canApprove
      canManage={false}
    />,
  );
  expect(screen.getByText(/filing management permission/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
});

it("keeps entity country and foreign obligation country distinct and blocks unassessed filing approval", () => {
  render(
    <ComplianceFiling
      base="grc/engagements/scoped"
      paper={{
        ...paper,
        body: {
          filing_stage: "under_review",
          jurisdiction: "IN",
          jurisdiction_scope: {
            entity_country: "AE",
            obligation_country: "IN",
            relationship: "foreign",
            applicability: "potential",
          },
        },
      }}
    />,
  );
  expect(screen.getByText(/Declared entity country: AE/)).toHaveTextContent(
    "Obligation country: IN",
  );
  expect(screen.getByText(/Assess country applicability/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Next filing stage"), {
    target: { value: "preparing" },
  });
  expect(
    screen.getByRole("button", { name: "Record evidenced filing stage" }),
  ).toBeEnabled();
});

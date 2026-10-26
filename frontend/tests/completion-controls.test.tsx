import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CompletionControls } from "@/features/completion-controls";

it("shows stale approvals as outstanding and links the records for reassessment", () => {
  render(
    <CompletionControls
      eid="E"
      ready={false}
      checks={[
        {
          code: "reviewed_source_freshness",
          passed: false,
          description:
            "Current sources for every approved or locked audit record",
          checked_records: 12,
          source_issues: [
            { record_id: "P1", kind: "working-papers", freshness: "STALE" },
          ],
        },
      ]}
    />,
  );
  expect(screen.getByText("outstanding")).toBeInTheDocument();
  expect(screen.getByText(/12 approved or locked/)).toBeInTheDocument();
  fireEvent.click(
    screen.getByText("Reviewed records needing source reassessment (1)"),
  );
  expect(
    screen.getByRole("link", { name: "working-papers · P1" }),
  ).toHaveAttribute("href", "/engagements/E/working-papers?record=P1");
  expect(
    screen.getByText(/Historical approval is retained/),
  ).toBeInTheDocument();
});

it("makes every affected record available beyond the first 25", () => {
  render(
    <CompletionControls
      eid="E"
      checks={[
        {
          code: "reviewed_source_freshness",
          passed: false,
          source_issues: Array.from({ length: 31 }, (_, i) => ({
            record_id: `P${i}`,
            kind: "testing",
            freshness: "STALE",
          })),
        },
      ]}
    />,
  );
  fireEvent.click(
    screen.getByText("Reviewed records needing source reassessment (31)"),
  );
  expect(
    screen.queryByRole("link", { name: "testing · P30" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Show more affected records" }),
  );
  expect(
    screen.getByRole("link", { name: "testing · P30" }),
  ).toBeInTheDocument();
});

it("preserves a current ready state without presenting source issues", () => {
  render(
    <CompletionControls
      eid="E"
      ready
      checks={[
        {
          code: "reviewed_source_freshness",
          passed: true,
          checked_records: 12,
          source_issues: [],
        },
      ]}
    />,
  );
  expect(screen.getByText("ready")).toBeInTheDocument();
  expect(
    screen.queryByText(/needing source reassessment/),
  ).not.toBeInTheDocument();
});

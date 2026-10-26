import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScreeningCandidates } from "@/features/screening-candidates";

const subject = (id: string, count: number) => ({
  id,
  subject_name: "شركة اختبار SYNTHETIC",
  subject_evidence_reference: "SYN-SUBJECT-REF",
  candidate_count: count,
  candidate_preview_truncated: false,
  candidates: Array.from({ length: count }, (_, index) => ({
    source_id: `${id}-ENTRY-${index}`,
    list_subject_id: `PERSON-${index}`,
    list_name: "SYNTHETIC CANDIDATE",
    list_version: "SYN-LIST-1",
    published_on: "2026-06-29",
    evidence_reference: `REF-${index}`,
    name_similarity: 1,
  })),
});

describe("complete screening candidate review", () => {
  it("pages candidates beyond 20 and 100, resets on subject change, and preserves context", () => {
    render(
      <ScreeningCandidates
        rows={[subject("SUBJECT-1", 121), subject("SUBJECT-2", 1)]}
      />,
    );
    const table = screen.getByRole("table", {
      name: "Name-screening candidates",
    });
    expect(within(table).getAllByRole("row")).toHaveLength(101);
    expect(screen.getByText("Candidates 1–100 of 121")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next candidates" }));
    expect(screen.getByText("Candidates 101–121 of 121")).toBeInTheDocument();
    expect(
      within(table).getByRole("cell", {
        name: "SUBJECT-1-ENTRY-120",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next candidates" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Previous candidates" }),
    );
    expect(screen.getByText("Candidates 1–100 of 121")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next candidates" }));
    fireEvent.change(screen.getByLabelText("Screening subject"), {
      target: { value: "1" },
    });
    expect(screen.getByText("Candidates 1–1 of 1")).toBeInTheDocument();
    expect(within(table).getByText("SUBJECT-2-ENTRY-0")).toBeInTheDocument();
    expect(
      screen.getByText(/Subject evidence reference: SYN-SUBJECT-REF/),
    ).toBeInTheDocument();
  });

  it.each([true, false])(
    "warns on incomplete historical results (flag %s) and does not label zero hits as cleared",
    (truncatedFlag) => {
      render(
        <ScreeningCandidates
          rows={[
            {
              ...subject("LEGACY", 20),
              candidate_count: 121,
              candidate_preview_truncated: truncatedFlag,
            },
            subject("NO-HITS", 0),
          ]}
        />,
      );
      expect(screen.getByRole("alert")).toHaveTextContent("only 20 of 121");
      fireEvent.change(screen.getByLabelText("Screening subject"), {
        target: { value: "1" },
      });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(
        screen.getByText(
          "No retained candidates. This does not clear the subject.",
        ),
      ).toBeInTheDocument();
    },
  );
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  buildUNSnapshot,
  EMPTY_UN_SNAPSHOT,
  UNSanctionsSource,
} from "@/features/un-sanctions-source";
import { ScreeningCandidates } from "@/features/screening-candidates";

const draft = {
  ...EMPTY_UN_SNAPSHOT,
  generated_at: "2026-06-29T23:00:00Z",
  assessment: "Independent synthetic population assessment",
  individuals: "1",
  entities: "1",
  original_script_names: "1",
  individual_alias_names: "2",
  entity_alias_names: "1",
  empty_alias_records: "2",
};

describe("controlled UN XML source", () => {
  it("requires explicit independent controls including literal zero; empty aliases are not name rows", () => {
    expect(buildUNSnapshot(draft, "6")).toMatchObject({
      individuals: 1,
      empty_alias_records: 2,
    });
    expect(() => buildUNSnapshot({ ...draft, individuals: "" }, "6")).toThrow(
      "whole-number",
    );
    expect(() => buildUNSnapshot({ ...draft, entities: "1.2" }, "6")).toThrow(
      "whole-number",
    );
    expect(() =>
      buildUNSnapshot({ ...draft, empty_alias_records: "-1" }, "6"),
    ).toThrow("whole-number");
    expect(() => buildUNSnapshot(draft, "8")).toThrow("Expanded UN name rows");
    expect(() =>
      buildUNSnapshot({ ...draft, generated_at: "2026-06-29T23:00:00" }, "6"),
    ).toThrow("timezone");
    expect(() =>
      buildUNSnapshot({ ...draft, assessment: "    " }, "6"),
    ).toThrow("assessment");
  });
  it("renders labelled controls, retains entered draft and explains population and clearance limits", () => {
    const change = vi.fn();
    render(<UNSanctionsSource value={draft} onChange={change} />);
    fireEvent.change(screen.getByLabelText("UN entities"), {
      target: { value: "0" },
    });
    expect(change).toHaveBeenCalledWith({ ...draft, entities: "0" });
    expect(
      screen.getByText(/Expected source rows must equal/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not identity clearance/)).toBeInTheDocument();
  });
  it("shows low-quality source observations and original permanent reference during adjudication", () => {
    render(
      <ScreeningCandidates
        rows={[
          {
            id: "S1",
            candidates: [
              {
                source_id: "A1",
                native_reference_number: "ZZi.001",
                native_alias_quality: "Low",
                native_name_origin: "individual-alias",
              },
            ],
          },
        ]}
      />,
    );
    expect(screen.getByText("ZZi.001")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(
      screen.getByText(/Low-quality aliases alone are insufficient/),
    ).toBeInTheDocument();
  });
  it("distinguishes documented observations from an identity disposition", () => {
    render(
      <ScreeningCandidates
        rows={[
          {
            id: "S1",
            reviewer_disposition: "OBSERVATIONS_DOCUMENTED",
            candidates: [],
          },
        ]}
      />,
    );
    expect(
      screen.getByText(/Observation assessment documented/),
    ).toHaveTextContent("do not establish positive identification");
  });
});

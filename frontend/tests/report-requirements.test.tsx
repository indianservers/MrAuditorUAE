import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ReportRequirementsEditor,
  ReportRequirementSelector,
  type ReportRequirement,
} from "@/features/report-requirements";

function setup(count = 65, locked = true) {
  const initial: ReportRequirement[] = Array.from(
    { length: count },
    (_, i) => ({
      key: `form26.item.${i + 1}`,
      title: `Source item ${i + 1}`,
      disposition: "UNASSESSED",
      source_required: true,
      basis: `Retained evidence assessment ${i + 1}`,
    }),
  );
  const save = vi.fn();
  function Harness() {
    const [items, setItems] = useState(initial);
    return (
      <>
        <ReportRequirementsEditor
          items={items}
          assessed={false}
          basis="Engagement scope assessment"
          onItems={setItems}
          onAssessed={() => {}}
          onBasis={() => {}}
          locked={locked}
          allowNotApplicable
          notApplicableKeys={["form26.item.65"]}
        />
        <button onClick={() => save(items)}>Save complete scope</button>
      </>
    );
  }
  render(<Harness />);
  return { initial, save };
}

describe("report requirement navigation", () => {
  it("edits later pages without losing hidden requirements or unlocking source guards", () => {
    const { initial, save } = setup();
    expect(
      screen.queryByLabelText("Requirement reference 21"),
    ).not.toBeInTheDocument();
    for (let i = 0; i < 3; i++)
      fireEvent.click(
        screen.getByRole("button", { name: "Next requirements" }),
      );
    expect(
      screen.getByRole("button", { name: "Next requirements" }),
    ).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText("Applicability and source basis 65"),
      { target: { value: "Reviewed final source evidence" } },
    );
    fireEvent.change(screen.getByLabelText("Requirement disposition 65"), {
      target: { value: "NOT_APPLICABLE" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save complete scope" }),
    );
    const saved = save.mock.calls[0][0];
    expect(saved).toHaveLength(65);
    expect(saved.slice(0, 64)).toEqual(initial.slice(0, 64));
    expect(saved[64]).toEqual({
      ...initial[64],
      disposition: "NOT_APPLICABLE",
      basis: "Reviewed final source evidence",
    });
    expect(screen.getByLabelText("Requirement reference 65")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Remove requirement 65" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Previous requirements" }),
    );
    expect(
      within(screen.getByLabelText("Requirement disposition 41")).getByRole(
        "option",
        { name: "Not applicable with reviewed basis" },
      ),
    ).toBeDisabled();
  });

  it("combines key, title and basis search with assessment filters and saves the whole scope", () => {
    const { save } = setup();
    fireEvent.change(screen.getByLabelText("Search report requirements"), {
      target: { value: "FORM26.ITEM.65" },
    });
    fireEvent.change(screen.getByLabelText("Requirement disposition 65"), {
      target: { value: "REQUIRED" },
    });
    fireEvent.change(screen.getByLabelText("Filter requirement assessment"), {
      target: { value: "UNASSESSED" },
    });
    expect(
      screen.getByText("No requirements match these filters."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter requirement assessment"), {
      target: { value: "REQUIRED" },
    });
    for (const query of ["Source item 65", "Retained evidence assessment 65"]) {
      fireEvent.change(screen.getByLabelText("Search report requirements"), {
        target: { value: query },
      });
      expect(
        screen.getByLabelText("Requirement reference 65"),
      ).toBeInTheDocument();
    }
    fireEvent.click(
      screen.getByRole("button", { name: "Save complete scope" }),
    );
    expect(save.mock.calls[0][0]).toHaveLength(65);
    expect(save.mock.calls[0][0][64].disposition).toBe("REQUIRED");
  });

  it("clamps the last page after deletion", () => {
    setup(21, false);
    fireEvent.click(screen.getByRole("button", { name: "Next requirements" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Remove requirement 21" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "20 of 20 requirements match. Page 1 of 1.",
    );
    expect(
      screen.getByLabelText("Requirement reference 1"),
    ).toBeInTheDocument();
  });
  it("reveals a newly added requirement after clearing active filters", () => {
    const { save } = setup(20, false);
    fireEvent.change(screen.getByLabelText("Search report requirements"), {
      target: { value: "does not match" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Add declared requirement" }),
    );
    expect(screen.getByLabelText("Search report requirements")).toHaveValue("");
    expect(screen.getByLabelText("Requirement reference 21")).toHaveValue(
      "item-1",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save complete scope" }),
    );
    expect(save.mock.calls[0][0]).toHaveLength(21);
  });
});

it("preserves hidden block selections and enforces the 100-item block limit", () => {
  const items = Array.from({ length: 877 }, (_, i) => ({
    key: `field.${i + 1}`,
    title: `Source field ${i + 1}`,
  }));
  function Selector() {
    const [selected, setSelected] = useState(
      items.slice(0, 100).map((item) => item.key),
    );
    return (
      <>
        <ReportRequirementSelector
          items={items}
          selected={selected}
          onChange={setSelected}
          label="Synthetic block coverage"
        />
        <output data-testid="selected-keys">{JSON.stringify(selected)}</output>
      </>
    );
  }
  render(<Selector />);
  fireEvent.change(screen.getByLabelText("Search Synthetic block coverage"), {
    target: { value: "field.877" },
  });
  expect(screen.getByLabelText("Source field 877")).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Search Synthetic block coverage"), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByLabelText("Source field 1"));
  fireEvent.change(screen.getByLabelText("Search Synthetic block coverage"), {
    target: { value: "field.877" },
  });
  fireEvent.click(screen.getByLabelText("Source field 877"));
  const selected = JSON.parse(screen.getByTestId("selected-keys").textContent!);
  expect(selected).toEqual([
    ...items.slice(1, 100).map((item) => item.key),
    "field.877",
  ]);
});

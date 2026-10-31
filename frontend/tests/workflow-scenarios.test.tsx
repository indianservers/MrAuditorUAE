import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  WorkflowScenarios,
  type ReferenceScenario,
} from "@/features/workflow-scenarios";

const scenarios: ReferenceScenario[] = [
  {
    id: "RW-A",
    title: "Assessed management scope",
    country: "AE",
    workflow: "controls",
    expected: { blocked: false, exceptions: 0 },
  },
  {
    id: "RW-B",
    title: "Assessed auditor scope",
    country: "IN",
    workflow: "controls",
    expected: { blocked: true, exceptions: 1 },
  },
  {
    id: "RW-C",
    title: "Ambiguous bank receipt",
    country: "AE",
    workflow: "bank",
    expected: { state: "UNRESOLVED" },
  },
];
const workflowTitles = {
  controls: "Control scope review",
  bank: "Bank reconciliation",
};

function props(country = "AE", workflow = "controls") {
  return { scenarios, country, workflow, workflowTitles };
}

describe("Country-labelled synthetic reference scenarios", () => {
  it("defaults to the engagement country and selected workflow, retaining expected outcomes", () => {
    const original = JSON.stringify(scenarios);
    render(<WorkflowScenarios {...props()} />);
    const list = screen.getByRole("list", {
      name: "Reference scenarios",
      hidden: true,
    });
    expect(
      within(list).getAllByRole("listitem", { hidden: true }),
    ).toHaveLength(1);
    expect(
      within(list).getByText("RW-A · Assessed management scope"),
    ).toBeInTheDocument();
    expect(
      within(list).queryByText(/Assessed auditor scope/),
    ).not.toBeInTheDocument();
    expect(
      within(list).getByText("UAE · Control scope review"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("1 of 3 reference scenarios shown"),
    ).toBeInTheDocument();
    expect(screen.getByText(/"blocked": false/)).toHaveTextContent(
      '"exceptions": 0',
    );
    expect(JSON.stringify(scenarios)).toBe(original);
  });

  it("can browse every country and workflow and search by case ID or country and workflow title", () => {
    render(<WorkflowScenarios {...props()} />);
    fireEvent.change(screen.getByLabelText("Reference scenario countries"), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByLabelText("Reference scenario workflows"), {
      target: { value: "all" },
    });
    expect(
      screen.getByText("3 of 3 reference scenarios shown"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search reference scenarios"), {
      target: { value: "india control scope" },
    });
    expect(
      screen.getByText("1 of 3 reference scenarios shown"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("RW-B · Assessed auditor scope"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("India · Control scope review"),
    ).toBeInTheDocument();
    expect(screen.getByText(/"blocked": true/)).toHaveTextContent(
      '"exceptions": 1',
    );
    fireEvent.change(screen.getByLabelText("Search reference scenarios"), {
      target: { value: "rw-c" },
    });
    expect(
      screen.getByText("RW-C · Ambiguous bank receipt"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not change this engagement or its rules/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search reference scenarios"), {
      target: { value: "absent" },
    });
    expect(
      screen.getByText("0 of 3 reference scenarios shown"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not establish a nil business population/),
    ).toBeInTheDocument();
  });

  it("follows engagement and selected workflow changes without retaining another country's default list", () => {
    const view = render(<WorkflowScenarios {...props()} />);
    view.rerender(<WorkflowScenarios {...props("IN")} />);
    expect(
      screen.getByText("RW-B · Assessed auditor scope"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("RW-A · Assessed management scope"),
    ).not.toBeInTheDocument();
    view.rerender(<WorkflowScenarios {...props("AE", "bank")} />);
    expect(
      screen.getByText("RW-C · Ambiguous bank receipt"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("RW-B · Assessed auditor scope"),
    ).not.toBeInTheDocument();
  });
});

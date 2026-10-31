import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ReportingRecordSelect } from "@/features/reporting-record-select";

const mock = vi.hoisted(() => ({ useAPI: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({ useAPI: mock.useAPI }));

function Harness() {
  const [profile, setProfile] = useState("");
  const [record, setRecord] = useState("");
  const [run, setRun] = useState("");
  return (
    <>
      <ReportingRecordSelect
        path="profiles"
        label="Reporting profile"
        value={profile}
        onChange={setProfile}
      />
      <ReportingRecordSelect
        path="records"
        label="Approved assumptions"
        value={record}
        onChange={setRecord}
      />
      <ReportingRecordSelect
        path="runs"
        label="Immutable version"
        value={run}
        onChange={setRun}
        runs
      />
    </>
  );
}

beforeEach(() => {
  mock.useAPI.mockImplementation((path: string) => {
    const [resource, params] = path.split("?");
    const offset = Number(new URLSearchParams(params).get("offset"));
    const rows = Array.from({ length: 151 }, (_, i) => ({
      id: `${resource}-${i + 1}`,
      reference: `${resource} record ${i + 1}`,
      status: "APPROVED",
      kind: `inventory-${i + 1}`,
    }));
    return {
      data: {
        items: rows.slice(offset, offset + 50),
        total: rows.length,
        offset,
        limit: 50,
      },
      isLoading: false,
      error: null,
    };
  });
});

it("reaches all 151 profiles, assumptions and immutable versions with independent paging and retained selection", () => {
  render(<Harness />);
  for (const label of [
    "Reporting profile",
    "Approved assumptions",
    "Immutable version",
  ])
    for (let i = 0; i < 3; i++)
      fireEvent.click(
        screen.getByRole("button", { name: `Next ${label.toLowerCase()}` }),
      );
  for (const [label, resource] of [
    ["Reporting profile", "profiles"],
    ["Approved assumptions", "records"],
    ["Immutable version", "runs"],
  ]) {
    fireEvent.change(screen.getByLabelText(label), {
      target: { value: `${resource}-151` },
    });
    expect(
      screen.getByRole("button", { name: `Next ${label.toLowerCase()}` }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: `Previous ${label.toLowerCase()}` }),
    );
    expect(screen.getByLabelText(label)).toHaveValue(`${resource}-151`);
    expect(
      within(screen.getByLabelText(label)).getByRole("option", {
        selected: true,
      }),
    ).toHaveTextContent("selected");
    expect(screen.getByLabelText(`${label} pages`)).toHaveTextContent(
      "101–150 of 151",
    );
  }
  fireEvent.click(
    screen.getByRole("button", { name: "Previous reporting profile" }),
  );
  expect(screen.getByLabelText("Reporting profile pages")).toHaveTextContent(
    "51–100 of 151",
  );
  expect(screen.getByLabelText("Approved assumptions pages")).toHaveTextContent(
    "101–150 of 151",
  );
  expect(screen.getByLabelText("Immutable version pages")).toHaveTextContent(
    "101–150 of 151",
  );
});

it("preserves a newly generated selected run outside the current page without choosing another run", () => {
  const onChange = vi.fn();
  render(
    <ReportingRecordSelect
      path="runs"
      label="Immutable version"
      value="NEW-RUN-ID"
      onChange={onChange}
      runs
    />,
  );
  expect(screen.getByLabelText("Immutable version")).toHaveValue("NEW-RUN-ID");
  expect(
    screen.getByRole("option", { name: "NEW-RUN-ID · selected" }),
  ).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

it("keeps an unavailable page visible as an error and never clears the retained ID", () => {
  mock.useAPI.mockReturnValue({
    data: undefined,
    error: new Error("Source unavailable"),
    isLoading: false,
  });
  const onChange = vi.fn();
  render(
    <ReportingRecordSelect
      path="records"
      label="Approved assumptions"
      value="SELECTED"
      onChange={onChange}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Source unavailable");
  expect(screen.getByLabelText("Approved assumptions pages")).toHaveTextContent(
    "Records unavailable",
  );
  expect(
    screen.getByRole("button", { name: "Next approved assumptions" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("SELECTED");
  expect(onChange).not.toHaveBeenCalled();
});

it("does not advance while a page is loading or infer a selected record", () => {
  mock.useAPI.mockReturnValue({
    data: undefined,
    error: null,
    isLoading: true,
  });
  const onChange = vi.fn();
  render(
    <ReportingRecordSelect
      path="records"
      label="Approved assumptions"
      value=""
      onChange={onChange}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Next approved assumptions" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("");
  expect(onChange).not.toHaveBeenCalled();
});

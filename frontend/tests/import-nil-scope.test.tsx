import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, it, expect } from "vitest";
import {
  ImportNilScopeForm,
  type ImportNilDraft,
} from "@/features/import-nil-scope";

function Form() {
  const [value, setValue] = useState<ImportNilDraft | null>(null);
  return (
    <>
      <ImportNilScopeForm
        value={value}
        onChange={setValue}
        evidence={[
          {
            id: "clean",
            label: "Independent nil assessment",
            scan_status: "CLEAN",
            sha256: "a".repeat(64),
          },
          {
            id: "bad",
            label: "Quarantined file",
            scan_status: "INFECTED",
            sha256: "b".repeat(64),
          },
        ]}
      />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  );
}

describe("explicit nil imports", () => {
  it("starts disabled without silently declaring either box nil", () => {
    render(<Form />);
    expect(screen.getByTestId("value")).toHaveTextContent("null");
    expect(screen.queryByLabelText("Nil import TRN")).not.toBeInTheDocument();
  });
  it("requires separate kind choices and binds the selected clean document hash", () => {
    render(<Form />);
    fireEvent.click(
      screen.getByLabelText("Declare an evidenced nil import population"),
    );
    expect(
      screen.getByLabelText("Box 6 declarations are nil"),
    ).not.toBeChecked();
    expect(
      screen.getByLabelText("Box 7 adjustments are nil"),
    ).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("Box 7 adjustments are nil"));
    fireEvent.change(screen.getByLabelText("Nil import supporting evidence"), {
      target: { value: "clean" },
    });
    const data = JSON.parse(screen.getByTestId("value").textContent!);
    expect(data.kinds).toEqual(["adjustment"]);
    expect(data.context_sha256).toBe("a".repeat(64));
    expect(
      screen.queryByRole("option", { name: "Quarantined file" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByLabelText("Declare an evidenced nil import population"),
    );
    expect(screen.getByTestId("value")).toHaveTextContent("null");
  });
});

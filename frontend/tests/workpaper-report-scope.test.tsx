import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { WorkpaperReportScopeEditor } from "@/features/workpaper-report-scope";

const data = vi.hoisted(() => ({ available: true }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: (path: string) => ({
    data: {
      items: path.endsWith("report-presets")
        ? data.available
          ? [
              {
                id: "india-form26-index:A/1",
                title: "Form 26 report part A",
                kind: "form26-index",
                not_applicable_keys: [],
                requirements: [
                  { key: "form26.C.1", title: "Identity particulars" },
                ],
              },
            ]
          : []
        : [
            {
              kind: "record",
              id: "protected",
              label: "Protected retained evidence",
            },
            {
              kind: "record",
              id: "not-linked",
              label: "Not in this workpaper",
            },
          ],
    },
  }),
}));

function Editor() {
  const [value, setValue] = useState<unknown>(null);
  return (
    <>
      <WorkpaperReportScopeEditor
        base="engagements/eng/audit"
        value={value}
        onChange={setValue}
        sections={[
          {
            heading: "Identity procedures",
            text: "Substantive synthetic source and procedure assessment",
          },
        ]}
        sources={[{ kind: "record", id: "protected" }]}
      />
      <output data-testid="saved">{JSON.stringify(value)}</output>
    </>
  );
}

describe("Workpaper report item declarations", () => {
  it("requires deliberate preset, section, protected support and assessment before adding an item", () => {
    data.available = true;
    render(<Editor />);
    fireEvent.change(screen.getByLabelText("Declare Form 26 item coverage"), {
      target: { value: "yes" },
    });
    expect(screen.getByLabelText("Workpaper report preset")).toHaveValue("");
    const add = screen.getByRole("button", {
      name: "Add declared item mappings",
    });
    expect(add).toBeDisabled();
    for (const [name, value] of [
      ["Workpaper report preset", "india-form26-index:A/1"],
      ["Workpaper report period start", "2026-04-01"],
      ["Workpaper report period end", "2027-03-31"],
      ["Supporting workpaper section", "0"],
      [
        "Item support and applicability assessment",
        "Synthetic identity support independently assessed",
      ],
    ])
      fireEvent.change(screen.getByLabelText(name), { target: { value } });
    const keys = screen.getByLabelText(
      "Report items supported by this section",
    ) as HTMLSelectElement;
    keys.options[0].selected = true;
    fireEvent.change(keys);
    const refs = screen.getByLabelText(
      "Existing protected supporting sources",
    ) as HTMLSelectElement;
    expect(refs.options).toHaveLength(1);
    expect(refs.options[0].textContent).toBe("Protected retained evidence");
    refs.options[0].selected = true;
    fireEvent.change(refs);
    expect(add).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Workpaper item applicability"), {
      target: { value: "NOT_APPLICABLE" },
    });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Workpaper item applicability"), {
      target: { value: "REQUIRED" },
    });
    fireEvent.click(add);
    expect(JSON.parse(screen.getByTestId("saved").textContent!).items).toEqual([
      {
        key: "form26.C.1",
        disposition: "REQUIRED",
        section_index: 0,
        supporting_sources: [{ kind: "record", id: "protected" }],
        assessment: "Synthetic identity support independently assessed",
      },
    ]);
    fireEvent.click(
      screen.getByRole("button", { name: "Remove item mapping" }),
    );
    expect(
      JSON.parse(screen.getByTestId("saved").textContent!).items,
    ).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Declare Form 26 item coverage"), {
      target: { value: "no" },
    });
    expect(screen.getByTestId("saved")).toHaveTextContent("null");
  });
  it("hides the optional declaration when the country has no compatible preset", () => {
    data.available = false;
    render(<Editor />);
    expect(
      screen.queryByText("Declare Form 26 item coverage"),
    ).not.toBeInTheDocument();
  });
});

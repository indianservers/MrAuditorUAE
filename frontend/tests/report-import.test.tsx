import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ mutate: vi.fn(), inspect: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useCurrency: () => "AED",
  usePopulation: () => ({ committed: [] }),
  useAction: () => ({
    mutate: mocks.mutate,
    mutateAsync: mocks.inspect,
    isPending: false,
  }),
  useAPI: (path: string) => ({
    data:
      path === "connectors/catalogue"
        ? {
            items: [
              { id: "netsuite", name: "Oracle NetSuite" },
              { id: "busy", name: "Busy Accounting" },
            ],
          }
        : {
            report_columns: {
              coa: ["account_code"],
              tb: ["account_code"],
              gl: ["account_code"],
            },
          },
  }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: () => ({ client: "client", entity: "entity", period: "period" }),
}));
import { ReportPackageWizard } from "@/features/report-import";

describe("accounting report-set import", () => {
  beforeEach(() => {
    mocks.mutate.mockClear();
    mocks.inspect.mockResolvedValue({
      headers: ["account_code"],
      sheets: [],
      selected_sheet: "",
    });
  });

  it("requires all three reports and retains the selected accounting provider", async () => {
    render(
      <ReportPackageWizard
        provider="netsuite"
        renderBatch={(id) => <p>{id}</p>}
      />,
    );
    const submit = screen.getByRole("button", {
      name: "Reconcile reports and create import batches",
    });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Accounting system"), {
      target: { value: "busy" },
    });
    for (const label of [
      "Chart of accounts",
      "Trial balance",
      "General ledger",
    ]) {
      fireEvent.change(screen.getByLabelText(label + " file"), {
        target: {
          files: [
            new File(["account_code\n100"], label + ".csv", {
              type: "text/csv",
            }),
          ],
        },
      });
      await waitFor(() =>
        expect(screen.getByLabelText(label + " file")).not.toBeDisabled(),
      );
    }
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    const request = mocks.mutate.mock.calls[0][0];
    expect(request.path).toBe("connectors/report-packages");
    expect(JSON.parse(request.body.get("options"))).toMatchObject({
      source_system: "busy",
      currency: "AED",
    });
    expect(request.body.get("gl")).toBeInstanceOf(File);
    expect(request.body.get("tb")).toBeInstanceOf(File);
    expect(request.body.get("coa")).toBeInstanceOf(File);
  });

  it("rejects multi-sheet workbooks before allowing a report-set upload", async () => {
    mocks.inspect.mockResolvedValue({
      headers: ["account_code"],
      sheets: ["One", "Two"],
    });
    render(
      <ReportPackageWizard provider="netsuite" renderBatch={() => null} />,
    );
    fireEvent.change(screen.getByLabelText("Trial balance file"), {
      target: { files: [new File(["workbook"], "test.xlsx")] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "single-sheet XLSX or CSV",
    );
    expect(
      screen.getByRole("button", {
        name: "Reconcile reports and create import batches",
      }),
    ).toBeDisabled();
    expect(mocks.mutate).not.toHaveBeenCalled();
  });
});

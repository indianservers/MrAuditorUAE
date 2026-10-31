import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ useAPI: vi.fn(), calculate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: mock.useAPI,
  useAction: () => ({
    mutateAsync: mock.calculate,
    isPending: false,
    error: null,
  }),
}));
vi.mock("@/features/audit-studio", () => ({ AuditStudio: () => null }));
vi.mock("@/features/shared", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@/components/grids/financial-data-grid", () => ({
  FinancialDataGrid: () => <div>Financial grid</div>,
  column: () => ({}),
  amount: () => ({}),
}));

import { IFRSStudio } from "@/features/ifrs-studio";
import { useScope } from "@/stores/workspace";

beforeEach(() => {
  useScope.setState({ tenant: "tenant-a" });
  mock.calculate.mockReset().mockResolvedValue({ id: "SYN-RUN" });
  mock.useAPI.mockImplementation((path: string) => {
    const recordKind = path.split("?")[0].match(/\/records\/([^/]+)$/)?.[1];
    return {
      data: recordKind
        ? {
            items: [
              {
                id: `SYN-${recordKind}`,
                reference: `Approved ${recordKind}`,
                status: "APPROVED",
              },
            ],
          }
        : path.endsWith("/runs")
          ? { items: [] }
          : undefined,
      isLoading: false,
      error: null,
    };
  });
});

it("clears retained record selections when the active tenant changes", () => {
  render(<IFRSStudio id="E" area="inventory" />);
  fireEvent.change(screen.getByLabelText("Approved assumptions"), {
    target: { value: "SYN-inventory" },
  });
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeEnabled();
  act(() => useScope.setState({ tenant: "tenant-b" }));
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeDisabled();
});

it.each([
  ["AE", "inventory"],
  ["IN", "inventory"],
  ["AE", "employee-benefits"],
  ["IN", "employee-benefits"],
])(
  "executes approved %s %s assumptions through the existing numeric engine",
  async (country, area) => {
    render(<IFRSStudio id={`${country}-E`} area={area} />);
    const calculate = screen.getByRole("button", {
      name: "Calculate approved inputs",
    });
    expect(calculate).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Approved assumptions"), {
      target: { value: `SYN-${area}` },
    });
    expect(calculate).toBeEnabled();
    fireEvent.click(calculate);
    await waitFor(() =>
      expect(mock.calculate).toHaveBeenCalledWith({
        path: `ifrs/engagements/${country}-E/calculate/SYN-${area}`,
      }),
    );
  },
);

it("clears selected assumptions and immutable runs when switching calculation subtype", async () => {
  const { rerender } = render(<IFRSStudio id="E" area="impairment" />);
  fireEvent.change(screen.getByLabelText("Approved assumptions"), {
    target: { value: "SYN-impairment" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  );
  await waitFor(() =>
    expect(mock.useAPI).toHaveBeenCalledWith(
      "ifrs/engagements/E/runs/SYN-RUN",
      true,
    ),
  );
  fireEvent.change(screen.getByLabelText("Calculation type"), {
    target: { value: "provision" },
  });
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("");
  expect(screen.getByLabelText("Immutable version")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Approved assumptions"), {
    target: { value: "SYN-provision" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  );
  await waitFor(() =>
    expect(mock.calculate).toHaveBeenLastCalledWith({
      path: "ifrs/engagements/E/calculate/SYN-provision",
    }),
  );
  rerender(<IFRSStudio id="E2" area="impairment" />);
  expect(screen.getByLabelText("Calculation type")).toHaveValue("impairment");
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeDisabled();
});

it("does not carry instrument mode or a selected record into an inventory workspace", () => {
  const { rerender } = render(<IFRSStudio id="E" area="ecl" />);
  fireEvent.change(screen.getByLabelText("Instrument workbench"), {
    target: { value: "instrument" },
  });
  fireEvent.change(screen.getByLabelText("Approved assumptions"), {
    target: { value: "SYN-instrument" },
  });
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeEnabled();
  rerender(<IFRSStudio id="E" area="inventory" />);
  expect(
    screen.getByRole("option", { name: "Approved inventory · APPROVED" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Approved assumptions")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeDisabled();
  expect(mock.calculate).not.toHaveBeenCalled();
});

it("keeps workflows without a standalone numeric engine disabled", () => {
  render(<IFRSStudio id="E" area="policies" />);
  fireEvent.change(screen.getByLabelText("Approved assumptions"), {
    target: { value: "SYN-accounting-policy" },
  });
  expect(
    screen.getByRole("button", { name: "Calculate approved inputs" }),
  ).toBeDisabled();
  expect(mock.calculate).not.toHaveBeenCalled();
});

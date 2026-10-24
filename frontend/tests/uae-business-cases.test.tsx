import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UAEBusinessCases } from "@/features/uae-business-cases";
const mocks = vi.hoisted(() => ({ run: vi.fn(), allowed: true }));
vi.mock("@/hooks/use-api", () => ({
  useCan: () => mocks.allowed,
  useAction: () => ({ mutateAsync: mocks.run, isPending: false }),
  useAPI: (path: string) => ({
    data: path.endsWith("/use-cases")
      ? {
          items: [
            {
              id: 1,
              key: "uae-01",
              title: "Synthetic VAT question",
              prompt: "Review supplied evidence",
              description: "Synthetic test scenario",
              engines: ["E01", "E04"],
              required_information: ["Reviewed tax facts"],
              module_url: "/vat/e/rules",
              workflow: null,
              calculation: {
                family: "vat",
                kind: "profile",
                operation: "compute",
              },
              limitations: ["Professional review required"],
            },
          ],
        }
      : path.endsWith("/inputs")
        ? {
            items: [
              {
                id: "approved",
                reference: "A",
                title: "Approved source",
                status: "APPROVED",
                kind: "vat-profile",
                version: 2,
              },
              {
                id: "draft",
                reference: "D",
                title: "Draft source",
                status: "DRAFT",
                kind: "vat-profile",
                version: 1,
              },
            ],
          }
        : undefined,
    error: undefined,
    refetch: vi.fn(),
  }),
}));
describe("UAE business workflow entry", () => {
  beforeEach(() => {
    mocks.allowed = true;
    mocks.run.mockReset();
    mocks.run.mockResolvedValue({ id: "retained-result" });
  });
  it("shows actual scoped records and required facts without a compliance badge", () => {
    render(<UAEBusinessCases eid="e" />);
    expect(screen.getByText("Reviewed tax facts")).toBeInTheDocument();
    expect(
      screen.getByRole("cell", { name: "A · Approved source" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Open specialist/ }),
    ).toHaveAttribute("href", "/vat/e/rules");
    expect(screen.queryByText("Compliant")).not.toBeInTheDocument();
  });
  it("invokes the governed action with an approved input, never a posting endpoint", async () => {
    render(<UAEBusinessCases eid="e" />);
    fireEvent.change(screen.getByLabelText("Approved engine input"), {
      target: { value: "approved" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Run governed calculation" }),
    );
    await waitFor(() =>
      expect(mocks.run).toHaveBeenCalledWith(
        expect.objectContaining({
          path: "ai/engagements/e/use-cases/1/actions",
          body: expect.objectContaining({
            action: "calculate",
            record_id: "approved",
          }),
        }),
      ),
    );
    expect(
      screen.queryByRole("option", { name: "D · Draft source" }),
    ).not.toBeInTheDocument();
  });
  it("disables actions without permission", () => {
    mocks.allowed = false;
    render(<UAEBusinessCases eid="e" />);
    expect(
      screen.getByRole("button", { name: "Start source-linked analysis" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "Create source-linked draft workpaper",
      }),
    ).toBeDisabled();
  });
});

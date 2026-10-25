import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WithholdingObligationSource } from "@/features/withholding-obligation-source";
const state = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/hooks/use-api", () => ({
  useAction: () => ({
    mutateAsync: state.mutate,
    isPending: false,
    error: null,
  }),
}));
beforeEach(() => {
  state.mutate.mockReset();
  state.mutate.mockResolvedValue({ id: "new-source" });
});

it("requires independent controls and does not preselect expected liability or a payer role", async () => {
  render(
    <WithholdingObligationSource
      eid="eng"
      sourceId="parent"
      onCreated={vi.fn()}
    />,
  );
  fireEvent.click(
    screen.getByText(
      "Prepare withholding obligations for split bank allocations",
    ),
  );
  expect(screen.getByLabelText("Withholding obligation purpose")).toHaveValue(
    "",
  );
  expect(screen.getByLabelText("Withholding payer role")).toHaveValue("");
  fireEvent.click(
    screen.getByRole("button", {
      name: "Prepare withholding bank-allocation source",
    }),
  );
  expect(
    await screen.findByText(/Enter the source purpose, payer role/),
  ).toBeVisible();
  expect(state.mutate).not.toHaveBeenCalled();
});

it.each(["expected", "reported"])(
  "prepares only the explicitly chosen %s purpose and preserves exact amount text",
  async (purpose) => {
    const created = vi.fn();
    render(
      <WithholdingObligationSource
        eid="eng"
        sourceId="parent"
        onCreated={created}
      />,
    );
    fireEvent.click(
      screen.getByText(
        "Prepare withholding obligations for split bank allocations",
      ),
    );
    for (const [label, value] of [
      ["Withholding obligation purpose", purpose],
      ["Withholding payer role", "deductor"],
      ["Withholding obligation cutoff", "2026-06-30"],
      ["Independent current withholding rows", "2"],
      ["Independent current withholding total (INR)", "180.00000001"],
      ["Withholding obligation source title", "Synthetic split liabilities"],
      [
        "Withholding allocation scope assessment",
        "Independent retained rule and reported populations assessed",
      ],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Prepare withholding bank-allocation source",
      }),
    );
    await waitFor(() => expect(created).toHaveBeenCalledWith("new-source"));
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      path: "intelligence/engagements/eng/events/parent/withholding-obligation-source",
      body: {
        purpose,
        legal_role: "deductor",
        expected_current_rows: 2,
        amount: "180.00000001",
        cutoff_date: "2026-06-30",
      },
    });
  },
);

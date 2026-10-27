import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TurnoverLedgerSource } from "@/features/turnover-ledger-source";

const mutate = vi.hoisted(() => vi.fn().mockResolvedValue({ id: "books" }));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({
    data: { items: [{ id: "revenue", code: "400", name: "Revenue" }] },
  }),
  useAction: () => ({ mutateAsync: mutate, isPending: false, error: null }),
}));

describe("Committed turnover controls", () => {
  it.each([
    ["AE", "TRN", "AED"],
    ["IN", "GSTIN", "INR"],
  ])(
    "requires explicit %s counts, nil assessment and signed amounts",
    async (country, scheme, currency) => {
      mutate.mockClear();
      const created = vi.fn();
      render(
        <TurnoverLedgerSource
          eid="eng"
          country={country}
          snapshots={[{ id: "snapshot", label: "Committed" }]}
          onCreated={created}
        />,
      );
      fireEvent.click(
        screen.getByText("Prepare book turnover from committed GL"),
      );
      const button = screen.getByRole("button", {
        name: "Prepare turnover books",
      });
      fireEvent.change(screen.getByLabelText("Turnover committed snapshot"), {
        target: { value: "snapshot" },
      });
      const select = screen.getByLabelText(
        "Turnover revenue accounts",
      ) as HTMLSelectElement;
      select.options[0].selected = true;
      fireEvent.change(select);
      for (const [name, value] of [
        [
          `Turnover registration (${scheme})`,
          country === "AE" ? "100000000000001" : "27ABCDE1234F1Z5",
        ],
        ["Turnover period start", "2026-06-01"],
        ["Turnover period end", "2026-06-30"],
        [`Independent signed book turnover (${currency})`, "0"],
        [
          "Revenue account and registration allocation assessment",
          "Selected revenue scope independently assessed",
        ],
        ["Turnover book source title", "Synthetic book movements"],
      ])
        fireEvent.change(screen.getByLabelText(name), { target: { value } });
      expect(button).toBeDisabled(); // A blank count is not an explicit nil selection.
      fireEvent.change(
        screen.getByLabelText("Independent GL movement line count"),
        { target: { value: "0" } },
      );
      expect(button).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Nil movement assessment"), {
        target: { value: "No movements in this assessed selection" },
      });
      expect(button).toBeEnabled();
      fireEvent.click(button);
      await waitFor(() => expect(created).toHaveBeenCalledWith("books"));
      expect(mutate.mock.calls[0][0].body).toMatchObject({
        currency,
        expected_rows: 0,
        expected_amount: "0",
        account_ids: ["revenue"],
      });
      fireEvent.change(screen.getByLabelText("Turnover committed snapshot"), {
        target: { value: "" },
      });
      expect(button).toBeDisabled();
    },
  );
});

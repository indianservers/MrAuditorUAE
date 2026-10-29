import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import {
  MerchantReserveControls,
  reserveControlPayload,
} from "@/features/merchant-reserve-controls";

it.each(["merchant-reserve-movements", "merchant-reserve-balances"])(
  "requires both independently declared %s controls",
  (table) => {
    expect(() =>
      reserveControlPayload(table, { currency: "AED", first: "", second: "0" }),
    ).toThrow();
    expect(() =>
      reserveControlPayload(table, {
        currency: "AED",
        first: "0",
        second: "-1",
      }),
    ).toThrow();
    expect(() =>
      reserveControlPayload(table, { currency: "AE", first: "0", second: "0" }),
    ).toThrow();
    const result = reserveControlPayload(table, {
      currency: "INR",
      first: "0",
      second: "5.001",
    });
    expect(result).toEqual(
      table.endsWith("movements")
        ? { INR: { held: "0", released: "5.001" } }
        : { INR: { opening_balance: "0", closing_balance: "5.001" } },
    );
  },
);

it("preserves separately entered gross controls and starts without invented zeros", () => {
  function Example() {
    const [value, setValue] = useState({ currency: "", first: "", second: "" });
    return (
      <MerchantReserveControls
        table="merchant-reserve-movements"
        value={value}
        onChange={setValue}
      />
    );
  }
  render(<Example />);
  expect(screen.getByLabelText("Total held")).toHaveValue("");
  expect(screen.getByLabelText("Total released")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Reserve control currency"), {
    target: { value: "aed" },
  });
  fireEvent.change(screen.getByLabelText("Total held"), {
    target: { value: "50" },
  });
  fireEvent.change(screen.getByLabelText("Total released"), {
    target: { value: "5" },
  });
  expect(screen.getByLabelText("Reserve control currency")).toHaveValue("AED");
  expect(screen.getByLabelText("Total held")).toHaveValue("50");
  expect(screen.getByLabelText("Total released")).toHaveValue("5");
});

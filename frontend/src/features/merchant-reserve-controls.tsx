"use client";

export type ReserveControls = {
  currency: string;
  first: string;
  second: string;
};

export function reserveControlPayload(table: string, values: ReserveControls) {
  if (
    !["merchant-reserve-movements", "merchant-reserve-balances"].includes(table)
  ) {
    throw new Error("Select a reserve movement or balance source.");
  }
  if (
    !/^[A-Z]{3}$/.test(values.currency) ||
    ![values.first, values.second].every((value) =>
      /^\d+(?:\.\d+)?$/.test(value),
    )
  ) {
    throw new Error(
      "Enter a three-letter currency and both independently checked reserve totals, including explicit zeros.",
    );
  }
  const fields =
    table === "merchant-reserve-movements"
      ? ["held", "released"]
      : ["opening_balance", "closing_balance"];
  return {
    [values.currency]: {
      [fields[0]]: values.first,
      [fields[1]]: values.second,
    },
  };
}

export function MerchantReserveControls({
  table,
  value,
  onChange,
}: {
  table: string;
  value: ReserveControls;
  onChange: (value: ReserveControls) => void;
}) {
  const movement = table === "merchant-reserve-movements";
  return (
    <fieldset style={{ gridColumn: "1 / -1" }}>
      <legend>Independent reserve controls</legend>
      <label>
        Reserve control currency
        <input
          aria-label="Reserve control currency"
          maxLength={3}
          value={value.currency}
          onChange={(event) =>
            onChange({ ...value, currency: event.target.value.toUpperCase() })
          }
        />
      </label>
      <label>
        {movement ? "Total held" : "Total opening balance"}
        <input
          aria-label={movement ? "Total held" : "Total opening balance"}
          inputMode="decimal"
          value={value.first}
          onChange={(event) =>
            onChange({ ...value, first: event.target.value })
          }
        />
      </label>
      <label>
        {movement ? "Total released" : "Total closing balance"}
        <input
          aria-label={movement ? "Total released" : "Total closing balance"}
          inputMode="decimal"
          value={value.second}
          onChange={(event) =>
            onChange({ ...value, second: event.target.value })
          }
        />
      </label>
      <p>
        Enter separately checked totals in one currency. Missing values are not
        zero. Holds and releases remain separate; no bank receipt is
        established.
      </p>
    </fieldset>
  );
}

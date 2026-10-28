"use client";

const components = [
  ["Gross sales", "sales"],
  ["Less refunds", "refunds"],
  ["Less chargebacks", "chargebacks"],
  ["Less processor fees", "fees"],
  ["Less assessed fee tax", "fee_tax"],
  ["Less reported withholding", "withholding"],
  ["Less reserve held", "reserve_held"],
  ["Plus reserve released", "reserve_released"],
  ["Calculated net", "expected_net"],
  ["Reported net", "amount"],
  ["Allocated bank amount", "bank_allocated"],
  ["Bank difference", "bank_difference"],
] as const;

const value = (row: Record<string, unknown>, key: string) => {
  const entry = row[key];
  return entry == null
    ? "Not supplied"
    : Array.isArray(entry)
      ? entry.length
        ? entry.join(", ")
        : "None retained for this row"
      : String(entry);
};

/** Reads the current result page only; never recalculates or approves an amount. */
export function MerchantSettlementDetails({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  return (
    <section aria-label="Merchant settlement components">
      <h3>Gross-to-net components</h3>
      {rows.map((row) =>
        row.kind === "MERCHANT_SETTLEMENT" ? (
          <details key={String(row.id)}>
            <summary>
              Batch {value(row, "batch")} · {value(row, "merchant")} ·{" "}
              {value(row, "processor")} · {value(row, "currency")}
            </summary>
            <p>
              Activity period {value(row, "period_start")} to{" "}
              {value(row, "period_end")}; processor settlement date{" "}
              {value(row, "settlement_date")}.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Amount ({value(row, "currency")})</th>
                </tr>
              </thead>
              <tbody>
                {components.map(([label, field]) => (
                  <tr key={field}>
                    <td>{label}</td>
                    <td>{value(row, field)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              Net arithmetic difference:{" "}
              {value(row, "net_arithmetic_difference")}.
            </p>
            <dl>
              {["sales", "refunds", "chargebacks"].map((field) => (
                <div key={field}>
                  <dt>Book {field} difference</dt>
                  <dd>
                    {value(
                      (row.book_differences &&
                      typeof row.book_differences === "object"
                        ? row.book_differences
                        : {}) as Record<string, unknown>,
                      field,
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            <p>
              Assessed fee-tax classification: {value(row, "tax_country")} /{" "}
              {value(row, "fee_tax_kind")}. Assessment reference:{" "}
              {value(row, "tax_assessment_reference")}.
            </p>
            <p>
              Book activity rows: {value(row, "book_activity_ids")}. Bank
              allocation rows: {value(row, "allocation_ids")}.
            </p>
            <p>Processor evidence: {value(row, "evidence_reference")}.</p>
            <p>
              Tax rates, tax recovery and withholding entitlement remain
              independently assessed.
            </p>
          </details>
        ) : row.kind === "BANK_RESIDUAL" ? (
          <p key={String(row.id)}>
            Unallocated bank movement {value(row, "bank_transaction_id")}:{" "}
            {value(row, "currency")} {value(row, "amount")}.
          </p>
        ) : null,
      )}
    </section>
  );
}

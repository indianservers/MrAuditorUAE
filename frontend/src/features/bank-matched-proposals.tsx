"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export type BankProposal = {
  left_ids: string[];
  right_ids: string[];
  rule: string;
  variance: string;
  auditor_status?: string;
};

type SourceRow = {
  id: string;
  reference: string;
  date: string;
  amount: string;
  currency: string;
  counterparty?: string;
  bank_date_basis?: string;
  bank_booking_date?: string;
  bank_value_date?: string;
};

function ProposalDetails({
  prefix,
  selected,
  index,
}: {
  prefix: string;
  selected: string;
  index: number;
}) {
  const q = useAPI<{ books: SourceRow[]; statement: SourceRow[] }>(
    `${prefix}/events/${selected}/bank-matched-proposal?index=${index}`,
  );
  return (
    <section aria-label="Matched proposal transaction details">
      <h4>Original transactions for proposal {index + 1}</h4>
      <ErrorState error={q.error} />
      {q.data &&
        (["books", "statement"] as const).map((side) => (
          <div key={side}>
            <h4>
              {side === "books"
                ? "Book transactions"
                : "Statement transactions"}
            </h4>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    {[
                      "Source row",
                      "Reference",
                      "Date",
                      "Amount",
                      "Currency",
                      "Counterparty",
                      "Booked date",
                      "Value date",
                      "Date evidence",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {q.data![side].map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>{row.reference}</td>
                      <td>{row.date}</td>
                      <td>{row.amount}</td>
                      <td>{row.currency}</td>
                      <td>{row.counterparty || "Not supplied"}</td>
                      <td>{row.bank_booking_date || "Not supplied"}</td>
                      <td>{row.bank_value_date || "Not supplied"}</td>
                      <td>{row.bank_date_basis || "Not supplied"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
    </section>
  );
}

/** Parent keys this reader by the immutable selected event version. */
export function BankMatchedProposals({
  prefix,
  selected,
  total,
}: {
  prefix: string;
  selected: string;
  total: number;
}) {
  const [offset, setOffset] = useState(0);
  const [active, setActive] = useState<number | null>(null);
  const q = useAPI<{ body: { matches: BankProposal[] } }>(
    `${prefix}/events/${selected}?offset=${offset}&limit=25`,
  );
  const rows = q.data?.body.matches || [];
  return (
    <section aria-label="Bank matched proposals">
      <h3>Matched transaction proposals</h3>
      <p>
        Inspect original references, dates and signed amounts before deciding.
        Matching alone does not authenticate bank documents, confirm payment or
        post accounting entries.
      </p>
      <ErrorState error={q.error} />
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              {[
                "Proposal",
                "Book items",
                "Statement items",
                "Matching rule",
                "Variance",
                "Saved decision",
                "Original transactions",
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={offset + index}>
                <td>{offset + index + 1}</td>
                <td>{row.left_ids.length}</td>
                <td>{row.right_ids.length}</td>
                <td>{row.rule}</td>
                <td>{row.variance}</td>
                <td>{row.auditor_status || "Not separately assessed"}</td>
                <td>
                  <Button
                    aria-pressed={active === offset + index}
                    onClick={() => setActive(offset + index)}
                  >
                    Inspect proposal {offset + index + 1}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar">
        <Button
          disabled={!offset || q.isFetching}
          onClick={() => {
            setOffset((value) => Math.max(0, value - 25));
            setActive(null);
          }}
        >
          Previous matched proposals
        </Button>
        <span>
          Proposals {rows.length ? offset + 1 : 0}–
          {Math.min(offset + rows.length, total)} of {total}
        </span>
        <Button
          disabled={offset + 25 >= total || q.isFetching}
          onClick={() => {
            setOffset((value) => value + 25);
            setActive(null);
          }}
        >
          Next matched proposals
        </Button>
      </div>
      {active !== null && (
        <ProposalDetails
          key={active}
          prefix={prefix}
          selected={selected}
          index={active}
        />
      )}
    </section>
  );
}

"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export type BankAmbiguity = {
  left_id: string;
  candidate_count?: number;
  candidate_ids?: string[];
  candidate_preview_truncated?: boolean;
};
type Transaction = {
  id: string;
  reference: string;
  counterparty?: string;
  date: string;
  amount: string;
  currency: string;
  machine_match?: {
    left_ids: string[];
    rule: string;
    auditor_status: string;
  } | null;
};

function CandidatePage({
  prefix,
  selected,
  left,
}: {
  prefix: string;
  selected: string;
  left: string;
}) {
  const [offset, setOffset] = useState(0);
  const q = useAPI<{ left: Transaction; items: Transaction[]; total: number }>(
    `${prefix}/events/${selected}/bank-candidates?left_id=${encodeURIComponent(left)}&offset=${offset}&limit=25`,
    true,
  );
  return (
    <section aria-label="Candidate transaction details">
      {q.data && (
        <>
          <p>
            Book item {q.data.left.id}: {q.data.left.reference} ·{" "}
            {q.data.left.counterparty || "No counterparty supplied"} ·{" "}
            {q.data.left.date} · {q.data.left.amount} {q.data.left.currency}
          </p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  {[
                    "Source ID",
                    "Reference",
                    "Counterparty",
                    "Date",
                    "Amount",
                    "Currency",
                    "Machine proposal",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((row) => (
                  <tr key={row.id}>
                    {[
                      row.id,
                      row.reference,
                      row.counterparty || "—",
                      row.date,
                      row.amount,
                      row.currency,
                      row.machine_match
                        ? `${row.machine_match.left_ids.join(", ")} · ${row.machine_match.rule} · ${row.machine_match.auditor_status}`
                        : "No machine proposal",
                    ].map((value, index) => (
                      <td key={index}>{value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="toolbar">
            <Button
              disabled={!offset || q.isFetching}
              onClick={() => setOffset((value) => Math.max(0, value - 25))}
            >
              Previous candidates
            </Button>
            <span>
              Candidates {offset + 1}–{Math.min(offset + 25, q.data.total)} of{" "}
              {q.data.total}
            </span>
            <Button
              disabled={offset + 25 >= q.data.total || q.isFetching}
              onClick={() => setOffset((value) => value + 25)}
            >
              Next candidates
            </Button>
          </div>
        </>
      )}
      <ErrorState error={q.error} />
    </section>
  );
}

export function BankMatchingCandidates({
  prefix,
  selected,
  initial,
  total,
  contract,
  label = "Bank matching candidates",
}: {
  prefix: string;
  selected: string;
  initial: BankAmbiguity[];
  total: number;
  contract?: string;
  label?: string;
}) {
  const [offset, setOffset] = useState(0);
  const [active, setActive] = useState(initial[0]?.left_id || "");
  const q = useAPI<{ body: { ambiguous: BankAmbiguity[] } }>(
    `${prefix}/events/${selected}?limit=1&ambiguity_offset=${offset}&ambiguity_limit=25`,
    contract === "indexed-transaction-candidates/1",
  );
  const rows = q.data?.body.ambiguous || (offset ? [] : initial.slice(0, 25));
  if (contract !== "indexed-transaction-candidates/1")
    return (
      <p role="note">
        Recalculate this historical matching result to retain every competing
        candidate before approval.
      </p>
    );
  return (
    <section aria-label={label}>
      <h3>Competing transaction candidates</h3>
      <p>
        Every retained candidate is available through these pages. These are
        possible alternatives; viewing a candidate does not select, match or
        approve it.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {rows.map((row) => (
          <Button
            key={row.left_id}
            onClick={() => setActive(row.left_id)}
            aria-pressed={active === row.left_id}
          >
            Inspect {row.left_id} · {row.candidate_count} candidates
          </Button>
        ))}
      </div>
      <div className="toolbar">
        <Button
          disabled={!offset || q.isFetching}
          onClick={() => {
            setOffset((value) => Math.max(0, value - 25));
            setActive("");
          }}
        >
          Previous ambiguous items
        </Button>
        <span>
          Ambiguous items {offset + 1}–{Math.min(offset + 25, total)} of {total}
        </span>
        <Button
          disabled={offset + 25 >= total || q.isFetching}
          onClick={() => {
            setOffset((value) => value + 25);
            setActive("");
          }}
        >
          Next ambiguous items
        </Button>
      </div>
      <ErrorState error={q.error} />
      {active && (
        <CandidatePage
          key={active}
          prefix={prefix}
          selected={selected}
          left={active}
        />
      )}
    </section>
  );
}

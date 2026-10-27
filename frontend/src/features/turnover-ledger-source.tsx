"use client";

import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export function TurnoverLedgerSource({
  eid,
  country,
  snapshots,
  onCreated,
}: {
  eid: string;
  country: string;
  snapshots: { id: string; label: string }[];
  onCreated: (id: string) => void;
}) {
  const [snapshot, setSnapshot] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [registration, setRegistration] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [count, setCount] = useState("");
  const [amount, setAmount] = useState("");
  const [assessment, setAssessment] = useState("");
  const [nil, setNil] = useState("");
  const [label, setLabel] = useState("");
  const prefix = `intelligence/engagements/${eid}`;
  const accounts = useAPI<{
    items: { id: string; code: string; name: string }[];
    truncated?: boolean;
  }>(
    `${prefix}/accounts?snapshot_id=${snapshot}&search=${encodeURIComponent(search)}`,
    !!snapshot,
  );
  const action = useAction<{ id: string }>();
  const currency = country === "AE" ? "AED" : "INR";
  const countValid = /^\d+$/.test(count) && Number(count) <= 5000;
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>Prepare book turnover from committed GL</summary>
      <p>
        Select the revenue accounts allocated to one{" "}
        {country === "AE" ? "TRN" : "GSTIN"} and period. Credits increase book
        turnover; debit reversals reduce it. Opening balances are excluded. This
        covers the selected accounts only. It requires independent review and
        separate return evidence.
      </p>
      <ErrorState error={action.error || accounts.error} />
      <label>
        Turnover committed snapshot
        <select
          value={snapshot}
          onChange={(e) => {
            setSnapshot(e.target.value);
            setSelected([]);
          }}
        >
          <option value="">Select committed GL/journal snapshot</option>
          {snapshots.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Find turnover accounts (changing the search clears the selection)
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setSelected([]);
          }}
        />
      </label>
      {accounts.data?.truncated && (
        <p>
          Only the first 1,000 matching accounts are shown. Narrow the account
          search before selecting.
        </p>
      )}
      <label>
        Turnover revenue accounts
        <select
          multiple
          size={6}
          value={selected}
          onChange={(e) =>
            setSelected(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {accounts.data?.items.map((a) => (
            <option key={a.id} value={a.id}>
              {a.code} · {a.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Turnover registration ({country === "AE" ? "TRN" : "GSTIN"})
        <input
          value={registration}
          onChange={(e) => setRegistration(e.target.value.toUpperCase())}
        />
      </label>
      <label>
        Turnover period start
        <input
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </label>
      <label>
        Turnover period end
        <input
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <label>
        Independent GL movement line count
        <input
          inputMode="numeric"
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      <label>
        Independent signed book turnover ({currency})
        <input
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <label>
        Revenue account and registration allocation assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      {countValid && Number(count) === 0 && (
        <label>
          Nil movement assessment
          <textarea value={nil} onChange={(e) => setNil(e.target.value)} />
        </label>
      )}
      <label>
        Turnover book source title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      <p>
        Amounts must already use the entity functional currency {currency}. No
        FX conversion, revenue classification or registration ownership is
        inferred.
      </p>
      <Button
        disabled={
          action.isPending ||
          !snapshot ||
          !selected.length ||
          selected.length > 100 ||
          !registration ||
          !start ||
          !end ||
          start > end ||
          !countValid ||
          !amount.trim() ||
          assessment.trim().length < 10 ||
          label.trim().length < 3 ||
          (Number(count) === 0 && nil.trim().length < 10)
        }
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `${prefix}/turnover-ledger-source`,
              body: {
                snapshot_id: snapshot,
                account_ids: selected,
                registration,
                period_start: start,
                period_end: end,
                currency,
                expected_rows: Number(count),
                expected_amount: amount,
                assessment,
                nil_reason: Number(count) === 0 ? nil : "",
                label,
              },
            });
            onCreated(result.id);
          } catch {
            /* Mutation errors are displayed above. */
          }
        }}
      >
        Prepare turnover books
      </Button>
    </details>
  );
}

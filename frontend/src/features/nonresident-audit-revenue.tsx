"use client";
import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Scope = {
  amount: string;
  currency: "AED";
  period_start: string;
  period_end: string;
  scope: "uae_pe_and_nexus";
  population_complete: boolean;
  assessment: string;
  evidence_id: string;
  source_path: (string | number)[];
};
type Paper = {
  id: string;
  reference: string;
  status: string;
  body: {
    financial_tables?: { title?: string; values?: Record<string, unknown> }[];
  };
};
export function NonresidentAuditRevenueEditor({
  base,
  value,
  onChange,
}: {
  base: string;
  value: unknown;
  onChange: (value: Scope | null) => void;
}) {
  const saved = value && typeof value === "object" ? (value as Scope) : null;
  const [picked, setPicked] = useState("");
  const [offset, setOffset] = useState(0);
  const [index, setIndex] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const selected = saved?.evidence_id || picked;
  const papers = useAPI<{ items: Paper[]; total: number }>(
    `${base}/working-papers?limit=50&offset=${offset}`,
  );
  const detail = useAPI<Paper>(`${base}/records/${selected}`, !!selected);
  const choices = (papers.data?.items || []).filter((item) =>
    ["APPROVED", "LOCKED"].includes(item.status),
  );
  if (
    detail.data &&
    detail.data.id === selected &&
    !choices.some((item) => item.id === selected)
  )
    choices.push(detail.data);
  const tables = detail.data?.body.financial_tables || [];
  const tableIndex =
    saved?.evidence_id === selected
      ? String(saved.source_path?.[1] ?? "")
      : index;
  function adopt() {
    const values = tables[Number(tableIndex)]?.values;
    const amount = values?.amount;
    if (
      !values ||
      values.scope !== "uae_pe_and_nexus" ||
      values.currency !== "AED" ||
      typeof values.population_complete !== "boolean" ||
      typeof values.period_start !== "string" ||
      typeof values.period_end !== "string" ||
      typeof values.assessment !== "string" ||
      !(
        typeof amount === "string" ||
        (typeof amount === "number" &&
          Number.isSafeInteger(amount) &&
          amount >= 0)
      )
    ) {
      setError(
        new Error(
          "The selected table needs an exact UAE PE/nexus scope, AED amount as a decimal string, tax-period dates, an explicit population-completeness decision and assessment.",
        ),
      );
      return;
    }
    setError(null);
    onChange({
      amount: String(amount),
      currency: "AED",
      period_start: values.period_start,
      period_end: values.period_end,
      scope: "uae_pe_and_nexus",
      population_complete: values.population_complete,
      assessment: values.assessment,
      evidence_id: selected,
      source_path: ["financial_tables", Number(tableIndex), "values"],
    });
  }
  return (
    <fieldset>
      <legend>Nonresident UAE PE/nexus audit revenue</legend>
      <p>
        For tax periods starting from 1 January 2025, select a separately
        reviewed working paper assessing the complete UAE PE/nexus revenue
        population. Worldwide turnover is not substituted. Sources must remain
        current and independently reviewed.
      </p>
      <ErrorState error={papers.error || detail.error || error} />
      <label>
        Revenue scope working paper
        <select
          value={selected}
          onChange={(e) => {
            setPicked(e.target.value);
            setIndex("");
            setError(null);
            onChange(null);
          }}
        >
          <option value="">No assessed source selected</option>
          {choices.map((item) => (
            <option key={item.id} value={item.id}>
              {item.reference} · {item.status}
            </option>
          ))}
        </select>
      </label>
      <Button
        disabled={offset === 0}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Previous scope papers
      </Button>
      <Button
        disabled={offset + 50 >= (papers.data?.total || 0)}
        onClick={() => setOffset(offset + 50)}
      >
        Next scope papers
      </Button>
      {selected && (
        <>
          <label>
            Retained revenue scope table
            <select
              value={tableIndex}
              onChange={(e) => {
                setPicked(selected);
                setIndex(e.target.value);
                onChange(null);
              }}
            >
              <option value="">Choose assessed table</option>
              {tables.map((table, i) => (
                <option key={i} value={String(i)}>
                  {table.title || `Financial table ${i + 1}`}
                </option>
              ))}
            </select>
          </label>
          <Button
            disabled={
              tableIndex === "" ||
              !["APPROVED", "LOCKED"].includes(detail.data?.status || "")
            }
            onClick={adopt}
          >
            Adopt reviewed revenue scope
          </Button>
        </>
      )}
      {saved && (
        <p>
          Adopted AED {saved.amount}, {saved.period_start} to {saved.period_end}
          . Population:{" "}
          {saved.population_complete
            ? "assessed complete"
            : "incomplete; obligation remains unresolved"}
          .
        </p>
      )}
      <Button
        onClick={() => {
          setPicked("");
          setIndex("");
          onChange(null);
        }}
      >
        Clear revenue scope
      </Button>
    </fieldset>
  );
}

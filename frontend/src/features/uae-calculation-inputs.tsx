"use client";
import { useState } from "react";
import { useAction, useCan } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
type Source = {
  id: string;
  reference: string;
  title: string;
  status: string;
  kind: string;
};
function rows(text: string, columns: number) {
  return text
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line, i) => {
      const values = line.split(",").map((v) => v.trim());
      if (values.length !== columns || values.some((v) => !v))
        throw new Error(
          `Row ${i + 1} must contain ${columns} nonempty comma-separated fields. Use plain decimal amounts without thousands separators.`,
        );
      return values;
    });
}
export function UAECalculationInputs({
  eid,
  caseId,
  sources,
  onResult,
}: {
  eid: string;
  caseId: number;
  sources: Source[];
  onResult: (value: Record<string, unknown>) => void;
}) {
  const [source, setSource] = useState(""),
    [asOf, setAsOf] = useState(""),
    [historic, setHistoric] = useState(""),
    [forecast, setForecast] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState<Error>();
  const action = useAction<Record<string, unknown>>();
  const [precision, setPrecision] = useState(2);
  const runPermission = useCan("ai.workflow.run"),
    calculatePermission = useCan(
      caseId === 1 ? "vat.calculate" : "ifrs.calculation.execute",
    );
  if (![1, 45].includes(caseId)) return null;
  async function run() {
    setError(undefined);
    try {
      const observations = (text: string) =>
        rows(text, 4).map(([id, date, amount, taxable]) => {
          if (!["true", "false"].includes(taxable))
            throw new Error(
              "Taxable classification must be true or false; unresolved items use false.",
            );
          return {
            id,
            date,
            amount_aed: amount,
            taxable_classification_confirmed: taxable === "true",
          };
        });
      const payload =
        caseId === 1
          ? {
              as_of: asOf,
              historical: observations(historic),
              forecast: forecast.trim() ? observations(forecast) : [],
              nonresident_or_exception_requires_review: true,
            }
          : {
              balances: rows(historic, 6).map(
                ([
                  reference,
                  foreign_currency,
                  functional_currency,
                  foreign_units,
                  carrying_functional,
                  closing_rate,
                ]) => ({
                  reference,
                  foreign_currency,
                  functional_currency,
                  foreign_units,
                  carrying_functional,
                  closing_rate,
                  monetary_classification_reviewed: confirmed,
                }),
              ),
              rounding_precision: precision,
            };
      onResult(
        await action.mutateAsync({
          path: `ai/engagements/${eid}/use-cases/${caseId}/actions`,
          body: {
            action: caseId === 1 ? "registration-exposure" : "fx-review",
            record_id: source,
            payload,
            idempotency_key: crypto.randomUUID(),
          },
        }),
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e
          : new Error("Calculation failed; check the source records"),
      );
    }
  }
  return (
    <section
      aria-label={
        caseId === 1
          ? "VAT registration exposure inputs"
          : "Monetary FX review inputs"
      }
    >
      <h3>
        {caseId === 1
          ? "Registration exposure calculation"
          : "Monetary closing-balance calculation"}
      </h3>
      <label>
        {caseId === 1
          ? "Approved effective registration rule"
          : "Approved monetary classification and rate evidence"}
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Select approved source</option>
          {sources
            .filter(
              (r) =>
                ["APPROVED", "LOCKED"].includes(r.status) &&
                (caseId !== 1 || r.kind === "vat-rule"),
            )
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.reference} · {r.title}
              </option>
            ))}
        </select>
      </label>
      {caseId === 1 && (
        <label>
          Assessment date
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
      )}
      <p>
        {caseId === 1
          ? "Paste historical ledger rows without a header: source line ID, date, amount in AED, taxable classification confirmed (true/false). Amounts and dates are checked against the authorized ledger."
          : "Paste reviewed balances without a header: account/reference, foreign currency, functional currency, signed foreign units, signed functional carrying amount, closing rate. Use one functional currency per schedule. This does not automatically tie supplied balances to the ledger."}
      </p>
      <label>
        {caseId === 1
          ? "Historical observations"
          : "Reviewed monetary balances"}
        <textarea
          value={historic}
          onChange={(e) => setHistoric(e.target.value)}
          maxLength={45000}
        />
      </label>
      {caseId === 45 && (
        <label>
          Functional-currency decimal places from approved policy
          <input
            type="number"
            min={0}
            max={8}
            value={precision}
            onChange={(e) => setPrecision(Number(e.target.value))}
          />
        </label>
      )}
      {caseId === 1 ? (
        <>
          <p>
            Optional forecast rows: approved evidence record ID, date, amount in
            AED, taxable classification confirmed. Forecast amounts remain
            reviewer-supplied assumptions linked to the evidence.
          </p>
          <label>
            Forecast observations
            <textarea
              value={forecast}
              onChange={(e) => setForecast(e.target.value)}
              maxLength={15000}
            />
          </label>
        </>
      ) : (
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          Monetary classification and rate applicability were independently
          reviewed
        </label>
      )}
      <Button
        disabled={
          !runPermission ||
          !calculatePermission ||
          !source ||
          !historic.trim() ||
          (caseId === 1 ? !asOf : !confirmed) ||
          action.isPending
        }
        onClick={run}
      >
        Calculate review schedule
      </Button>
      {error && <ErrorState error={error} />}
      <p>
        Review signals and proposed balance adjustments only. No registration
        decision, journal posting or filing is performed.
      </p>
    </section>
  );
}

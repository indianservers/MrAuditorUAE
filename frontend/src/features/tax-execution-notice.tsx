"use client";

export function TaxExecutionNotice({
  result,
}: {
  result?: Record<string, unknown>;
}) {
  const value = result?.tax_execution as
    | {
        tax_type: string;
        input_completeness: string;
        professional_review: string;
        source_snapshots: { id: string; sha256: string }[];
        unresolved_questions: string[];
        filing_status: string;
        authority_assessment: string;
        payment_status: string;
        rounding: string;
      }
    | undefined;
  if (!value)
    return (
      <p className="subtle">
        Legacy tax execution metadata is incomplete. Review original source
        receipts before relying on this result.
      </p>
    );
  return (
    <aside
      className="main-panel"
      aria-label="Tax execution and review status"
      style={{ padding: 16 }}
    >
      <h3>{value.tax_type} calculation and review</h3>
      <p>
        Calculation method: deterministic. Input completeness:{" "}
        {value.input_completeness.replaceAll("_", " ")}.
      </p>
      <p>
        Professional review: draft requires review. Filing: not submitted.
        Authority assessment: not established. Payments: not reconciled by this
        calculation.
      </p>
      <p>
        {value.source_snapshots.length} retained source snapshots.{" "}
        {value.rounding}
      </p>
      {value.unresolved_questions.length > 0 && (
        <>
          <strong>Unresolved inputs and questions</strong>
          <ul>
            {value.unresolved_questions.map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}

"use client";

export function CTAuditObligationNotice({
  result,
}: {
  result: Record<string, unknown>;
}) {
  const value = result.audit_statement_obligation as
    | {
        assessment: string;
        decision: string;
        source_url: string;
        required_for_ct: boolean | null;
        statement_kind: string;
        threshold_revenue: string | null;
        declared_required: boolean;
        evidence_record_id: string | null;
        issues: string[];
      }
    | undefined;
  if (!value) return null;
  return (
    <aside className="main-panel" aria-label="CT audited statements obligation">
      <h3>CT audited statements obligation</h3>
      <p>
        {value.decision}: {value.assessment.replaceAll("_", " ")}
      </p>
      <dl>
        <dt>Required for Corporate Tax</dt>
        <dd>
          {value.required_for_ct === null
            ? "Not assessed"
            : value.required_for_ct
              ? "Yes"
              : "No threshold obligation identified"}
        </dd>
        <dt>Statement type</dt>
        <dd>{value.statement_kind.replaceAll("_", " ")}</dd>
        <dt>Revenue used for threshold (AED)</dt>
        <dd>{value.threshold_revenue ?? "Not assessed"}</dd>
        <dt>Approved profile declares an audit requirement</dt>
        <dd>{value.declared_required ? "Yes" : "No"}</dd>
        <dt>Supporting reviewed record</dt>
        <dd>{value.evidence_record_id || "Not supplied"}</dd>
      </dl>
      {value.issues.length > 0 && (
        <ul>
          {value.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      <p>
        Company-law, licensing and regulator audit requirements need separate
        assessment. A linked file does not certify an audit opinion or document
        authenticity.
      </p>
      <a href={value.source_url} target="_blank" rel="noreferrer">
        Read {value.decision}
      </a>
    </aside>
  );
}

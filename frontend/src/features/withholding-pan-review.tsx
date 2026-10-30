const MARKERS = ["PANNOTAVBL", "PANAPPLIED", "PANINVALID"];
const CONTRACT = "withholding-missing-pan-treatment/1";
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const value = (input: unknown) =>
  input == null || input === "" ? "Not recorded" : String(input);

export function WithholdingPANReview({
  rows,
  contract,
  counts,
}: {
  rows: Record<string, unknown>[];
  contract?: string;
  counts?: {
    rows_with_marker: number;
    pending_rows: number;
    documented_rows: number;
  };
}) {
  const selected = rows.filter((row) =>
    MARKERS.includes(
      String(row.pan_status ?? row.counterparty ?? "")
        .trim()
        .toUpperCase(),
    ),
  );
  if (!selected.length && !counts?.rows_with_marker) return null;
  const pending =
    !!counts?.pending_rows ||
    selected.some(
      (row) =>
        row.pan_treatment_state !== "DOCUMENTED_ON_RETAINED_ASSESSMENT" ||
        (Array.isArray(row.pan_issues) && row.pan_issues.length > 0),
    );
  return (
    <section aria-label="Missing PAN treatment review">
      <h3>Missing or invalid PAN treatment</h3>
      <p>
        Matching amounts do not resolve an unavailable, applied-for or invalid
        PAN. Documented treatment retains the uploaded marker and does not
        authenticate PAN or establish tax entitlement.
      </p>
      {contract !== CONTRACT ? (
        <p role="alert">
          Regenerate this retained result with current PAN-treatment controls
          before approval or downstream use.
        </p>
      ) : (
        pending && (
          <p role="alert">
            Complete the scoped treatment in the retained expected-rule or
            certificate source and regenerate. Row exception notes do not
            resolve this missing assessment.
          </p>
        )
      )}
      <p>
        This schedule follows the current result page. XLSX includes the
        complete bounded PAN-treatment schedule.
      </p>
      {counts && (
        <p>
          Complete result: {counts.rows_with_marker} marker rows;{" "}
          {counts.pending_rows} pending; {counts.documented_rows} documented.
        </p>
      )}
      {!selected.length && (
        <p>
          No missing-PAN rows are on this page. Use the result page controls or
          the complete XLSX schedule.
        </p>
      )}
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Withholding missing PAN assessments">
          <thead>
            <tr>
              <th>Transaction</th>
              <th>Uploaded marker</th>
              <th>Review state</th>
              <th>Retained assessment</th>
            </tr>
          </thead>
          <tbody>
            {selected.map((row, index) => {
              const context = object(row.pan_treatment);
              const provenance = object(row.assessment_provenance);
              const issues = Array.isArray(row.pan_issues)
                ? row.pan_issues
                : [];
              return (
                <tr key={String(row.id ?? index)}>
                  <td>
                    {value(row.transaction_reference)}
                    <br />
                    {value(row.legal_role)} · {value(row.period)}
                  </td>
                  <td>
                    {value(row.pan_status ?? row.counterparty)}
                    <br />
                    Authentication: {value(row.pan_authentication)}
                  </td>
                  <td>
                    {value(row.pan_treatment_state)}
                    {issues.length > 0 && (
                      <ul>
                        {issues.map((issue, i) => (
                          <li key={i}>{String(issue).replaceAll("_", " ")}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    <details>
                      <summary>Review party and treatment evidence</summary>
                      <dl>
                        <dt>Assessed party reference</dt>
                        <dd>{value(context.party_reference)}</dd>
                        <dt>Treatment reference</dt>
                        <dd>{value(context.treatment_reference)}</dd>
                        <dt>Assessed on</dt>
                        <dd>{value(context.assessed_on)}</dd>
                        <dt>Assessment</dt>
                        <dd>{value(context.assessment)}</dd>
                        <dt>Rule/certificate evidence version</dt>
                        <dd>
                          {value(provenance.assessment_evidence_version_id)}
                        </dd>
                        <dt>Original SHA-256</dt>
                        <dd>{value(provenance.assessment_sha256)}</dd>
                      </dl>
                    </details>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

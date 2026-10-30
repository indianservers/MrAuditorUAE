export type ADGMAccountsAssessment = {
  profile: string;
  state: string;
  filing_required: boolean | null;
  company_status_at_reference_end?: string;
  accounting_reference_start?: string;
  accounting_reference_end?: string;
  period_classification?: string;
  shortened_period?: string;
  assessed_on?: string;
  issues: string[];
  limitations?: string;
};

export function ADGMAccountsResult({
  assessment,
  available,
  freshness,
}: {
  assessment?: ADGMAccountsAssessment | null;
  available: boolean;
  freshness?: string;
}) {
  return (
    <section aria-label="ADGM accounts timetable assessment">
      <h3>ADGM accounts timetable assessment</h3>
      {!available || !assessment ? (
        <p role="status">
          The current-version ADGM assessment is pending. No filing duty,
          exemption or timetable is inferred.
        </p>
      ) : (
        <>
          <p>
            {assessment.state.replaceAll("_", " ")} · Assessed on{" "}
            {assessment.assessed_on ?? "Not retained"} · Source freshness:{" "}
            {freshness ?? "Unknown"}.
          </p>
          {freshness !== "CURRENT" && (
            <p role="alert">
              Reassess the original source documents before relying on this
              timetable.
            </p>
          )}
          <dl>
            <dt>Filing duty</dt>
            <dd>
              {assessment.filing_required === true
                ? "Required on assessed facts"
                : assessment.filing_required === false
                  ? "Assessed exempt; no filing deadline"
                  : "Unresolved"}
            </dd>
            <dt>Company status immediately before reference period end</dt>
            <dd>
              {assessment.company_status_at_reference_end ?? "Unresolved"}
            </dd>
            <dt>Accounting reference period</dt>
            <dd>
              {assessment.accounting_reference_start ?? "Not retained"} to{" "}
              {assessment.accounting_reference_end ?? "Not retained"}
            </dd>
            <dt>Period classification</dt>
            <dd>
              {assessment.period_classification?.replaceAll("_", " ") ??
                "Unresolved"}
            </dd>
            <dt>Shortening assessment</dt>
            <dd>
              {assessment.shortened_period?.replaceAll("_", " ") ??
                "Unresolved"}
            </dd>
          </dl>
          <p>
            The accounting reference date drives the timetable and can differ
            from the accounts period end. Separate original calendar evidence
            governs following-day adjustments.
          </p>
          {assessment.issues.length > 0 && (
            <ul aria-label="Unresolved ADGM timetable issues">
              {assessment.issues.map((issue) => (
                <li key={issue}>{issue.replaceAll("_", " ")}</li>
              ))}
            </ul>
          )}
          <p>
            {assessment.limitations ??
              "An assessed timetable does not establish a complete accounts or audit pack, an external filing or professional qualification."}
          </p>
        </>
      )}
    </section>
  );
}

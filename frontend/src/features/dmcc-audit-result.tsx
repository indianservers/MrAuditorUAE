export type DMCCAssessment = {
  profile: string;
  state: string;
  procedure_required: boolean | null;
  accounts_required?: boolean | null;
  audit_required?: boolean | null;
  group_accounts_required?: boolean | null;
  procedure?: string;
  legal_form?: string;
  approved_auditor_rule?: string;
  assessed_on?: string;
  issues: string[];
  limitations?: string;
};

function determination(value: boolean | null | undefined) {
  return value === true
    ? "Required on assessed facts"
    : value === false
      ? "Not required on assessed facts"
      : "Unresolved";
}

export function DMCCAuditResult({
  assessment,
  available,
  freshness,
}: {
  assessment?: DMCCAssessment | null;
  available: boolean;
  freshness?: string;
}) {
  return (
    <section aria-label="DMCC authority procedure assessment">
      <h3>DMCC authority procedure assessment</h3>
      {!available || !assessment ? (
        <p role="status">
          The current-version DMCC assessment could not yet be verified. No
          requirement or exemption is inferred.
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
              Reassess the retained source documents before relying on this
              procedure assessment.
            </p>
          )}
          <dl>
            <dt>Procedure</dt>
            <dd>
              {assessment.procedure?.replaceAll("_", " ") ?? "Unresolved"}
            </dd>
            <dt>Legal form</dt>
            <dd>
              {assessment.legal_form?.replaceAll("_", " ") ?? "Unresolved"}
            </dd>
            <dt>Selected procedure</dt>
            <dd>{determination(assessment.procedure_required)}</dd>
            <dt>Individual accounts</dt>
            <dd>{determination(assessment.accounts_required)}</dd>
            <dt>Audit of accounts</dt>
            <dd>{determination(assessment.audit_required)}</dd>
            <dt>Group accounts</dt>
            <dd>{determination(assessment.group_accounts_required)}</dd>
            <dt>Auditor requirement assessment</dt>
            <dd>
              {assessment.approved_auditor_rule?.replaceAll("_", " ") ??
                "Unresolved"}
            </dd>
          </dl>
          {assessment.issues.length > 0 && (
            <ul aria-label="Unresolved DMCC assessment issues">
              {assessment.issues.map((issue) => (
                <li key={issue}>{issue.replaceAll("_", " ")}</li>
              ))}
            </ul>
          )}
          <p>
            {assessment.limitations ??
              "Original evidence and a separate professional assessment are required."}
          </p>
          <p>
            This authority procedure is separate from the UAE corporate-tax
            audit threshold. No audit opinion or external submission is
            produced.
          </p>
        </>
      )}
    </section>
  );
}

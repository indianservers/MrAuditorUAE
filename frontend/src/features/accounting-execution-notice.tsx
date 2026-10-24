type AccountingReceipt = {
  source_completeness?: string;
  framework?: string;
  functional_currency?: string;
  presentation_currency?: string;
  unresolved_issues?: {
    code: string;
    remediation?: string;
    reference?: string;
  }[];
};

export function AccountingExecutionNotice({
  receipt,
}: {
  receipt?: AccountingReceipt;
}) {
  if (!receipt)
    return (
      <p role="status">
        Historical run: regenerate to retain the accounting execution receipt.
      </p>
    );
  return (
    <aside
      aria-label="Accounting execution controls"
      className="workbench-body"
    >
      <strong>At calculation: draft · journals not posted</strong>
      <p>
        {receipt.framework} · functional {receipt.functional_currency} ·
        presentation {receipt.presentation_currency}. Source completeness:{" "}
        {receipt.source_completeness?.replaceAll("_", " ")}. Approved input
        assumptions and calculation review are separate. Proposed adjustments
        require independent approval. See package history for subsequent
        approvals.
      </p>
      {!!receipt.unresolved_issues?.length && (
        <ul>
          {receipt.unresolved_issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              {issue.code.replaceAll("_", " ")}
              {issue.reference ? ` (${issue.reference})` : ""}:{" "}
              {issue.remediation}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

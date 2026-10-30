export type ADGMFilingDutyAssessment = {
  procedure: string;
  filing_required: boolean | null;
  chapter_8_applies: boolean | null;
  unlimited_company_exemption: boolean | null;
  dormant_individual_accounts_exemption: boolean | null;
  supporting_documents_required: boolean | null;
  reason: string;
  missing_criteria: string[];
  checks: {
    key: string;
    answer: string;
    evidence_ids: string[];
    assessment: string;
  }[];
  supporting_documents: {
    key: string;
    title: string;
    delivery_assessment: string;
  }[];
  limitations: string;
};

function determination(value: boolean | null) {
  return value === true
    ? "Assessed yes"
    : value === false
      ? "Assessed no"
      : "Unresolved";
}

export function ADGMFilingDutyResult({
  assessment,
}: {
  assessment: ADGMFilingDutyAssessment;
}) {
  return (
    <section aria-label="ADGM filing duty conditions">
      <h4>ADGM filing duty conditions</h4>
      <p>
        Selected procedure: {assessment.procedure.replaceAll("_", " ")}.{" "}
        {assessment.reason.replaceAll("_", " ")}.
      </p>
      <dl>
        <dt>Chapter 8 applies</dt>
        <dd>{determination(assessment.chapter_8_applies)}</dd>
        <dt>Unlimited-company filing exemption</dt>
        <dd>{determination(assessment.unlimited_company_exemption)}</dd>
        <dt>Dormant subsidiary individual-accounts exemption</dt>
        <dd>
          {determination(assessment.dormant_individual_accounts_exemption)}
        </dd>
        <dt>Separate supporting-document filing duty</dt>
        <dd>{determination(assessment.supporting_documents_required)}</dd>
      </dl>
      {assessment.supporting_documents_required === true && (
        <>
          <p>
            Individual-accounts exemption does not remove the five
            supporting-document filings. Delivery and timeliness need their own
            retained evidence.
          </p>
          <ol aria-label="Dormant subsidiary supporting documents">
            {assessment.supporting_documents.map((item) => (
              <li key={item.key}>
                {item.title}: {item.delivery_assessment.replaceAll("_", " ")}
              </li>
            ))}
          </ol>
        </>
      )}
      {assessment.missing_criteria.length > 0 && (
        <p>
          {assessment.missing_criteria.length} relevant conditions remain
          unassessed. A separately established filing requirement or exemption
          can be decisive; review the stated outcome and issues.
        </p>
      )}
      <details>
        <summary>
          Review source-bound filing-duty conditions ({assessment.checks.length}
          )
        </summary>
        <p>
          Unlimited-company exclusions cover the accounting reference period.
          Dormant-subsidiary conditions cover the financial year. Each source is
          retained separately from the authority rules.
        </p>
        <ol aria-label="Retained filing duty checks">
          {assessment.checks.map((check) => (
            <li key={check.key}>
              <p>
                <strong>{check.key.replaceAll("_", " ")}</strong>:{" "}
                {check.answer.replaceAll("_", " ")}
              </p>
              <p>{check.assessment}</p>
              <p style={{ overflowWrap: "anywhere" }}>
                Original evidence:{" "}
                {check.evidence_ids.join(", ") || "Not retained"}
              </p>
            </li>
          ))}
        </ol>
      </details>
      <p>{assessment.limitations}</p>
    </section>
  );
}

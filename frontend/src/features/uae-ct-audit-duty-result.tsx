const ISSUES: Record<string, string> = {
  TAXABLE_PERSON_CLASSIFICATION_CONFLICT:
    "Taxable-person and group/free-zone classifications conflict.",
  TAXABLE_PERSON_UNASSESSED: "Taxable-person status has not been assessed.",
  SEPARATE_TAX_GROUP_AND_QFZP_ELIGIBILITY_REVIEW_REQUIRED:
    "Tax Group and qualifying free-zone classifications need a separate eligibility review.",
  TAX_GROUP_STATUS_UNASSESSED: "Tax Group status has not been assessed.",
  RESIDENCY_UNASSESSED_FOR_REVENUE_TEST:
    "Residency has not been assessed for the revenue test.",
  ASSESSED_REVENUE_BASIS_REQUIRED_FOR_RESIDENCY:
    "The revenue basis does not establish the required resident or UAE permanent-establishment/nexus scope.",
  COMPLETE_TAX_PERIOD_AED_REVENUE_MISSING:
    "Complete tax-period revenue in AED is missing.",
  QUALIFYING_FREE_ZONE_PERSON_STATUS_UNASSESSED:
    "Qualifying free-zone-person status has not been assessed.",
  OPERATIVE_RULE_CHANGES_UNRESOLVED:
    "Changes to the operative rules remain unresolved.",
};

const STATEMENTS: Record<string, string> = {
  AUDITED_SPECIAL_PURPOSE_FINANCIAL_STATEMENTS:
    "Audited special-purpose financial statements for the Tax Group",
  AUDITED_FINANCIAL_STATEMENTS: "Audited financial statements",
  OUTSIDE_ASSESSED_TAXABLE_PERSON_SCOPE:
    "Outside the assessed taxable-person scope",
  NO_MD84_AUDIT_DUTY_ON_ASSESSED_FACTS:
    "No MD84 audit duty on the assessed facts",
  AUDIT_REQUIRED_STATEMENT_TYPE_UNRESOLVED:
    "Audit required; statement type unresolved",
  TAX_GROUP_AND_QFZP_CLASSIFICATIONS_REQUIRE_REVIEW:
    "Tax Group and qualifying free-zone classifications require review",
  UNRESOLVED: "Unresolved",
};

const BASES: Record<string, string> = {
  whole_person: "Whole taxable person",
  uae_pe_and_nexus: "UAE permanent establishment and nexus only",
  NOT_NEEDED_FOR_SELECTED_BRANCH: "Not needed for the selected branch",
  UNRESOLVED: "Unresolved",
};

function duty(value: unknown) {
  return value === true
    ? "Required"
    : value === false
      ? "Not required under the selected MD84 assessment"
      : "Unresolved";
}

export function UAECTAuditDutyResult({
  row,
}: {
  row?: Record<string, unknown>;
}) {
  if (!row) return null;
  const issues = Array.isArray(row.issues)
    ? row.issues.filter((value): value is string => typeof value === "string")
    : [];
  const amount = row.revenue_aed;
  return (
    <section
      aria-label="UAE corporate-tax audit duty summary"
      className="main-panel"
      style={{ padding: 16, marginBottom: 16 }}
    >
      <h3>Corporate-tax audited statement duty</h3>
      <p>
        <strong>
          MD84 preparation and maintenance duty:{" "}
          {duty(row.audited_financial_statements_required)}
        </strong>
      </p>
      <dl>
        <dt>Registration reference</dt>
        <dd>{String(row.registration ?? "Not supplied")}</dd>
        <dt>Assessed tax period</dt>
        <dd>
          {String(row.period_start ?? "Not supplied")} to{" "}
          {String(row.period_end ?? "Not supplied")}
        </dd>
        <dt>Dated source assessment</dt>
        <dd>{duty(row.dated_source_requirement)}</dd>
        <dt>Statement branch</dt>
        <dd>
          {STATEMENTS[String(row.statement_type)] ??
            "Unresolved statement type"}
        </dd>
        <dt>Assessed revenue</dt>
        <dd>
          {amount === null || amount === undefined || amount === ""
            ? "Not established"
            : `AED ${String(amount)}`}
        </dd>
        <dt>Revenue basis</dt>
        <dd>{BASES[String(row.threshold_basis)] ?? "Unresolved"}</dd>
        <dt>Revenue strictly exceeds AED50,000,000</dt>
        <dd>
          {row.revenue_exceeds_threshold === true
            ? "Yes"
            : row.revenue_exceeds_threshold === false
              ? "No"
              : "Not determined for this branch"}
        </dd>
      </dl>
      {issues.length > 0 && (
        <ul aria-label="Unresolved corporate-tax duty issues">
          {issues.map((issue, index) => (
            <li key={`${index}:${issue}`}>{ISSUES[issue] ?? issue}</li>
          ))}
        </ul>
      )}
      {row.tax_group_procedures ===
        "SEPARATE_FTA_FORM_FRAMEWORK_AND_SUBMISSION_REQUIREMENTS" && (
        <p>
          Tax Group forms, aggregation, special-purpose audit and submission
          need their separate authority requirements. This duty assessment does
          not complete them.
        </p>
      )}
      {row.additional_qfzp_procedures ===
        "SEPARATE_AUTHORITY_PROCEDURES_REQUIRE_ASSESSMENT" && (
        <p>
          Additional designated-zone distribution procedures need separate
          assessment.
        </p>
      )}
      {row.additional_qfzp_procedures ===
        "DESIGNATED_DISTRIBUTION_SCOPE_UNASSESSED" && (
        <p>Designated-zone distribution scope has not been assessed.</p>
      )}
      <p>
        Company-law and free-zone audit exemptions are not established by this
        assessment. No audit opinion, statutory issuance or filing is
        established.
      </p>
    </section>
  );
}

"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

const CONTRACT = "uae-ccl-accounts-articles26-27/1";
const LAW = "b08a904a9af7102804e96e70c77a975876f3f2705190ecb6bea4f39d533435af";
const AMENDMENT =
  "7e035b6c3616255ffe8f1c4326080bec3f270f165aa63eeb06ab4c1f481e7163";
type Evidence = {
  id: string;
  label: string;
  scan_status: string;
  sha256?: string;
};
const FLAGS = [
  "holding_company",
  "selected_year_is_last_audited",
  "accounts_copy_delivered",
  "auditor_report_copy_delivered",
  "group_accounts_copy_delivered",
];
const DATES = [
  "fiscal_year_start",
  "fiscal_year_end",
  "assessed_on",
  "adopted_from",
  "adopted_through",
  "amendment_publication_date",
  "request_received_on",
  "responded_on",
];
const OPTIONAL_DATES = new Set([
  "amendment_publication_date",
  "request_received_on",
  "responded_on",
]);
const LABELS: Record<string, string> = {
  label: "Company accounts assessment title",
  registration_reference: "Company registration reference",
  fiscal_year_start: "Company fiscal year start",
  fiscal_year_end: "Company fiscal year end",
  assessed_on: "Company assessed on",
  adopted_from: "Company rule adopted from",
  adopted_through: "Company rule adopted through",
  amendment_publication_date: "Declared amendment publication date",
  request_received_on: "Written request received on",
  responded_on: "Response delivered on",
  rule_adoption_assessment: "Company operative source-chain assessment",
  scope_assessment: "Company-law applicability and exclusions assessment",
  fact_assessment: "Company and request evidence assessment",
  counting_assessment: "Written request day-counting assessment",
  holding_company: "Holding company assessed",
  selected_year_is_last_audited: "Selected year is last audited accounts",
  accounts_copy_delivered: "Accounts copy delivered",
  auditor_report_copy_delivered: "Auditor report copy delivered",
  group_accounts_copy_delivered: "Group accounts copy delivered",
};
const SELECTS: [string, string, [string, string][]][] = [
  [
    "rule_chain_status",
    "Company source-chain status",
    [
      ["unresolved", "Unresolved"],
      ["assessed_adopted", "Independently assessed for the exact period"],
    ],
  ],
  [
    "other_rule_changes",
    "Company other operative changes",
    [
      ["unresolved", "Unresolved"],
      ["assessed_none", "Assessed: no other operative changes"],
    ],
  ],
  [
    "law_scope",
    "Company-law applicability",
    [
      ["unresolved", "Unresolved"],
      ["assessed_applies", "Assessed: applies for the whole fiscal year"],
      ["assessed_excluded", "Assessed: excluded from this law's scope"],
    ],
  ],
  [
    "fiscal_year_validity",
    "Company fiscal year validity",
    [
      ["unassessed", "Unassessed"],
      ["assessed_valid", "Independently assessed as valid"],
    ],
  ],
  [
    "legal_form",
    "Assessed company legal form",
    [
      ["unassessed", "Unassessed"],
      ["limited_liability", "Limited liability company"],
      ["public_joint_stock", "Public joint stock company"],
      ["private_joint_stock", "Private joint stock company"],
      ["general_partnership", "General partnership"],
      ["limited_partnership", "Limited partnership"],
    ],
  ],
  [
    "request_population",
    "Company written request population",
    [
      ["unassessed", "Unassessed"],
      ["assessed_none", "Independently assessed: no written requests"],
      ["written_request", "One retained written request"],
    ],
  ],
  [
    "requester_eligibility",
    "Written requester eligibility",
    [
      ["unassessed", "Unassessed"],
      ["assessed_partner_or_shareholder", "Assessed partner or shareholder"],
      ["assessed_other", "Assessed: other requester"],
    ],
  ],
  [
    "response_counting",
    "Written request counting basis",
    [
      ["unassessed", "Unassessed"],
      [
        "assessed_calendar_days_excluding_receipt",
        "Independently adopted calendar days, excluding receipt day",
      ],
    ],
  ],
  [
    "response_status",
    "Company response status",
    [
      ["unassessed", "Unassessed"],
      ["assessed_responded", "Assessed: response delivered"],
      ["assessed_not_responded", "Assessed: not responded"],
    ],
  ],
];

export function UAECompanyAccounts({
  eid,
  evidence,
  onCreated,
}: {
  eid: string;
  evidence: Evidence[];
  onCreated: (id: string) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => ({
    ...Object.fromEntries(
      SELECTS.map(([key, , options]) => [key, options[0][0]]),
    ),
    ...Object.fromEntries(FLAGS.map((key) => [key, "unassessed"])),
  }));
  const [sources, setSources] = useState<Record<string, string>>({});
  const action = useAction<{ id: string }>();
  const change = (key: string, value: string) =>
    setValues({ ...values, [key]: value });
  const clean = evidence.filter((e) => e.scan_status === "CLEAN" && e.sha256);
  const adoption = clean.find((e) => e.id === sources.adoption);
  const facts = clean.find((e) => e.id === sources.facts);
  const disabled =
    !["law", "amendment", "adoption", "facts"].every((key) => sources[key]) ||
    !adoption?.sha256 ||
    !facts?.sha256 ||
    ![
      "label",
      "registration_reference",
      "fiscal_year_start",
      "fiscal_year_end",
      "assessed_on",
      "adopted_from",
      "adopted_through",
      "rule_adoption_assessment",
      "scope_assessment",
      "fact_assessment",
    ].every((key) => values[key]?.trim()) ||
    action.isPending;
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>
        Assess UAE company-law accounts and written-request duties
      </summary>
      <p>
        Use the exact completed fiscal year, the original Ministry-hosted PDFs,
        separate legal adoption and separate company facts. The English law PDF
        is marked unofficial translation. Publication, amendments, exclusions
        and applicability need an independently retained assessment. This
        procedure is separate from corporate-tax thresholds and free-zone audit
        rules.
      </p>
      <ErrorState error={action.error} />
      {["label", "registration_reference"].map((key) => (
        <label key={key}>
          {LABELS[key]}
          <input
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {DATES.map((key) => (
        <label key={key}>
          {LABELS[key]}
          {OPTIONAL_DATES.has(key) ? " (leave blank if not established)" : ""}
          <input
            type="date"
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {SELECTS.map(([key, label, options]) => (
        <label key={key}>
          {label}
          <select
            aria-label={label}
            value={values[key]}
            onChange={(e) => change(key, e.target.value)}
          >
            {options.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
      ))}
      {FLAGS.map((key) => (
        <label key={key}>
          {LABELS[key]}
          <select
            aria-label={LABELS[key]}
            value={values[key]}
            onChange={(e) => change(key, e.target.value)}
          >
            <option value="unassessed">Unassessed</option>
            <option value="assessed_yes">Assessed yes</option>
            <option value="assessed_no">Assessed no</option>
          </select>
        </label>
      ))}
      {[
        "rule_adoption_assessment",
        "scope_assessment",
        "fact_assessment",
        "counting_assessment",
      ].map((key) => (
        <label key={key}>
          {LABELS[key]}
          <textarea
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {[
        ["law", "Original Ministry-hosted unofficial English law PDF"],
        ["amendment", "Original Arabic company-law amendment PDF"],
        ["adoption", "Separate company-law operative adoption evidence"],
        ["facts", "Separate company and request facts"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <select
            aria-label={label}
            value={sources[key] || ""}
            onChange={(e) => setSources({ ...sources, [key]: e.target.value })}
          >
            <option value="">Select retained clean evidence</option>
            {clean
              .filter((e) =>
                key === "law"
                  ? e.sha256 === LAW
                  : key === "amendment"
                    ? e.sha256 === AMENDMENT
                    : e.sha256 !== LAW &&
                      e.sha256 !== AMENDMENT &&
                      !Object.entries(sources).some(
                        ([other, id]) => other !== key && id === e.id,
                      ),
              )
              .map((e) => (
                <option key={e.id} value={e.id}>
                  {e.label}
                </option>
              ))}
          </select>
        </label>
      ))}
      <Button
        disabled={disabled}
        onClick={async () => {
          const result = await action.mutateAsync({
            path: `intelligence/engagements/${eid}/uae-company-accounts-duty`,
            body: {
              profile: CONTRACT,
              ...values,
              ...Object.fromEntries(
                DATES.map((key) => [key, values[key] || null]),
              ),
              counting_assessment: values.counting_assessment || "",
              law_evidence_version_id: sources.law,
              amendment_evidence_version_id: sources.amendment,
              adoption_evidence_version_id: sources.adoption,
              adoption_sha256: adoption!.sha256,
              fact_evidence_version_id: sources.facts,
              fact_sha256: facts!.sha256,
            },
          });
          onCreated(result.id);
        }}
      >
        Prepare company-law accounts assessment
      </Button>
    </details>
  );
}

function assessed(value: unknown) {
  return value === true
    ? "Required"
    : value === false
      ? "Not required by this assessment"
      : "Unresolved";
}
export function UAECompanyAccountsResult({
  row,
}: {
  row?: Record<string, unknown>;
}) {
  if (!row) return null;
  return (
    <section
      aria-label="UAE company-law accounts summary"
      className="main-panel"
      style={{ padding: 16, marginBottom: 16 }}
    >
      <h3>Company-law accounts and written-request duties</h3>
      <p>
        {String(row.registration ?? "Not supplied")} ·{" "}
        {String(row.period_start ?? "")} to {String(row.period_end ?? "")}
      </p>
      <dl>
        <dt>Annual accounts</dt>
        <dd>{assessed(row.annual_accounts_required)}</dd>
        <dt>Annual audit</dt>
        <dd>{assessed(row.annual_audit_required)}</dd>
        <dt>Accounting registers</dt>
        <dd>{assessed(row.accounting_registers_required)}</dd>
        <dt>Minimum register retention</dt>
        <dd>
          {row.minimum_register_retention_years === 5
            ? "At least five years from fiscal year end; additional retention rules need separate assessment"
            : "Not determined"}
        </dd>
        <dt>Written-request response</dt>
        <dd>{assessed(row.response_required)}</dd>
        <dt>Response deadline under assessed counting</dt>
        <dd>{String(row.response_deadline ?? "Not determined")}</dd>
        <dt>Required response copies complete</dt>
        <dd>
          {row.response_complete === true
            ? "Assessed complete"
            : row.response_complete === false
              ? "Not complete"
              : "Unresolved"}
        </dd>
        <dt>Response timing observation</dt>
        <dd>
          {String(row.response_timing ?? "Unresolved source chain").replaceAll(
            "_",
            " ",
          )}
        </dd>
        <dt>Group accounts copy required</dt>
        <dd>{assessed(row.group_accounts_copy_required)}</dd>
      </dl>
      {Array.isArray(row.issues) && row.issues.length > 0 && (
        <ul aria-label="Unresolved company-law procedures">
          {row.issues.map((issue, index) => (
            <li key={index}>{String(issue).replaceAll("_", " ")}</li>
          ))}
        </ul>
      )}
      <p>
        This assessment does not establish a general audit exemption, complete
        retention policy, valid fiscal year, audited accounts, opinion or
        filing.
      </p>
    </section>
  );
}

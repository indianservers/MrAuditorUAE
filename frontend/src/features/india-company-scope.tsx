"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

const FLAGS = [
  ["is_indian_company", "Indian incorporated company"],
  ["is_foreign_company", "Foreign company"],
  ["is_private_company", "Private company"],
  ["is_public_company", "Public company"],
  ["banking_company", "Banking company"],
  ["insurance_company", "Insurance company"],
  ["section8_company", "Section 8 company"],
  ["one_person_company", "One Person Company"],
  ["holding_or_subsidiary", "Holding or subsidiary of any company"],
  [
    "holding_or_subsidiary_of_public_company",
    "Holding or subsidiary of a public company",
  ],
  ["governed_by_special_act", "Governed by a special Act"],
  ["other_special_exemption_claimed", "Other exemption claimed"],
  ["financial_statements_filing_default", "Financial statement filing default"],
  ["annual_return_filing_default", "Annual return filing default"],
] as const;
const MONEY = [
  ["small_paid_up_capital", "Paid-up capital at balance sheet date (INR)"],
  [
    "preceding_financial_year_turnover",
    "Immediately preceding financial year turnover (INR)",
  ],
  [
    "caro_capital_reserves_and_surplus",
    "CARO paid-up capital, reserves and surplus (INR)",
  ],
  [
    "caro_max_bank_fi_borrowings",
    "Maximum bank and financial institution borrowings during year (INR)",
  ],
  [
    "caro_current_year_total_revenue",
    "Current year total revenue including discontinued operations (INR)",
  ],
  ["latest_audited_turnover", "Turnover per latest audited statements (INR)"],
  [
    "max_bank_fi_body_corporate_borrowings",
    "Maximum bank, financial institution and body corporate borrowings (INR)",
  ],
] as const;
const DATES = [
  ["financial_period_start", "India financial period start"],
  ["financial_period_end", "India financial period end"],
  ["report_date", "India report assessment date"],
  ["adopted_from", "India rules adopted from"],
  ["adopted_through", "India rules adopted through"],
] as const;
const ROLES = [
  ["companies_act", "Companies Act original PDF"],
  ["small_company_amendment", "GSR 880(E) small-company original PDF"],
  ["caro_order", "CARO 2020 original order PDF"],
  ["caro_commencement", "SO 4588(E) CARO commencement original PDF"],
  ["ifc_notification", "GSR 583(E) IFC original PDF"],
  ["ifc_corrigendum", "SO 2218(E) IFC corrigendum original PDF"],
  ["legal_adoption", "Separate India legal adoption evidence"],
  ["company_facts", "Separate India company facts evidence"],
] as const;
type Evidence = {
  id: string;
  label: string;
  scan_status: string;
  sha256?: string;
};

export function IndiaCompanyScope({
  eid,
  evidence,
  onCreated,
}: {
  eid: string;
  evidence: Evidence[];
  onCreated: (id: string) => void;
}) {
  const action = useAction<{ id: string }>();
  const [values, setValues] = useState<Record<string, string>>({
    statement_scope: "standalone",
    source_chain_status: "unresolved",
    other_operative_changes: "unresolved",
  });
  const [sources, setSources] = useState<Record<string, string>>({});
  const change = (key: string, value: string) =>
    setValues((previous) => ({ ...previous, [key]: value }));
  const clean = evidence.filter(
    (e) => e.scan_status.toUpperCase() === "CLEAN" && e.sha256,
  );
  const selected = ROLES.map(([role]) => ({
    role,
    source: clean.find((e) => e.id === sources[role]),
  }));
  const required = [
    "label",
    "entity_reference",
    "facts_assessment",
    "legal_adoption_assessment",
    ...DATES.map(([key]) => key),
  ];
  const disabled =
    action.isPending ||
    required.some((key) => !values[key]?.trim()) ||
    selected.some((d) => !d.source) ||
    new Set(selected.map((d) => d.source?.sha256)).size !== 8;
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>
        Assess India company audit, CARO and IFC reporting scope
      </summary>
      <p>
        Keep the Companies Act audit duty, CARO and IFC reporting separate.
        Blank amounts and unassessed facts remain unresolved. Use eight separate
        retained sources, including the IFC corrigendum. Review establishes a
        workpaper assessment; it does not issue an audit opinion or authenticate
        the source law.
      </p>
      <ErrorState error={action.error} />
      {[
        ["label", "India scope assessment title"],
        ["entity_reference", "India company registration reference"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {DATES.map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            type="date"
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      <label>
        India statement scope
        <select
          value={values.statement_scope}
          onChange={(e) => change("statement_scope", e.target.value)}
        >
          <option value="standalone">Standalone</option>
          <option value="consolidated">
            Consolidated; assess CARO paragraph 3(xxi) separately
          </option>
        </select>
      </label>
      {FLAGS.map(([key, label]) => (
        <label key={key}>
          {label}
          <select
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          >
            <option value="">Unassessed</option>
            <option value="yes">Assessed yes</option>
            <option value="no">Assessed no</option>
          </select>
        </label>
      ))}
      {MONEY.map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            inputMode="decimal"
            placeholder="Blank means unassessed"
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      <label>
        India operative source chain
        <select
          value={values.source_chain_status}
          onChange={(e) => change("source_chain_status", e.target.value)}
        >
          <option value="unresolved">Unresolved</option>
          <option value="independently_assessed">
            Independently assessed for this period
          </option>
        </select>
      </label>
      <label>
        India other operative changes
        <select
          value={values.other_operative_changes}
          onChange={(e) => change("other_operative_changes", e.target.value)}
        >
          <option value="unresolved">Unresolved</option>
          <option value="assessed_none">Assessed: no other changes</option>
        </select>
      </label>
      {[
        ["facts_assessment", "India company facts assessment"],
        [
          "legal_adoption_assessment",
          "India legal source-chain adoption assessment",
        ],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <textarea
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {ROLES.map(([role, label]) => (
        <label key={role}>
          {label}
          <select
            value={sources[role] || ""}
            onChange={(e) =>
              setSources((previous) => ({
                ...previous,
                [role]: e.target.value,
              }))
            }
          >
            <option value="">Select separate clean retained evidence</option>
            {clean
              .filter(
                (e) =>
                  !selected.some(
                    (d) => d.role !== role && d.source?.sha256 === e.sha256,
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
            path: `intelligence/engagements/${eid}/india-company-reporting-scope`,
            body: {
              profile: "india-company-reporting-scope/1",
              label: values.label,
              adopted_from: values.adopted_from,
              adopted_through: values.adopted_through,
              source_chain_status: values.source_chain_status,
              other_operative_changes: values.other_operative_changes,
              legal_adoption_assessment: values.legal_adoption_assessment,
              facts: {
                country: "IN",
                entity_reference: values.entity_reference,
                financial_period_start: values.financial_period_start,
                financial_period_end: values.financial_period_end,
                report_date: values.report_date,
                statement_scope: values.statement_scope,
                facts_assessment: values.facts_assessment,
                ...Object.fromEntries(
                  FLAGS.map(([key]) => [
                    key,
                    values[key] === "yes"
                      ? true
                      : values[key] === "no"
                        ? false
                        : null,
                  ]),
                ),
                ...Object.fromEntries(
                  MONEY.map(([key]) => [key, values[key]?.trim() || null]),
                ),
              },
              documents: selected.map(({ role, source }) => ({
                role,
                evidence_version_id: source!.id,
                sha256: source!.sha256,
              })),
            },
          });
          onCreated(result.id);
        }}
      >
        Prepare India reporting scope assessment
      </Button>
    </details>
  );
}

export function IndiaCompanyScopeResult({
  row,
}: {
  row?: Record<string, unknown>;
}) {
  if (!row) return null;
  return (
    <section
      aria-label="India company reporting scope summary"
      className="main-panel"
      style={{ padding: 16 }}
    >
      <h3>India company reporting scope</h3>
      <p>
        {String(row.entity_reference)} · {String(row.period_start)} to{" "}
        {String(row.period_end)}
      </p>
      <dl>
        {[
          ["small_company", "Small-company classification"],
          ["companies_act_section139_audit", "Companies Act section 139 audit"],
          ["caro2020_applies", "CARO 2020 applies"],
          ["caro_full_standalone_matters", "CARO standalone matters"],
          [
            "caro_consolidated_paragraph3_xxi",
            "CARO consolidated paragraph 3(xxi)",
          ],
          ["section143_3_i_ifc_reporting", "Section 143(3)(i) IFC reporting"],
        ].map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>
              {row[key] === true
                ? "Yes, within assessed scope"
                : row[key] === false
                  ? "No, within assessed scope"
                  : "Unresolved"}
            </dd>
          </div>
        ))}
      </dl>
      <p>
        Review does not establish audit completion, an exemption from every
        audit regime, or authority to issue a statutory report.
      </p>
    </section>
  );
}

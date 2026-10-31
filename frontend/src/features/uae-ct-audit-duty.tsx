"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Evidence = {
  id: string;
  label: string;
  scan_status: string;
  sha256?: string;
};
const FLAGS = [
  "taxable_person",
  "tax_group",
  "qualifying_free_zone_person",
  "designated_zone_distribution",
] as const;
const DATES = [
  "tax_period_start",
  "tax_period_end",
  "assessed_on",
  "adopted_from",
  "adopted_through",
] as const;
export function UAECTAuditDuty({
  eid,
  evidence,
  onCreated,
}: {
  eid: string;
  evidence: Evidence[];
  onCreated: (id: string) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({
    taxable_person: "unassessed",
    tax_group: "unassessed",
    qualifying_free_zone_person: "unassessed",
    designated_zone_distribution: "unassessed",
    residency: "unassessed",
    revenue_basis: "unassessed",
    other_rule_changes: "unresolved",
  });
  const [rule, setRule] = useState("");
  const [facts, setFacts] = useState("");
  const action = useAction<{ id: string }>();
  const change = (key: string, value: string) =>
    setValues({ ...values, [key]: value });
  const clean = evidence.filter((e) => e.scan_status === "CLEAN" && e.sha256);
  const fact = clean.find((e) => e.id === facts);
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>Assess UAE corporate-tax audited statement duty</summary>
      <p>
        Use the original MD84 of 2025 and separate retained entity facts for a
        completed tax period commencing from 1 January 2025. Earlier periods
        need their separate MD82 source. This checks corporate-tax preparation
        and maintenance duty; company-law and free-zone audit duties remain
        separate.
      </p>
      <ErrorState error={action.error} />
      {[
        ["label", "CT audit duty title"],
        ["registration_reference", "CT registration reference"],
        ["revenue_aed", "Assessed complete-period AED revenue"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      <p>
        Leave unknown revenue blank. A recorded zero is different. For a
        non-resident, use only revenue derived through UAE permanent
        establishments and/or nexus, assessed in AED.
      </p>
      {DATES.map((key) => (
        <label key={key}>
          CT {key.replaceAll("_", " ")}
          <input
            type="date"
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      {FLAGS.map((key) => (
        <label key={key}>
          CT {key.replaceAll("_", " ")}
          <select
            value={values[key]}
            onChange={(e) => change(key, e.target.value)}
          >
            <option value="unassessed">Unassessed</option>
            <option value="assessed_yes">Assessed yes</option>
            <option value="assessed_no">Assessed no</option>
          </select>
        </label>
      ))}
      <label>
        CT residency
        <select
          value={values.residency}
          onChange={(e) => change("residency", e.target.value)}
        >
          <option value="unassessed">Unassessed</option>
          <option value="resident">Resident</option>
          <option value="non_resident">Non-resident</option>
        </select>
      </label>
      <label>
        CT revenue basis
        <select
          value={values.revenue_basis}
          onChange={(e) => change("revenue_basis", e.target.value)}
        >
          <option value="unassessed">Unassessed</option>
          <option value="whole_person">Whole-person revenue</option>
          <option value="uae_pe_and_nexus">UAE PE and nexus revenue</option>
        </select>
      </label>
      <label>
        CT other rule changes
        <select
          value={values.other_rule_changes}
          onChange={(e) => change("other_rule_changes", e.target.value)}
        >
          <option value="unresolved">Unresolved</option>
          <option value="assessed_none">Assessed no operative change</option>
        </select>
      </label>
      <label>
        Original MD84 rule PDF
        <select value={rule} onChange={(e) => setRule(e.target.value)}>
          <option value="">Select clean original rule evidence</option>
          {clean.map((e) => (
            <option key={e.id} value={e.id}>
              {e.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Separate CT period and classification facts
        <select value={facts} onChange={(e) => setFacts(e.target.value)}>
          <option value="">Select separate clean fact evidence</option>
          {clean
            .filter((e) => e.id !== rule)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
        </select>
      </label>
      {[
        ["rule_adoption_assessment", "CT operative rule assessment"],
        ["fact_assessment", "CT entity and revenue assessment"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <textarea
            value={values[key] || ""}
            onChange={(e) => change(key, e.target.value)}
          />
        </label>
      ))}
      <Button
        disabled={
          action.isPending ||
          !rule ||
          !fact ||
          !values.label ||
          !values.registration_reference ||
          DATES.some((k) => !values[k]) ||
          (values.rule_adoption_assessment || "").trim().length < 10 ||
          (values.fact_assessment || "").trim().length < 10
        }
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/uae-ct-audit-duty`,
              body: {
                ...values,
                profile: "uae-ct-audited-statements-md84-2025/1",
                currency: "AED",
                revenue_aed: values.revenue_aed?.trim() || null,
                rule_evidence_version_id: rule,
                fact_evidence_version_id: facts,
                fact_sha256: fact!.sha256,
              },
            });
            onCreated(result.id);
          } catch {
            /* Server error remains visible above. */
          }
        }}
      >
        Prepare CT audited statement duty
      </Button>
    </details>
  );
}

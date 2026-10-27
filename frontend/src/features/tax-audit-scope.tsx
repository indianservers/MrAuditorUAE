"use client";

import { Button, ErrorState } from "@/components/ui/primitives";
import { useAPI } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";

export type TaxAuditScope = {
  applicability_id: string;
  tax_period_start: string;
  tax_period_end: string;
  audited_under_other_law: boolean;
  form: "3CA-3CD" | "3CB-3CD" | "26";
  audit_report_part: "C" | "D" | null;
};
export type TaxScopeDraft = Omit<
  TaxAuditScope,
  "audited_under_other_law" | "form"
> & {
  audited_under_other_law: boolean | null;
  form: TaxAuditScope["form"] | "";
};
export const emptyTaxScope: TaxScopeDraft = {
  applicability_id: "",
  tax_period_start: "",
  tax_period_end: "",
  audited_under_other_law: null,
  form: "",
  audit_report_part: null,
};
export function selectedTaxScope(value: TaxScopeDraft): TaxAuditScope {
  if (
    !value.applicability_id ||
    !value.tax_period_start ||
    !value.tax_period_end ||
    value.audited_under_other_law === null ||
    !value.form
  )
    throw new Error(
      "Select the reviewed applicability case, tax period, form and other-law audit basis",
    );
  if (value.form === "26" && !value.audit_report_part)
    throw new Error("Select Form 26 audit-report Part C or D");
  return {
    ...value,
    audited_under_other_law: value.audited_under_other_law,
    form: value.form,
    audit_report_part: value.form === "26" ? value.audit_report_part : null,
  };
}

type CaseChoice = {
  id: string;
  label: string;
  kind: string;
  area?: string;
  review_status: string;
  freshness: string;
};
export function TaxAuditScopeForm({
  eid,
  value,
  onChange,
}: {
  eid: string;
  value: TaxScopeDraft;
  onChange: (scope: TaxScopeDraft) => void;
}) {
  const history = useEventHistory<CaseChoice>(
    `intelligence/engagements/${eid}`,
    !!eid,
  );
  const selected = useAPI<{
    id: string;
    kind: string;
    freshness: string;
    body: { area: string; title: string; review_status: string };
  }>(
    `intelligence/engagements/${eid}/events/${value.applicability_id}`,
    !!eid && !!value.applicability_id,
  );
  const options = (history.data?.items || []).filter(
    (item) =>
      item.kind === "statutory-checklist" &&
      item.area === "india-tax-audit" &&
      item.review_status === "REVIEWED" &&
      item.freshness === "CURRENT",
  );
  const retained = selected.data;
  if (
    retained?.kind === "statutory-checklist" &&
    retained.body.area === "india-tax-audit" &&
    retained.body.review_status === "REVIEWED" &&
    retained.freshness === "CURRENT" &&
    !options.some((item) => item.id === retained.id)
  )
    options.push({
      id: retained.id,
      label: retained.body.title,
      kind: retained.kind,
      area: retained.body.area,
      review_status: retained.body.review_status,
      freshness: retained.freshness,
    });
  return (
    <fieldset>
      <legend>India tax-audit scope</legend>
      <p>
        Select the tax period independently of the report creation date. It must
        be covered by the engagement financial period. Use an independently
        reviewed applicability case with retained period, form and other-law
        audit facts.
      </p>
      <ErrorState error={history.error || selected.error} />
      <label>
        Reviewed tax-audit applicability case
        <select
          value={value.applicability_id}
          onChange={(e) =>
            onChange({ ...value, applicability_id: e.target.value })
          }
        >
          <option value="">Select a current reviewed case</option>
          {options.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      {history.hasOlder && (
        <Button disabled={history.loadingOlder} onClick={history.loadOlder}>
          Load older applicability cases
        </Button>
      )}
      <label>
        Tax period start
        <input
          type="date"
          value={value.tax_period_start}
          onChange={(e) =>
            onChange({ ...value, tax_period_start: e.target.value })
          }
        />
      </label>
      <label>
        Tax period end
        <input
          type="date"
          value={value.tax_period_end}
          onChange={(e) =>
            onChange({ ...value, tax_period_end: e.target.value })
          }
        />
      </label>
      <label>
        Accounts audited under another law
        <select
          value={
            value.audited_under_other_law === null
              ? ""
              : value.audited_under_other_law
                ? "yes"
                : "no"
          }
          onChange={(e) =>
            onChange({
              ...value,
              audited_under_other_law:
                e.target.value === "" ? null : e.target.value === "yes",
            })
          }
        >
          <option value="">Select the assessed audit basis</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </label>
      <label>
        Selected tax-audit form
        <select
          value={value.form}
          onChange={(e) =>
            onChange({
              ...value,
              form: e.target.value as TaxScopeDraft["form"],
              audit_report_part: null,
            })
          }
        >
          <option value="">Select the assessed form</option>
          <option value="3CA-3CD">Legacy 3CA with 3CD</option>
          <option value="3CB-3CD">Legacy 3CB with 3CD</option>
          <option value="26">Form 26</option>
        </select>
      </label>
      {value.form === "26" && (
        <label>
          Form 26 audit-report part
          <select
            value={value.audit_report_part || ""}
            onChange={(e) =>
              onChange({
                ...value,
                audit_report_part: (e.target.value ||
                  null) as TaxAuditScope["audit_report_part"],
              })
            }
          >
            <option value="">Select the assessed report part</option>
            <option value="C">Part C — audited under another law</option>
            <option value="D">Part D — not audited under another law</option>
          </select>
        </label>
      )}
      <p>
        The period/form guard does not qualify every tax-audit clause or produce
        an official e-filing form. Generated outputs remain working drafts.
      </p>
    </fieldset>
  );
}

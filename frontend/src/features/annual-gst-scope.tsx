"use client";

export type AnnualGSTDraft = {
  enabled: boolean;
  pan: string;
  financial_year_start: string;
  financial_year_end: string;
  rule_review_date: string;
  taxpayer_type: string;
  aggregate_turnover: string;
  other_pan_turnover: string;
  pan_population_complete: boolean;
  assessment: string;
};

export const emptyAnnualGST = (): AnnualGSTDraft => ({
  enabled: false,
  pan: "",
  financial_year_start: "",
  financial_year_end: "",
  rule_review_date: "",
  taxpayer_type: "unknown",
  aggregate_turnover: "",
  other_pan_turnover: "",
  pan_population_complete: false,
  assessment: "",
});

export function annualGSTPayload(draft: AnnualGSTDraft) {
  const { enabled, ...scope } = draft;
  if (!enabled) return {};
  return {
    gst_annual_scope: {
      ...scope,
      aggregate_turnover:
        draft.aggregate_turnover === "" ? null : draft.aggregate_turnover,
      other_pan_turnover:
        draft.other_pan_turnover === "" ? null : draft.other_pan_turnover,
    },
  };
}

export function AnnualGSTScopeForm({
  value,
  onChange,
}: {
  value: AnnualGSTDraft;
  onChange: (value: AnnualGSTDraft) => void;
}) {
  const update = (key: keyof AnnualGSTDraft, next: string | boolean) =>
    onChange({ ...value, [key]: next });
  return (
    <fieldset>
      <legend>India annual GST applicability candidates</legend>
      <label>
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={(e) => update("enabled", e.target.checked)}
        />
        Assess GSTR-9 / GSTR-9C candidates with this turnover bridge
      </label>
      {value.enabled && (
        <>
          <p>
            FY 2024-25 and 2025-26 only. Use PAN-wide turnover, independently
            reviewed full-year registration populations and an explicit
            other-turnover control. Missing facts stay pending. These candidates
            do not establish filing, legal qualification or a mandatory CA
            certification.
          </p>
          <label>
            PAN
            <input
              value={value.pan}
              onChange={(e) => update("pan", e.target.value)}
            />
          </label>
          <label>
            Annual GST financial year start
            <input
              type="date"
              value={value.financial_year_start}
              onChange={(e) => update("financial_year_start", e.target.value)}
            />
          </label>
          <label>
            Annual GST financial year end
            <input
              type="date"
              value={value.financial_year_end}
              onChange={(e) => update("financial_year_end", e.target.value)}
            />
          </label>
          <label>
            Annual GST rule review date
            <input
              type="date"
              value={value.rule_review_date}
              onChange={(e) => update("rule_review_date", e.target.value)}
            />
          </label>
          <label>
            Assessed annual GST taxpayer status
            <select
              value={value.taxpayer_type}
              onChange={(e) => update("taxpayer_type", e.target.value)}
            >
              <option value="unknown">Unresolved</option>
              <option value="regular">Regular</option>
              <option value="isd">Input Service Distributor</option>
              <option value="section-51">Section 51 taxpayer</option>
              <option value="section-52">Section 52 taxpayer</option>
              <option value="casual">Casual taxable person</option>
              <option value="non-resident">Non-resident taxable person</option>
              <option value="government-local-authority-audited">
                Government department / local authority with qualifying audited
                books
              </option>
              <option value="composition">Composition — separate review</option>
              <option value="mixed">Mixed regimes — separate review</option>
            </select>
          </label>
          <label>
            PAN-wide aggregate turnover (INR)
            <input
              inputMode="decimal"
              value={value.aggregate_turnover}
              onChange={(e) => update("aggregate_turnover", e.target.value)}
            />
          </label>
          <label>
            Other PAN turnover outside this registration bridge (INR)
            <input
              inputMode="decimal"
              value={value.other_pan_turnover}
              onChange={(e) => update("other_pan_turnover", e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={value.pan_population_complete}
              onChange={(e) =>
                update("pan_population_complete", e.target.checked)
              }
            />
            PAN-wide population assessed complete, including all registrations
            and other turnover
          </label>
          <label>
            Annual GST population, taxpayer status and legal review basis
            <textarea
              value={value.assessment}
              onChange={(e) => update("assessment", e.target.value)}
            />
          </label>
        </>
      )}
    </fieldset>
  );
}

export function AnnualGSTResult({ value }: { value: Record<string, unknown> }) {
  const scope =
    value.scope && typeof value.scope === "object"
      ? (value.scope as Record<string, unknown>)
      : {};
  const display = (key: string) =>
    scope[key] === null || scope[key] === undefined || scope[key] === ""
      ? "Not supplied"
      : String(scope[key]);
  return (
    <section aria-label="Annual GST applicability candidates">
      <h3>Annual GST applicability candidates</h3>
      <dl>
        <dt>PAN</dt>
        <dd>{display("pan")}</dd>
        <dt>Financial year</dt>
        <dd>
          {display("financial_year_start")} to {display("financial_year_end")}
        </dd>
        <dt>Rule review date</dt>
        <dd>{display("rule_review_date")}</dd>
        <dt>Assessed taxpayer status</dt>
        <dd>{display("taxpayer_type")}</dd>
        <dt>PAN-wide aggregate turnover (INR)</dt>
        <dd>{display("aggregate_turnover")}</dd>
        <dt>Other PAN turnover (INR)</dt>
        <dd>{display("other_pan_turnover")}</dd>
        <dt>Assessment basis</dt>
        <dd>{display("assessment")}</dd>
      </dl>
      <p>
        GSTR-9: {String(value.gstr9)}. GSTR-9C: {String(value.gstr9c)}.
      </p>
      <p>
        Registration turnover: {String(value.registration_turnover)} INR. Filing
        is not established.
      </p>
      {Array.isArray(value.pending_reasons) &&
        value.pending_reasons.length > 0 && (
          <p>Pending: {value.pending_reasons.map(String).join(", ")}</p>
        )}
      {Array.isArray(value.limitations) && (
        <ul>
          {value.limitations.map((item, i) => (
            <li key={i}>{String(item)}</li>
          ))}
        </ul>
      )}
      {Array.isArray(value.source_urls) && (
        <p>
          Rule references:{" "}
          {value.source_urls
            .filter(
              (url) => typeof url === "string" && url.startsWith("https://"),
            )
            .map((url, index) => (
              <a key={String(url)} href={String(url)}>
                Source {index + 1}{" "}
              </a>
            ))}
        </p>
      )}
    </section>
  );
}

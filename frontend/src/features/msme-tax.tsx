"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { ErrorState } from "@/components/ui/primitives";
import { MSMERecordTrace } from "./msme-interest";

type Row = Record<string, unknown>;
type Total = {
  expected_amount: string;
  expected_complete: boolean;
  reported_amount: string;
  reported_complete: boolean;
};
export type MSMETaxBody = {
  tax_totals?: Record<string, Total>;
  tax_year_start?: string;
  as_of?: string;
  tax_observed_through?: string;
  timing_observed_through?: string;
  tax_reference?: string;
  msme_tax_document_binding?: string;
  net_expected_tax_adjustment?: string | null;
  principal_timing_exception_count?: number;
  form26_targets?: Record<string, string> | null;
};
const labels: Record<string, string> = {
  INTEREST_PNL_DISALLOWANCE: "P&L interest adjustment",
  CURRENT_PRINCIPAL_DISALLOWANCE: "Current expense disallowance",
  PRIOR_PRINCIPAL_RELEASE: "Release of earlier disallowance",
};
const value = (entry: unknown) =>
  entry == null
    ? "Not supplied"
    : typeof entry === "object"
      ? JSON.stringify(entry)
      : String(entry);
const row = (entry: unknown): Row | null =>
  entry && typeof entry === "object" && !Array.isArray(entry)
    ? (entry as Row)
    : null;

/** Server amounts remain exact strings; this view never computes a tax amount. */
export function MSMETaxDetails({
  eid,
  eventId,
  tenant,
  body,
}: {
  eid: string;
  eventId: string;
  tenant: string;
  body: MSMETaxBody;
}) {
  const [offset, setOffset] = useState(0);
  const detail = useAPI<{
    freshness: string;
    body: { invoice_tax_details?: Row[] };
    collection_totals?: Record<string, number>;
  }>(
    `intelligence/engagements/${eid}/events/${eventId}?limit=1&tax_invoice_offset=${offset}&tax_invoice_limit=10`,
    Boolean(tenant && eid && eventId),
  );
  const invoices = detail.data?.body.invoice_tax_details ?? [];
  const count = detail.data?.collection_totals?.invoice_tax_details ?? 0;
  return (
    <section aria-label="MSE annual tax scope">
      <h3>Annual MSE tax bridge</h3>
      <p>
        Tax year starts {body.tax_year_start}; year-end cutoff {body.as_of}.
        Settlement observations through {body.tax_observed_through}. Selected
        reference: {body.tax_reference}.
      </p>
      <p>
        Net expected adjustment to income: INR{" "}
        {body.net_expected_tax_adjustment ?? "Unresolved"}. This is an income
        adjustment, not tax payable or a refund.
      </p>
      <p>
        Principal timing exceptions at {body.timing_observed_through}:{" "}
        {body.principal_timing_exception_count ?? "Unknown"}. These observations
        remain separate from the tax comparison.
      </p>
      {detail.data?.freshness === "STALE" && (
        <p>
          This saved tax calculation is not current. Recheck supporting
          documents and regenerate before approval.
        </p>
      )}
      <p>
        {body.msme_tax_document_binding === "RETAINED_DOCUMENT_BYTES_VERIFIED"
          ? "Supporting bytes were verified for this saved calculation. Tax treatment and applicability remain independently assessed."
          : "No resolved tax support claimed; missing facts do not become zero adjustments."}
      </p>
      <table aria-label="Separate MSE tax adjustments">
        <thead>
          <tr>
            <th>Adjustment</th>
            <th>Expected INR</th>
            <th>Reported INR</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(body.tax_totals ?? {}).map(([metric, total]) => (
            <tr key={metric}>
              <td>
                {labels[metric] ?? metric}
                {body.form26_targets?.[metric] &&
                  ` — Form 26 ${body.form26_targets[metric]}`}
              </td>
              <td>
                {!total.expected_complete && "Partial subtotal: "}
                {total.expected_amount}
              </td>
              <td>
                {!total.reported_complete && "Partial subtotal: "}
                {total.reported_amount}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Closing accrued interest is not a P&L charge. Earlier allowed amounts
        are excluded from the release bucket. Overdue MSE expenses do not use
        the return-filing date as a payment deadline. Other tax provisions and
        full statutory disclosures remain separate.
      </p>
      <ErrorState error={detail.error} />
      <h4>Invoice tax bases and settlement evidence</h4>
      <p>
        Invoice details have their own pages, independent of the comparison
        rows. Complete sources and traces remain in XLSX.
      </p>
      {invoices.map((invoice) => {
        const basis = row(invoice.tax_basis);
        const pnl = row(invoice.interest_pnl_assessment);
        return (
          <details key={value(invoice.id)}>
            <summary>
              {value(invoice.reference)} — closing disallowed carry INR{" "}
              {value(invoice.closing_disallowed_carry)}
            </summary>
            <p>
              Principal tax issue: {value(invoice.principal_tax_issue)}. P&L
              interest issue: {value(invoice.interest_pnl_issue)}. Original
              timing: {value(invoice.timing_state)}.
            </p>
            {basis && (
              <dl>
                {[
                  "amount",
                  "liability_tax_year_start",
                  "opening_paid_basis",
                  "opening_disallowed_basis",
                  "opening_previously_allowed_unpaid",
                  "tax_reference",
                  "prior_disallowance_reference",
                  "otherwise_allowable",
                  "basis_assessment",
                ].map((key) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{value(basis[key])}</dd>
                  </div>
                ))}
              </dl>
            )}
            <MSMERecordTrace
              title="Complete assessed tax basis"
              rows={basis ? [basis] : []}
            />
            <MSMERecordTrace
              title="Assessed P&L interest"
              rows={pnl ? [pnl] : []}
            />
            <MSMERecordTrace
              title="Tax settlements and original bank links"
              rows={
                Array.isArray(invoice.tax_settlements)
                  ? (invoice.tax_settlements as Row[])
                  : []
              }
            />
            <MSMERecordTrace
              title="Retained original invoice facts"
              rows={
                row(invoice.retained_invoice_facts)
                  ? [row(invoice.retained_invoice_facts)!]
                  : []
              }
            />
            <MSMERecordTrace
              title="Retained supplier assessment"
              rows={
                row(invoice.retained_supplier_assessment)
                  ? [row(invoice.retained_supplier_assessment)!]
                  : []
              }
            />
          </details>
        );
      })}
      <nav aria-label="Invoice tax detail pages">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 10))}
        >
          Previous invoices
        </button>
        <span>
          {" "}
          {count ? offset + 1 : 0}–{Math.min(offset + 10, count)} of{" "}
          {count}{" "}
        </span>
        <button
          type="button"
          disabled={offset + 10 >= count}
          onClick={() => setOffset(offset + 10)}
        >
          Next invoices
        </button>
      </nav>
    </section>
  );
}

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
type Receipt = {
  type: string;
  id: string;
  record_id?: string;
  sha256?: string;
};

export function PartyConfirmationEvidence({
  eid,
  tenant,
  rows,
  dependencies,
}: {
  eid: string;
  tenant: string;
  rows: Row[];
  dependencies: Receipt[];
}) {
  const [index, setIndex] = useState(0);
  const [itemOffset, setItemOffset] = useState(0);
  const [itemScope, setItemScope] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const row = rows[index];
  if (!row) return null;
  const evidence = (row.confirmation_evidence || {}) as Row;
  const itemIds = Array.isArray(row.open_item_source_ids)
    ? row.open_item_source_ids.map(String)
    : [];
  const selectedIds =
    itemScope === "all" ? itemIds : row[`${itemScope}_item_source_ids`];
  const scopedIds = Array.isArray(selectedIds) ? selectedIds.map(String) : null;
  const page = (scopedIds || []).slice(itemOffset, itemOffset + 100);

  async function download(prefix: string, receipt: Receipt) {
    setError(null);
    try {
      const response = await fetch(
        `/api/backend/engagements/${eid}/audit/evidence-files/${receipt.record_id}/${receipt.id}/download`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!response.ok)
        throw new Error("Retained document download denied or unavailable");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download =
        response.headers
          .get("content-disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ||
        `${prefix}-confirmation-evidence`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Retained document download failed",
      );
    }
  }

  return (
    <details style={{ margin: "16px 0" }}>
      <summary>Request, response and follow-up evidence</summary>
      <section aria-label="Party confirmation evidence">
        <label>
          Party evidence position
          <select
            value={index}
            onChange={(event) => {
              setIndex(Number(event.target.value));
              setItemOffset(0);
              setItemScope("all");
              setError(null);
            }}
          >
            {rows.map((value, position) => (
              <option key={String(value.id)} value={position}>
                {String(value.account)} · {String(value.counterparty)} ·{" "}
                {String(value.side)} · {String(value.currency)}
              </option>
            ))}
          </select>
        </label>
        <p>
          Source assessment:{" "}
          {String(
            evidence.scope_assessment ||
              "No assessment row retained for this position",
          )}
        </p>
        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(180px, 1fr) 2fr",
            gap: 8,
          }}
        >
          {[
            "status",
            "request_basis",
            "scope_balance",
            "requested_amount",
            "requested_on",
            "responded_on",
            "contact_verified",
            "independently_received",
            "followup_kind",
            "followup_on",
          ].map((field) => (
            <div key={field} style={{ display: "contents" }}>
              <dt>
                {field.replaceAll("followup", "follow-up").replaceAll("_", " ")}
              </dt>
              <dd style={{ margin: 0 }}>
                {evidence[field] == null
                  ? field === "requested_amount" &&
                    evidence.request_basis === "blank-positive"
                    ? "Intentionally blank"
                    : "Not supplied"
                  : String(evidence[field])}
              </dd>
            </div>
          ))}
        </dl>
        <p>
          Verification and direct receipt are assessed declarations. Downloaded
          files and hashes do not authenticate the sender or establish
          sufficient audit evidence.
        </p>
        <div className="form-grid" style={{ alignItems: "start" }}>
          {(["request", "response", "followup"] as const).map((prefix) => {
            const id = evidence[`${prefix}_evidence_version_id`];
            const receipt = dependencies.find(
              (value) =>
                value.type === "evidence" &&
                value.id === id &&
                value.sha256 === evidence[`${prefix}_source_sha256`] &&
                value.record_id,
            );
            return (
              <section
                key={prefix}
                aria-label={`${prefix} document`}
                style={{ overflowWrap: "anywhere" }}
              >
                <h4>
                  {prefix === "followup"
                    ? "Follow-up"
                    : prefix[0].toUpperCase() + prefix.slice(1)}{" "}
                  document
                </h4>
                {id ? (
                  <>
                    <p>Reference: {String(evidence[`${prefix}_reference`])}</p>
                    <p>Retained version: {String(id)}</p>
                    <p>
                      SHA-256:{" "}
                      <code>{String(evidence[`${prefix}_source_sha256`])}</code>
                    </p>
                    <Button
                      disabled={!receipt}
                      onClick={() => receipt && void download(prefix, receipt)}
                    >
                      Download {prefix === "followup" ? "follow-up" : prefix}{" "}
                      evidence
                    </Button>
                    {!receipt && (
                      <p>
                        Download receipt unavailable in this result. Review the
                        retained source evidence.
                      </p>
                    )}
                  </>
                ) : (
                  <p>
                    No retained {prefix === "followup" ? "follow-up" : prefix}{" "}
                    document
                  </p>
                )}
              </section>
            );
          })}
        </div>
        {evidence.followup_assessment ? (
          <p>Follow-up assessment: {String(evidence.followup_assessment)}</p>
        ) : null}
        {error && <p role="alert">{error}</p>}
        <details>
          <summary>Linked open items · {itemIds.length}</summary>
          {row.confirmation_status === "partially-received" && (
            <>
              <label>
                Linked item scope
                <select
                  value={itemScope}
                  onChange={(event) => {
                    setItemScope(event.target.value);
                    setItemOffset(0);
                  }}
                >
                  <option value="all">All book items</option>
                  <option value="covered">Declared reply-covered items</option>
                  <option value="uncovered">Items outside reply scope</option>
                </select>
              </label>
              <p>
                Covered book balance:{" "}
                {String(row.covered_book_balance ?? "Unknown")}. Uncovered book
                balance: {String(row.uncovered_book_balance ?? "Unknown")}.
                Covered reply difference:{" "}
                {String(row.covered_response_difference ?? "Unknown")}. The full
                balance has not been confirmed.
              </p>
            </>
          )}
          <p>
            {page.length
              ? `Item links ${itemOffset + 1}–${itemOffset + page.length} of ${scopedIds?.length}`
              : scopedIds === null
                ? "Partial reply item membership is unknown"
                : "No reporting-date item links"}
            . Use the schedule pages to reach additional party positions. XLSX
            retains every item ID.
          </p>
          <ol start={itemOffset + 1}>
            {page.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ol>
          <div className="toolbar">
            <Button
              disabled={itemOffset === 0}
              onClick={() => setItemOffset(Math.max(0, itemOffset - 100))}
            >
              Previous item links
            </Button>
            <Button
              disabled={itemOffset + page.length >= (scopedIds?.length || 0)}
              onClick={() => setItemOffset(itemOffset + 100)}
            >
              Next item links
            </Button>
          </div>
        </details>
      </section>
    </details>
  );
}

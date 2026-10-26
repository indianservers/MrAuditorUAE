"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

export type GrantDocument = { id: string; record_id?: string; sha256?: string };
export function GrantSourceNotice({ kind }: { kind: string }) {
  return (
    <p role="note">
      {kind === "grant-budgets"
        ? "The file total sums category ceilings for import control. Whole-fund ceilings are tested separately; neither total establishes cash available or permission to spend."
        : kind === "grant-utilisation-controls"
          ? "The file total combines opening balances and period account controls solely to check this file. Business comparisons separate each fund/category opening from each account’s net, gross and row-count controls."
          : kind === "grant-expenses"
            ? "Amounts are signed book expenditure observations. Recognition, capitalisation, source completeness and cash settlement need separate assessment."
            : "Allocations distribute the declared expenditure population. A credit needs a retained original-reference recovery assessment and always remains subject to review."}
    </p>
  );
}
export function GrantUtilisationEvidence({
  eid,
  tenant,
  documents,
  currencies,
  reviewWindow,
}: {
  eid: string;
  tenant: string;
  documents: GrantDocument[];
  currencies?: string[];
  reviewWindow?: { from: string; through: string };
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function download(document: GrantDocument) {
    setBusy(document.id);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/engagements/${eid}/audit/evidence-files/${document.record_id}/${document.id}/download`,
        { headers: { "X-Tenant-ID": tenant }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "Retained grant document is unavailable or access was denied.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = url;
      link.download =
        response.headers
          .get("content-disposition")
          ?.match(/filename="([^"]+)"/)?.[1] || "grant-evidence";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy("");
    }
  }
  return (
    <section aria-label="Grant utilisation scope">
      <h3>Grant expenditure and budget review</h3>
      {reviewWindow && (
        <p>
          {reviewWindow.from} through {reviewWindow.through} ·{" "}
          {(currencies || []).join(", ")}
        </p>
      )}
      <p>
        Opening utilisation plus this period’s signed expenditure is compared
        separately with each category ceiling and the whole fund ceiling.
        Currencies remain separate. Missing opening balances and account
        controls block approval.
      </p>
      <p>
        Remaining amounts describe the signed expenditure schedule. They do not
        establish cash available, donor permission, legal eligibility or a
        utilisation certificate. Credits always require a separate recovery
        review.
      </p>
      <details>
        <summary>
          Retained grant mandate and recovery evidence ({documents.length})
        </summary>
        {documents.map((document, index) => (
          <div
            key={document.id}
            style={{ margin: "12px 0", overflowWrap: "anywhere" }}
          >
            <Button
              disabled={!!busy || !document.record_id}
              onClick={() => download(document)}
            >
              Download grant evidence {index + 1}
            </Button>
            <p>SHA-256: {document.sha256 || "Not retained"}</p>
          </div>
        ))}
      </details>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

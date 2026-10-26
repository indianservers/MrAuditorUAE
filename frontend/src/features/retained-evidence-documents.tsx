"use client";
import { useState } from "react";
import { Button } from "@/components/ui/primitives";
export type RetainedEvidenceDocument = {
  id: string;
  record_id?: string;
  sha256?: string;
};
export function RetainedEvidenceDocuments({
  eid,
  tenant,
  documents,
  summary,
  label,
}: {
  eid: string;
  tenant: string;
  documents: RetainedEvidenceDocument[];
  summary: string;
  label: string;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function download(document: RetainedEvidenceDocument) {
    setBusy(document.id);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/engagements/${eid}/audit/evidence-files/${document.record_id}/${document.id}/download`,
        { headers: { "X-Tenant-ID": tenant }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "Retained supporting document is unavailable or access was denied.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = window.document.createElement("a");
      link.href = url;
      link.download =
        response.headers
          .get("content-disposition")
          ?.match(/filename="([^"]+)"/)?.[1] || "supporting-evidence";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <details>
        <summary>
          {summary} ({documents.length})
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
              Download {label} evidence {index + 1}
            </Button>
            <p>SHA-256: {document.sha256 || "Not retained"}</p>
          </div>
        ))}
      </details>
      {error && <p role="alert">{error}</p>}
    </>
  );
}

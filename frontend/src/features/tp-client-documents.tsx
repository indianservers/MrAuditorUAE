"use client";
import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { RecordRow } from "@/types/models";

export function TPClientDocuments() {
  const documents = useAPI<{ items: RecordRow[] }>("tp/client-documents");
  const tenant = useScope((s) => s.tenant);
  const [error, setError] = useState("");
  async function download(id: string) {
    try {
      const response = await fetch(
        `/api/backend/tp/client-documents/${id}/download`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!response.ok)
        throw new Error("Issued document is unavailable for this client.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `AuditOS-TP-issued-${id}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <section className="workbench-body">
      <h2>Issued Transfer Pricing documents</h2>
      {documents.error && <ErrorState error={documents.error} />}
      {error && <ErrorState error={new Error(error)} />}
      {documents.data?.items.map((x) => (
        <p key={x.id}>
          {String(x.title)} · Version {String(x.annual_version)}{" "}
          <Button onClick={() => download(x.id)}>Download issued PDF</Button>
        </p>
      ))}
      {documents.data && !documents.data.items.length && (
        <p>
          No Transfer Pricing document has been issued to your organization.
        </p>
      )}
    </section>
  );
}

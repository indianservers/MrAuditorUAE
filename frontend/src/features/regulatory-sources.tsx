"use client";

import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";

export type RegulatorySource = {
  id: string;
  title: string;
  country: string;
  source_url: string;
  retrieved_on: string;
  filename: string;
  sha256: string;
  scan_status: string;
};

export function bindRetainedSource(
  editor: string,
  document: RegulatorySource,
  citationNumber: number,
) {
  const body = JSON.parse(editor);
  if (document.country !== "GLOBAL" && document.country !== body.country)
    throw new Error(
      "The source jurisdiction must match the proposed rule or be GLOBAL.",
    );
  if (
    !Number.isInteger(citationNumber) ||
    citationNumber < 1 ||
    citationNumber > (body.citations?.length || 0)
  )
    throw new Error("Select an existing citation number in the rule proposal.");
  body.citations[citationNumber - 1] = {
    ...body.citations[citationNumber - 1],
    source_document_id: document.id,
    document_sha256: document.sha256,
    url: document.source_url,
    retrieved_on: document.retrieved_on,
    retrieval_status: "RETRIEVED",
  };
  return JSON.stringify(body, null, 2);
}

export function RegulatorySources({
  country,
  editor,
  onAttach,
}: {
  country: string;
  editor: string;
  onAttach: (document: RegulatorySource, citationNumber: number) => void;
}) {
  const tenant = useScope((scope) => scope.tenant);
  const canManage = useCan("tax.rules.manage");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<RegulatorySource | null>(null);
  const [citationNumber, setCitationNumber] = useState(1);
  const [title, setTitle] = useState("");
  const [sourceCountry, setSourceCountry] = useState(country);
  const [url, setUrl] = useState("");
  const [retrieved, setRetrieved] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const action = useAction<RegulatorySource>();
  const copies = useAPI<{ items: RegulatorySource[] }>(
    `regulatory/sources?country=${country}&offset=${offset}`,
  );
  const choices = [...(copies.data?.items || [])];
  if (selected && !choices.some((copy) => copy.id === selected.id))
    choices.unshift(selected);

  async function upload() {
    setError(null);
    try {
      if (!file || !title.trim() || !url || !retrieved)
        throw new Error(
          "Choose a source file, title, jurisdiction, HTTPS URL and retrieval date.",
        );
      const data = new FormData();
      data.set(
        "metadata",
        JSON.stringify({
          title,
          country: sourceCountry,
          source_url: url,
          retrieved_on: retrieved,
        }),
      );
      data.set("file", file);
      const copy = await action.mutateAsync({
        path: "regulatory/sources",
        body: data,
      });
      setSelected(copy);
    } catch (failure) {
      setError(failure as Error);
    }
  }

  async function download() {
    if (!selected) return;
    setError(null);
    try {
      const response = await fetch(
        `/api/backend/regulatory/sources/${selected.id}/download`,
        { headers: { "X-Tenant-ID": tenant } },
      );
      if (!response.ok)
        throw new Error(`Source download failed (${response.status})`);
      const blob = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = blob;
      link.download = selected.filename;
      link.click();
      URL.revokeObjectURL(blob);
    } catch (failure) {
      setError(failure as Error);
    }
  }

  return (
    <details className="main-panel" style={{ padding: 20 }}>
      <summary>Firm regulatory reference copies</summary>
      <p>
        Retain public regulatory reference material separately from client
        evidence. Source copies are immutable. File integrity and scanning do
        not establish authenticity or legal applicability.
      </p>
      <ErrorState error={error || copies.error || action.error} />
      <label>
        Retained regulatory source
        <select
          aria-label="Retained regulatory source"
          value={selected?.id || ""}
          onChange={(event) =>
            setSelected(
              choices.find((copy) => copy.id === event.target.value) || null,
            )
          }
        >
          <option value="">Choose a retained copy</option>
          {choices.map((copy) => (
            <option key={copy.id} value={copy.id}>
              {copy.title} · {copy.country} · {copy.retrieved_on}
            </option>
          ))}
        </select>
      </label>
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous source copies
        </Button>
        <Button
          disabled={copies.data?.items.length !== 50}
          onClick={() => setOffset(offset + 50)}
        >
          Next source copies
        </Button>
        <Button disabled={!selected} onClick={download}>
          Download retained source
        </Button>
      </div>
      {selected && (
        <p>
          SHA-256: {selected.sha256} · Scan: {selected.scan_status}
        </p>
      )}
      {editor && (
        <>
          <label>
            Citation number
            <input
              type="number"
              min={1}
              max={20}
              value={citationNumber}
              onChange={(event) =>
                setCitationNumber(Number(event.target.value))
              }
            />
          </label>
          <Button
            disabled={!selected}
            onClick={() => selected && onAttach(selected, citationNumber)}
          >
            Attach source to proposal citation
          </Button>
          <p>
            This binds the retained copy and retrieval details. Technical
            validation and independent professional review remain separate.
          </p>
        </>
      )}
      {canManage && (
        <fieldset>
          <legend>Retain a new reference copy</legend>
          <label>
            Reference title
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            Source jurisdiction
            <select
              value={sourceCountry}
              onChange={(event) => setSourceCountry(event.target.value)}
            >
              <option value={country}>{country}</option>
              <option value="GLOBAL">GLOBAL</option>
            </select>
          </label>
          <label>
            Source HTTPS URL
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
          </label>
          <label>
            Source retrieved on
            <input
              type="date"
              value={retrieved}
              onChange={(event) => setRetrieved(event.target.value)}
            />
          </label>
          <label>
            Regulatory reference file
            <input
              type="file"
              accept=".pdf,.txt"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <Button disabled={action.isPending} onClick={upload}>
            Retain scanned reference copy
          </Button>
          <p>
            PDF or UTF-8 text, up to 10 MiB. Malware clearance is required;
            scanner failures do not create usable copies.
          </p>
        </fieldset>
      )}
    </details>
  );
}

"use client";
import { useState } from "react";
import { useAction, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { RecordRow } from "@/types/models";

export function SoDImport({ base }: { base: string }) {
  const action = useAction<RecordRow>();
  const [file, setFile] = useState<File>();
  const [reference, setReference] = useState("");
  const [title, setTitle] = useState("");
  const [system, setSystem] = useState("");
  const [rule, setRule] = useState("");
  const [asOf, setAsOf] = useState("");
  const [evidence, setEvidence] = useState("");
  return (
    <details>
      <summary>Import an ERP permission population</summary>
      <form
        className="grc-editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (!file) return;
          const body = new FormData();
          body.append("file", file);
          body.append(
            "metadata",
            JSON.stringify({
              reference,
              title,
              body: {
                system,
                rule_id: rule,
                as_of: asOf,
                source_evidence_id: evidence,
              },
            }),
          );
          action.mutate({ path: `${base}/sod/import`, body });
        }}
      >
        <p>
          CSV columns: principal, permission, scope, valid_from, optional
          valid_to. Maximum 4 MiB and 10,000 assignments. The file must match
          its clean, independently approved evidence version.
        </p>
        <label>
          Access population reference
          <input
            required
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
        <label>
          Access population title
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          ERP system
          <input
            required
            value={system}
            onChange={(e) => setSystem(e.target.value)}
          />
        </label>
        <label>
          Approved SoD rule reference
          <input
            required
            value={rule}
            onChange={(e) => setRule(e.target.value)}
          />
        </label>
        <label>
          Assessment date
          <input
            required
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <label>
          Approved CSV evidence reference
          <input
            required
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
          />
        </label>
        <label>
          ERP access CSV
          <input
            required
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </label>
        <Button primary disabled={!file || action.isPending}>
          Import for review
        </Button>
        {action.data && (
          <p>
            Imported {String(action.data.reference)} ·{" "}
            {String(action.data.status)}. Independent approval remains required.
          </p>
        )}
        {action.error && <ErrorState error={action.error} />}
      </form>
    </details>
  );
}

export function MLFeedback({
  inference,
  transaction,
}: {
  inference: unknown;
  transaction: string;
}) {
  const allowed = useCan("ml.feedback");
  const action = useAction();
  const [label, setLabel] = useState("insufficient_evidence");
  const [evidence, setEvidence] = useState("");
  const [rationale, setRationale] = useState("");
  if (!allowed || typeof inference !== "string") return null;
  return (
    <details>
      <summary>Record evidence-backed model feedback</summary>
      <label>
        Reviewer label
        <select value={label} onChange={(e) => setLabel(e.target.value)}>
          {[
            "false_positive",
            "valid_exception",
            "confirmed_misstatement",
            "insufficient_evidence",
            "no_issue",
          ].map((x) => (
            <option key={x} value={x}>
              {x.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
      <label>
        Approved evidence reference
        <input value={evidence} onChange={(e) => setEvidence(e.target.value)} />
      </label>
      <label>
        Feedback rationale
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </label>
      <Button
        disabled={!evidence || rationale.length < 20 || action.isPending}
        onClick={() =>
          action.mutate({
            path: `ml/predictions/${inference}/feedback`,
            body: {
              transaction_id: transaction,
              label,
              evidence_id: evidence,
              rationale,
            },
          })
        }
      >
        Record reviewer feedback
      </Button>
      <p>
        Feedback requires separate curation. Monitoring holdout rows remain
        outside training.
      </p>
      {action.error && <ErrorState error={action.error} />}
    </details>
  );
}

export function BoardDownloads({
  eid,
  identifier,
}: {
  eid: string;
  identifier: string;
}) {
  const tenant = useScope((s) => s.tenant);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function download(format: string) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/grc/engagements/${eid}/board/packages/${identifier}/export/${format}`,
        { headers: { "X-Tenant-ID": tenant }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "Package unavailable; verify audience, source approval and validity.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `governance-${identifier}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <div className="grc-toolbar">
        <Button disabled={busy} onClick={() => download("pdf")}>
          Download reviewed PDF
        </Button>
        <Button disabled={busy} onClick={() => download("docx")}>
          Download reviewed Word report
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

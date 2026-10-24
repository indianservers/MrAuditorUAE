"use client";

import { useState } from "react";
import { Button, ErrorState, Facts } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import type { RecordRow } from "@/types/models";
import { JobProgress } from "./shared";

type Operation = {
  id: string;
  namespace: string;
  payload: Record<string, unknown>;
};

export function ConnectorOperations({ connection }: { connection: RecordRow }) {
  const health = useAPI<{
    status: string;
    records: Operation[];
    operational_health?: Record<string, unknown>;
  }>(`connectors/operations/${connection.id}`);
  const action = useAction<RecordRow>();
  const [session, setSession] = useState("");
  const [job, setJob] = useState("");
  const preferences = (connection.config || {}) as Record<string, unknown>;
  const [documents, setDocuments] = useState(
    Boolean(preferences.include_documents),
  );
  const [attachments, setAttachments] = useState(
    Boolean(preferences.include_attachments),
  );
  const [incremental, setIncremental] = useState(
    Boolean(preferences.incremental_documents),
  );
  const [company, setCompany] = useState(String(preferences.company || ""));
  const [fingerprint, setFingerprint] = useState(
    String(preferences.company_fingerprint || ""),
  );
  const [batch, setBatch] = useState("");
  const native = connection.provider !== "tally";
  const records = health.data?.records || [];
  const resume = (id: string) =>
    action.mutate(
      {
        path: `connectors/${connection.provider === "zoho" ? "zoho" : "native"}/${connection.id}/sync?resume_session=${encodeURIComponent(id)}`,
      },
      { onSuccess: (result) => setJob(result.id) },
    );

  return (
    <details>
      <summary>Sync health and recovery</summary>
      <ErrorState error={health.error || action.error} />
      <p>
        Saved pages are verified before replay. A recovered extraction still
        needs validation and review before activation.
      </p>
      <Facts
        data={{
          ...health.data?.operational_health,
          status: health.data?.status || connection.status,
          pending_repairs: records.filter(
            (r) =>
              r.namespace === "event" && r.payload.state === "repair_pending",
          ).length,
          qualification_records: records.filter(
            (r) => r.namespace === "qualification",
          ).length,
        }}
      />
      {connection.provider === "zoho" && (
        <fieldset>
          <legend>Supporting evidence</legend>
          <label>
            <input
              type="checkbox"
              checked={incremental}
              onChange={(event) => setIncremental(event.target.checked)}
            />
            Use documented document deltas; refresh the full ledger
          </label>
          <label>
            <input
              type="checkbox"
              checked={documents}
              onChange={(e) => setDocuments(e.target.checked)}
            />
            Document and payment details
          </label>
          <label>
            <input
              type="checkbox"
              checked={attachments}
              onChange={(e) => setAttachments(e.target.checked)}
            />
            Invoice attachments
          </label>
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate({
                path: `connectors/operations/${connection.id}/preferences`,
                method: "PATCH",
                body: {
                  include_documents: documents,
                  include_attachments: attachments,
                  incremental_documents: incremental,
                },
              })
            }
          >
            Save evidence preferences
          </Button>
        </fieldset>
      )}
      {connection.provider === "tally" && (
        <fieldset>
          <legend>Tally source identity and history</legend>
          <label>
            Selected Tally company
            <input
              value={company}
              onChange={(event) => setCompany(event.target.value)}
            />
          </label>
          <label>
            Company fingerprint from the local agent
            <input
              value={fingerprint}
              onChange={(event) => setFingerprint(event.target.value)}
            />
          </label>
          <Button
            disabled={
              action.isPending ||
              !company ||
              !/^[a-f0-9]{64}$/.test(fingerprint)
            }
            onClick={() =>
              action.mutate({
                path: `connectors/operations/${connection.id}/tally-identity`,
                method: "PATCH",
                body: { company, company_fingerprint: fingerprint },
              })
            }
          >
            Pin selected company identity
          </Button>
          <label>
            Uploaded Tally ledger batch identifier
            <input
              value={batch}
              onChange={(event) => setBatch(event.target.value)}
            />
          </label>
          <Button
            disabled={action.isPending || !/^[0-9a-f-]{36}$/i.test(batch)}
            onClick={() =>
              action.mutate({
                path: `connectors/operations/${connection.id}/agent-revisions`,
                body: { batch_id: batch },
              })
            }
          >
            Compare native voucher revisions
          </Button>
        </fieldset>
      )}
      {native && (
        <>
          <label>
            Saved sync session identifier
            <input
              value={session}
              onChange={(e) => setSession(e.target.value)}
            />
          </label>
          <Button
            disabled={action.isPending || !/^[0-9a-f-]{36}$/i.test(session)}
            onClick={() => resume(session)}
          >
            Resume saved extraction
          </Button>
          {records
            .filter((r) => r.namespace === "session")
            .slice(0, 5)
            .map((record) => (
              <div key={record.id}>
                <span>
                  {String(record.payload.status)} ·{" "}
                  {String(record.payload.resume_session)}
                </span>
                <Button
                  disabled={action.isPending}
                  onClick={() => {
                    const id = String(record.payload.resume_session);
                    setSession(id);
                    resume(id);
                  }}
                >
                  Replay session
                </Button>
              </div>
            ))}
        </>
      )}
      {connection.provider === "quickbooks" &&
        ((connection.config || {}) as Record<string, unknown>).edition !==
          "desktop-partner-api" && (
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(
                { path: `connectors/operations/${connection.id}/repair` },
                { onSuccess: (result) => setJob(result.id) },
              )
            }
          >
            Repair QuickBooks changes
          </Button>
        )}
      {job && (
        <JobProgress
          id={job}
          onDone={() => {
            void health.refetch();
          }}
        />
      )}
      {records
        .filter((r) =>
          ["qualification", "source_revision"].includes(r.namespace),
        )
        .slice(0, 5)
        .map((record) => (
          <Facts
            key={record.id}
            data={{
              kind: record.namespace,
              ...Object.fromEntries(
                Object.entries(record.payload).filter(([key]) =>
                  [
                    "status",
                    "scenario",
                    "matched",
                    "comparable",
                    "deletions_testable",
                    "identity_warning",
                  ].includes(key),
                ),
              ),
            }}
          />
        ))}
    </details>
  );
}

"use client";
import { useState } from "react";
import Link from "next/link";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { Button, ErrorState, Facts } from "@/components/ui/primitives";

type Case = {
  id: number;
  key: string;
  title: string;
  prompt: string;
  description: string;
  engines: string[];
  required_information: string[];
  module_url: string;
  workflow: string | null;
  calculation: { family: string; kind: string; operation: string } | null;
  limitations: string[];
};
type RecordInput = {
  id: string;
  kind: string;
  title: string;
  reference: string;
  status: string;
  version: number;
};
type Run = {
  id: string;
  state: string;
  plan: string[];
  outputs: Record<string, unknown>;
  events?: { id: string; kind: string; body: Record<string, unknown> }[];
};

export function UAEBusinessCases({ eid }: { eid: string }) {
  const base = `ai/engagements/${eid}`;
  const catalogue = useAPI<{ items: Case[] }>(`${base}/use-cases`);
  const [caseId, setCaseId] = useState(1),
    [filter, setFilter] = useState(""),
    [question, setQuestion] = useState(""),
    [recordId, setRecordId] = useState(""),
    [runId, setRunId] = useState(""),
    [error, setError] = useState<Error>(),
    [actionResult, setActionResult] = useState<Record<string, unknown>>();
  const chosen = catalogue.data?.items.find((c) => c.id === caseId);
  const records = useAPI<{
    items: RecordInput[];
    missing_information: string[];
  }>(`${base}/use-cases/${caseId}/inputs`, !!chosen);
  const run = useAPI<Run>(`${base}/investigations/${runId}`, !!runId);
  const action = useAction<Record<string, unknown>>();
  const [draftNotes, setDraftNotes] = useState("");
  const canDraft = useCan("workingpaper.create");
  const canRun = useCan("ai.workflow.run"),
    canCreate = useCan("ai.investigation.create");
  async function start() {
    if (!chosen) return;
    setError(undefined);
    try {
      const r = await action.mutateAsync({
        path: "ai/command",
        body: {
          engagement_id: eid,
          task: chosen.key,
          prompt: question || chosen.prompt,
          idempotency_key: crypto.randomUUID(),
          inputs: { use_case_id: caseId },
        },
      });
      setRunId(String(r.id));
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Analysis could not start"));
    }
  }
  async function next() {
    try {
      await action.mutateAsync({
        path: `${base}/investigations/${runId}/step`,
      });
      await run.refetch();
    } catch (e) {
      setError(
        e instanceof Error
          ? e
          : new Error("Step failed; review current status before retrying"),
      );
    }
  }
  async function calculate() {
    setError(undefined);
    try {
      const r = await action.mutateAsync({
        path: `${base}/use-cases/${caseId}/actions`,
        body: {
          action: "calculate",
          record_id: recordId,
          idempotency_key: crypto.randomUUID(),
        },
      });
      setActionResult(r);
    } catch (e) {
      setError(
        e instanceof Error
          ? e
          : new Error("Engine rejected the selected inputs"),
      );
    }
  }
  async function draft() {
    if (!chosen) return;
    setError(undefined);
    try {
      const key = crypto.randomUUID();
      const r = await action.mutateAsync({
        path: `${base}/use-cases/${caseId}/actions`,
        body: {
          action: "draft-workpaper",
          idempotency_key: key,
          payload: {
            reference: `UAE-${String(caseId).padStart(2, "0")}-${key.slice(0, 8)}`,
            title: chosen.title,
            body: {
              folder: "UAE business workstreams",
              sources: (records.data?.items ?? [])
                .slice(0, 20)
                .map((r) => ({ kind: "record", id: r.id })),
              sections: [
                { heading: "Reviewer preparation notes", text: draftNotes },
              ],
              conclusion:
                "Unapproved draft. Evidence sufficiency, unresolved facts and professional conclusions require independent review.",
            },
          },
        },
      });
      setActionResult(r);
    } catch (e) {
      setError(
        e instanceof Error ? e : new Error("Draft could not be created"),
      );
    }
  }
  const visible =
    catalogue.data?.items.filter((c) =>
      (c.title + " " + c.id).toLowerCase().includes(filter.toLowerCase()),
    ) ?? [];
  return (
    <section aria-label="UAE business use cases" className="ai-compose">
      <h2>Mr Auditor · UAE business workflows</h2>
      <p>
        Choose a question, inspect current evidence, then run the appropriate
        engine or prepare an authorized draft. Calculations and professional
        conclusions remain separate.
      </p>
      <label>
        Find a use case
        <input value={filter} onChange={(e) => setFilter(e.target.value)} />
      </label>
      <label>
        Business question
        <select
          value={caseId}
          onChange={(e) => {
            setCaseId(Number(e.target.value));
            setRunId("");
            setRecordId("");
            setQuestion("");
            setActionResult(undefined);
            setError(undefined);
          }}
        >
          {visible.map((c) => (
            <option key={c.id} value={c.id}>
              {String(c.id).padStart(2, "0")} · {c.title}
            </option>
          ))}
        </select>
      </label>
      {catalogue.error && <ErrorState error={catalogue.error} />}{" "}
      {records.error && <ErrorState error={records.error} />}
      {chosen && (
        <>
          <h3>{chosen.title}</h3>
          <p>{chosen.description}</p>
          <p>Connected responsibilities: {chosen.engines.join(", ")}</p>
          <details>
            <summary>Information and evidence to verify</summary>
            <ul>
              {chosen.required_information.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <p>
              These are required facts, not assertions that the client supplied
              them.
            </p>
          </details>
          <label>
            Ask Mr Auditor
            <textarea
              value={question}
              placeholder={chosen.prompt}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <Button
            disabled={!canRun || !canCreate || action.isPending}
            onClick={start}
          >
            Start source-linked analysis
          </Button>
          <Link href={chosen.module_url}>
            Open specialist inputs, evidence and approvals
          </Link>
          <p>
            Source collection uses approved application tools. Optional
            language-model explanations remain in the investigation workspace.
          </p>
          <h3>Available source records</h3>
          <table>
            <caption>
              Authorized records for this case; draft inputs cannot be
              calculated
            </caption>
            <thead>
              <tr>
                <th>Reference</th>
                <th>Type</th>
                <th>Status</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {records.data?.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.reference} · {r.title}
                  </td>
                  <td>{r.kind}</td>
                  <td>{r.status}</td>
                  <td>{r.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {chosen.calculation && (
            <>
              <label>
                Approved engine input
                <select
                  value={recordId}
                  onChange={(e) => setRecordId(e.target.value)}
                >
                  <option value="">Select an approved record</option>
                  {records.data?.items
                    .filter(
                      (r) =>
                        ["APPROVED", "LOCKED"].includes(r.status) &&
                        r.kind ===
                          `${chosen.calculation?.family}-${chosen.calculation?.kind}`,
                    )
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.reference} · {r.title}
                      </option>
                    ))}
                </select>
              </label>
              <Button
                disabled={!recordId || !canRun || action.isPending}
                onClick={calculate}
              >
                Run governed calculation
              </Button>
            </>
          )}
          {chosen.workflow && (
            <p>
              Prepare the required source roles and execute the shared workflow
              in the linked specialist module. Its existing background job,
              review, export and source-freshness controls apply.
            </p>
          )}
          <label>
            Workpaper preparation notes
            <textarea
              value={draftNotes}
              maxLength={12000}
              onChange={(e) => setDraftNotes(e.target.value)}
            />
          </label>
          <Button
            disabled={
              !canRun ||
              !canDraft ||
              action.isPending ||
              draftNotes.trim().length < 10
            }
            onClick={draft}
          >
            Create source-linked draft workpaper
          </Button>
          {chosen.limitations.map((l) => (
            <p key={l}>{l}</p>
          ))}
        </>
      )}
      {run.data && (
        <section aria-label="Analysis progress">
          <h3>Analysis · {run.data.state}</h3>
          <ol>
            {run.data.plan.map((step, i) => (
              <li key={step}>
                {i + 1}. {step}
              </li>
            ))}
          </ol>
          <Button
            disabled={
              !canRun ||
              action.isPending ||
              [
                "COMPLETED",
                "PARTIALLY_COMPLETED",
                "FAILED",
                "CANCELLED",
              ].includes(run.data.state)
            }
            onClick={next}
          >
            Run next authorized step
          </Button>
          <Link href="/ai/investigations">
            Open investigation review and controlled drafts
          </Link>
          <Facts data={run.data.outputs} />
          <details>
            <summary>Source receipts and step results</summary>
            <Facts data={{ events: run.data.events }} />
          </details>
        </section>
      )}
      {actionResult && (
        <section>
          <h3>Retained engine result</h3>
          <Facts data={actionResult} />
          <p>No journal was posted, message sent or filing submitted.</p>
        </section>
      )}
      {error && <ErrorState error={error} />}
    </section>
  );
}

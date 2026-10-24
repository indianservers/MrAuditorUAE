"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import { BusinessEvidenceFacts as Facts } from "./business-evidence-facts";
import { UAECalculationInputs } from "./uae-calculation-inputs";
import { ConnectedTaxReview } from "./connected-tax-review";
import { UAEAdvancedInputs } from "./uae-advanced-inputs";
import { UAEVATErrorInputs } from "./uae-vat-error-inputs";
import styles from "./uae-business-cases.module.css";

type Case = {
  id: number;
  advanced_contract?: {
    name: string;
    fields: { name: string; type: string }[];
    required_evidence: string[];
    limitation: string;
  } | null;
  key: string;
  title: string;
  prompt: string;
  description: string;
  engines: string[];
  required_information: string[];
  module_url: string;
  calculation_module_url?: string | null;
  workflow: string | null;
  calculation: { family: string; kind: string; operation: string } | null;
  limitations: string[];
  scope_status?: string;
  completion_status?: string;
  legal_source_ids?: string[];
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
  const catalogue = useAPI<{
    items: Case[];
    legal_source_register?: {
      items: {
        id: string;
        title: string;
        url: string;
        reviewer_status: string;
      }[];
    };
  }>(`${base}/use-cases`);
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
  const alerts = useAPI<{
    items: { id: string; reason: string; changed_source_version: number }[];
  }>(`${base}/use-cases/${caseId}/alerts`, caseId >= 51, true);
  const run = useAPI<Run>(`${base}/investigations/${runId}`, !!runId);
  const action = useAction<Record<string, unknown>>();
  const hasRetainedAction =
    actionResult?.kind === "business-action" &&
    typeof actionResult.id === "string";
  const retained = useAPI<Record<string, unknown> & { freshness: string }>(
    `intelligence/engagements/${eid}/events/${String(actionResult?.id ?? "")}`,
    hasRetainedAction,
    true,
  );
  const [sourceId, setSourceId] = useState("");
  const source = useAPI<{
    title: string;
    kind: string;
    version: number;
    body: Record<string, unknown>;
  }>(`${base}/use-cases/${caseId}/source-records/${sourceId}`, !!sourceId);
  const [collecting, setCollecting] = useState(false);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  const [draftNotes, setDraftNotes] = useState("");
  const canDraft = useCan("workingpaper.create");
  const canRun = useCan("ai.workflow.run"),
    canCreate = useCan("ai.investigation.create");
  async function start() {
    if (!chosen) return;
    setError(undefined);
    const token = ++generation.current;
    setCollecting(true);
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
      if (token !== generation.current) {
        await action.mutateAsync({
          path: `${base}/investigations/${String(r.id)}/control`,
          body: { version: r.version, action: "pause" },
        });
        return;
      }
      setRunId(String(r.id));
      for (const _ of (Array.isArray(r.plan) ? r.plan : []).slice(0, 12)) {
        if (token !== generation.current) break;
        const progress = await action.mutateAsync({
          path: `${base}/investigations/${String(r.id)}/step`,
        });
        if (token !== generation.current) {
          if (
            ![
              "COMPLETED",
              "PARTIALLY_COMPLETED",
              "FAILED",
              "CANCELLED",
            ].includes(String(progress.state))
          ) {
            await action.mutateAsync({
              path: `${base}/investigations/${String(r.id)}/control`,
              body: { version: progress.version, action: "pause" },
            });
          }
          break;
        }
        if (
          [
            "COMPLETED",
            "PARTIALLY_COMPLETED",
            "FAILED",
            "CANCELLED",
            "PAUSED",
            "WAITING_FOR_APPROVAL",
          ].includes(String(progress.state))
        )
          break;
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Analysis could not start"));
    } finally {
      setCollecting(false);
    }
  }
  async function next() {
    try {
      if (run.data?.state === "PAUSED")
        await action.mutateAsync({
          path: `${base}/investigations/${runId}/control`,
          body: {
            version: (run.data as Run & { version: number }).version,
            action: "resume",
          },
        });
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
              sources: [
                ...(records.data?.items ?? [])
                  .slice(0, 20)
                  .map((r) => ({ kind: "record", id: r.id })),
                ...(actionResult?.kind === "business-action" &&
                typeof actionResult.id === "string"
                  ? [{ kind: "intelligence", id: actionResult.id }]
                  : []),
              ],
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
    <section
      aria-label="UAE business use cases"
      className={`${styles.panel} ai-compose`}
    >
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
            generation.current++;
            setCaseId(Number(e.target.value));
            setSourceId("");
            setRunId("");
            setRecordId("");
            setQuestion("");
            setActionResult(undefined);
            setDraftNotes("");
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
          <p>
            Implementation: {chosen.completion_status ?? "Verification pending"}
            . This describes the scoped workflow, not client compliance.
          </p>
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
            disabled={!canRun || !canCreate || action.isPending || collecting}
            onClick={start}
          >
            Start source-linked analysis
          </Button>
          {collecting && (
            <>
              <p role="status">
                Collecting authorized engine results. Each step rechecks source
                access and freshness.
              </p>
              <Button
                onClick={() => {
                  generation.current++;
                }}
              >
                Pause after current step
              </Button>
            </>
          )}
          <Link href={chosen.module_url}>
            Open specialist inputs, evidence and approvals
          </Link>
          {chosen.calculation_module_url &&
            chosen.calculation_module_url !== chosen.module_url && (
              <Link href={chosen.calculation_module_url}>
                Prepare specialist calculation inputs
              </Link>
            )}
          <p>
            Source collection uses approved application tools. Optional
            language-model explanations remain in the investigation workspace.
          </p>
          {alerts.data?.items.length ? (
            <aside aria-label="Source change inbox">
              <h3>Source changes requiring reassessment</h3>
              {alerts.data.items.map((a) => (
                <p key={a.id}>
                  {a.reason} · source version {a.changed_source_version}. The
                  prior approved version is preserved; revise and reapprove the
                  input before rerunning.
                </p>
              ))}
            </aside>
          ) : null}
          <h3>Available source records</h3>
          <Button
            onClick={() => {
              void records.refetch();
              if (runId) void run.refetch();
              if (hasRetainedAction) void retained.refetch();
            }}
          >
            Refresh sources and result status
          </Button>
          {caseId === 8 && (
            <UAEVATErrorInputs
              key={eid}
              eid={eid}
              sources={records.data?.items ?? []}
              onResult={setActionResult}
            />
          )}
          {chosen.advanced_contract && (
            <UAEAdvancedInputs
              key={`advanced:${eid}:${caseId}`}
              eid={eid}
              caseId={caseId}
              contract={chosen.advanced_contract}
              sources={records.data?.items ?? []}
              onResult={setActionResult}
              onSaved={() => {
                void records.refetch();
              }}
            />
          )}
          <UAECalculationInputs
            key={`calculation:${eid}:${caseId}`}
            eid={eid}
            caseId={caseId}
            sources={records.data?.items ?? []}
            onResult={setActionResult}
          />
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
                <th>Evidence</th>
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
                  <td>
                    <Button onClick={() => setSourceId(r.id)}>
                      Inspect source
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sourceId && (
            <aside aria-label="Source evidence">
              <h3>Source evidence</h3>
              <Button onClick={() => setSourceId("")}>Close source</Button>
              {source.error && <ErrorState error={source.error} />}{" "}
              {source.data && !source.error && (
                <>
                  <p>
                    {source.data.title} · version {source.data.version}
                  </p>
                  <Facts data={source.data.body} />
                  <Link href={`/engagements/${eid}/evidence`}>
                    Open original evidence versions and review history
                  </Link>
                </>
              )}
            </aside>
          )}
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
          {caseId === 50 && <ConnectedTaxReview eid={eid} />}
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
              caseId === 48 ||
              (hasRetainedAction &&
                (retained.data?.freshness === "STALE" ||
                  !!retained.error ||
                  retained.isLoading)) ||
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
          {!!chosen.legal_source_ids?.length && (
            <details>
              <summary>Primary-source references and adoption status</summary>
              <ul>
                {catalogue.data?.legal_source_register?.items
                  .filter((s) => chosen.legal_source_ids?.includes(s.id))
                  .map((s) => (
                    <li key={s.id}>
                      <a href={s.url} target="_blank" rel="noreferrer">
                        {s.title}
                      </a>{" "}
                      · {s.reviewer_status.replaceAll("_", " ")}
                    </li>
                  ))}
              </ul>
              <p>
                A source locator does not replace the engagement’s approved
                effective rule and applicability assessment.
              </p>
            </details>
          )}
        </>
      )}
      {run.error && <ErrorState error={run.error} />}
      {run.data && !run.error && (
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
          {hasRetainedAction && (
            <p role="status">
              Source state: {retained.data?.freshness ?? "CHECKING"}. Retained
              results refresh while this view is open.
            </p>
          )}
          {retained.error && <ErrorState error={retained.error} />}
          {retained.data?.freshness === "STALE" ? (
            <p role="alert">
              Source records, rules or context changed. Recalculate from
              reviewed current inputs before preparing or approving a workpaper.
            </p>
          ) : (
            !retained.error && <Facts data={retained.data ?? actionResult} />
          )}
          <p>No journal was posted, message sent or filing submitted.</p>
        </section>
      )}
      {error && <ErrorState error={error} />}
    </section>
  );
}

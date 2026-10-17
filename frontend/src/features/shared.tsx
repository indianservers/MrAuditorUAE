"use client";
import { LineageGraph } from "@/components/financial/lineage";
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Facts,
  QueryState,
  Status,
} from "@/components/ui/primitives";
import {
  useAPI,
  useAction,
  useCan,
  useDirectory,
  usePopulation,
} from "@/hooks/use-api";
import { textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { RecordRow } from "@/types/models";
import { Database, Link as LinkIcon, Play, Sparkles } from "lucide-react";
import { useState } from "react";
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  const scope = useScope();
  const dir = useDirectory();
  return (
    <header className="page-header">
      <div>
        <div className="breadcrumb">
          {eyebrow}
          <span>›</span> {title}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="page-context">
        {scope.client && (
          <div>
            <small>Client</small>
            <strong>
              {dir.clients.data?.find((c) => c.id === scope.client)?.name ||
                "Loading…"}
            </strong>
          </div>
        )}
        {scope.entity && (
          <div>
            <small>Entity</small>
            <strong>
              {dir.entities.data?.find((c) => c.id === scope.entity)?.name ||
                "Loading…"}
            </strong>
          </div>
        )}
        {scope.period && (
          <div>
            <small>Financial period</small>
            <strong>
              {dir.periods.data?.find((c) => c.id === scope.period)?.end_date ||
                "Loading…"}
            </strong>
          </div>
        )}
      </div>
      {actions && <div className="header-actions">{actions}</div>}
    </header>
  );
}
export function PopulationPicker() {
  const scope = useScope();
  const population = usePopulation();
  return (
    <label className="population-picker">
      <Database size={14} />
      <select
        aria-label="Financial population"
        value={population.chosen?.id || ""}
        onChange={(e) => scope.setSnapshot(e.target.value)}
      >
        <option value="">Select population</option>
        {population.committed.map((r) => (
          <option key={r.id} value={r.id}>
            {String(r.kind).toUpperCase()} · {String(r.status)} ·{" "}
            {String(r.created_at).slice(0, 16)}
          </option>
        ))}
      </select>
    </label>
  );
}
export function ContextGate({ children }: { children: React.ReactNode }) {
  const scope = useScope();
  return scope.period && scope.entity && scope.client ? (
    children
  ) : (
    <Empty title="Choose your financial context">
      Select a client, entity and financial period in the header to open this
      workbench.
    </Empty>
  );
}
export function Future({
  title,
  phase = 4,
  description,
}: {
  title: string;
  phase?: number;
  description?: string;
}) {
  return (
    <section className="card future">
      <Badge tone="blue">Phase {phase}</Badge>
      <Empty title={title}>
        {description ||
          "This workflow is not yet available. No completion or compliance result has been recorded."}
      </Empty>
    </section>
  );
}
export function AIRequest({
  task,
  accountId,
  lineId,
  runId,
  snapshot,
}: {
  task: string;
  accountId?: string;
  lineId?: string;
  runId?: string;
  snapshot: string;
}) {
  const action = useAction<RecordRow>();
  const can = useCan("financial_ai.execute");
  const review = useAction();
  const canReview = useCan("financial_ai.approve");
  const models = useAPI<{ key?: string; name?: string; model?: string }[]>(
    "ai/models",
    can,
  );
  const [model, setModel] = useState("mock-diagnostic");
  const result = action.data;
  return (
    <section className="card ai-request">
      <h3>
        <Sparkles size={16} /> AI-supported investigation
      </h3>
      <p className="subtle">
        Structured suggestion • human review required. No ledger changes.
      </p>
      <label>
        Approved model
        <select
          aria-label="AI model"
          value={model}
          onChange={(e) => setModel(e.target.value)}
        >
          <option value="mock-diagnostic">
            Mock diagnostic · no live provider
          </option>
          {models.data
            ?.filter((m) => (m.key || m.name) !== "mock-diagnostic")
            .map((m) => (
              <option key={m.key || m.name} value={m.key || m.name}>
                {m.key || m.name}
              </option>
            ))}
        </select>
      </label>
      <Button
        primary
        disabled={!can || action.isPending}
        onClick={() =>
          action.mutate({
            path: "ai/" + task,
            body: {
              snapshot_id: snapshot,
              model,
              account_id: accountId,
              line_ids: lineId ? [lineId] : [],
              analytics_run_id: runId,
            },
          })
        }
      >
        <Sparkles size={14} />
        {action.isPending
          ? "Executing…"
          : "Request " + task.replaceAll("-", " ")}
      </Button>
      <ErrorState error={action.error} />
      {result && (
        <>
          <Badge tone="warning">
            {model === "mock-diagnostic"
              ? "Mock diagnostic result"
              : "AI suggestion"}{" "}
            · Review required
          </Badge>
          <div className="structured-output">
            <Facts
              data={
                (result.output || result.suggestion || result) as Record<
                  string,
                  unknown
                >
              }
            />
          </div>
          {typeof result.suggestion_id === "string" && canReview && (
            <div className="actions">
              <Button
                disabled={review.isPending || !!review.data}
                onClick={() =>
                  review.mutate({
                    path: `ai/suggestions/${result.suggestion_id}/review`,
                    body: { decision: "approved" },
                  })
                }
              >
                Approve suggestion
              </Button>
              <Button
                disabled={review.isPending || !!review.data}
                onClick={() =>
                  review.mutate({
                    path: `ai/suggestions/${result.suggestion_id}/review`,
                    body: { decision: "rejected" },
                  })
                }
              >
                Reject
              </Button>
            </div>
          )}
          <ErrorState error={review.error} />
          {review.data && <Status value={review.data.review_status} />}
        </>
      )}
    </section>
  );
}
export function LineageDetail({ id }: { id: string }) {
  const q = useAPI<RecordRow>("accounting/lineage/" + id);
  return (
    <QueryState query={q}>
      {q.data && (
        <>
          <h3>
            <LinkIcon size={16} /> Original source lineage
          </h3>
          <LineageGraph
            source={String((q.data.source_record as RecordRow)?.id)}
            snapshot={String((q.data.snapshot as RecordRow)?.id)}
            line={id}
          />
          {Object.entries(q.data)
            .filter(([, v]) => v && typeof v === "object")
            .map(([key, value]) => (
              <details key={key} open={key === "journal_line"}>
                <summary>{key.replaceAll("_", " ")}</summary>
                <Facts data={value as Record<string, unknown>} />
              </details>
            ))}
        </>
      )}
    </QueryState>
  );
}
export function JobProgress({
  id,
  onDone,
}: {
  id: string;
  onDone?: () => void;
}) {
  const q = useAPI<RecordRow>("jobs/" + id, true, true);
  const retry = useAction();
  const done = ["completed", "failed", "cancelled"].includes(
    String(q.data?.status),
  );
  return (
    <div className="job-progress">
      <QueryState query={q}>
        {q.data && (
          <>
            <div className="split">
              <Status value={q.data.status} />
              <span>{textValue(q.data.progress)}%</span>
            </div>
            <progress max={100} value={Number(q.data.progress || 0)} />
            <small>
              Backend job {id.slice(0, 8)} ·{" "}
              {textValue(q.data.error_category || q.data.job_type)}
            </small>
            {q.data.status === "failed" && (
              <Button
                disabled={retry.isPending}
                onClick={() => retry.mutate({ path: "jobs/" + id + "/retry" })}
              >
                Retry failed job
              </Button>
            )}
            {done && onDone && (
              <Button onClick={onDone}>
                <Play size={12} /> Refresh workflow result
              </Button>
            )}
          </>
        )}
      </QueryState>
      <ErrorState error={retry.error} />
    </div>
  );
}

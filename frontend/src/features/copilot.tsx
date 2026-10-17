"use client";
import {
  Badge,
  Button,
  ErrorState,
  Facts,
  Status,
} from "@/components/ui/primitives";
import { useAPI, useAction, useCan, usePopulation } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import {
  BookOpen,
  FileSearch,
  MessageSquareText,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import {
  ContextGate,
  LineageDetail,
  PageHeader,
  PopulationPicker,
} from "./shared";
const tasks = [
  {
    name: "Explain an unusual journal",
    task: "anomaly-explanation",
    icon: FileSearch,
    needs: "line",
  },
  {
    name: "Analyze an account movement",
    task: "financial-commentary",
    icon: BookOpen,
    needs: "account",
  },
  {
    name: "Suggest audit procedures",
    task: "audit-procedures",
    icon: ShieldCheck,
    needs: "line",
  },
  {
    name: "Suggest account classification",
    task: "account-classification",
    icon: Sparkles,
    needs: "account",
  },
];
export function Copilot() {
  return (
    <>
      <PageHeader
        eyebrow="Financial investigation"
        title="AI Audit Copilot"
        description="Contextual financial intelligence with traceable evidence and human review."
        actions={
          <Badge tone="warning">No audit opinion or ledger changes</Badge>
        }
      />
      <ContextGate>
        <CopilotBody />
      </ContextGate>
    </>
  );
}
function CopilotBody() {
  const pop = usePopulation(),
    scope = useScope();
  const [task, setTask] = useState(tasks[0]),
    [account, setAccount] = useState(""),
    [line, setLine] = useState(""),
    [model, setModel] = useState("mock-diagnostic"),
    [history, setHistory] = useState<
      { task: string; result: RecordRow; model: string }[]
    >([]),
    [selected, setSelected] = useState(-1);
  const can = useCan("financial_ai.execute");
  const models = useAPI<{ name: string }[]>("ai/models", useCan("ai.read"));
  const accounts = useAPI<Page<RecordRow>>(
    "accounting/accounts?" + qs({ entity_id: scope.entity, limit: 100 }),
  );
  const lines = useAPI<Page<RecordRow>>(
    "workspace/ledger?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        snapshot_id: pop.snapshot,
        account_id: account,
        limit: 50,
      }),
    !!pop.snapshot,
  );
  const action = useAction<RecordRow>();
  const current = history[selected] || history[history.length - 1];
  const review = useAction<RecordRow>();
  const canReview = useCan("financial_ai.approve");
  return (
    <div className="copilot-layout">
      <aside className="copilot-tasks">
        <h3>
          <Sparkles size={17} /> Investigation workspace
        </h3>
        <p className="subtle">Choose a structured financial task.</p>
        {tasks.map((t) => (
          <button
            key={t.task}
            className={"task-button" + (t.task === task.task ? " active" : "")}
            onClick={() => setTask(t)}
          >
            <t.icon size={17} />
            {t.name}
          </button>
        ))}
        <h4>This session</h4>
        {history.length ? (
          history.map((h, i) => (
            <button
              className="history-item"
              key={i}
              onClick={() => setSelected(i)}
            >
              <MessageSquareText size={14} />
              {h.task}
              <Status value={h.result.status || "pending_review"} />
            </button>
          ))
        ) : (
          <p className="subtle">
            Executions appear here after a request. Conversation history is not
            stored by this frontend.
          </p>
        )}
        <div className="copilot-disclosure">
          <ShieldCheck size={18} />
          <p>
            Only permitted, snapshot-scoped evidence reaches the AI gateway.
            Suggestions require professional review.
          </p>
        </div>
      </aside>
      <section className="copilot-main">
        <div className="toolbar">
          <PopulationPicker />
          <select
            aria-label="Copilot model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="mock-diagnostic">
              Mock diagnostic · no live AI
            </option>
            {models.data
              ?.filter((m) => m.name !== "mock-diagnostic")
              .map((m) => (
                <option key={m.name}>{m.name}</option>
              ))}
          </select>
        </div>
        <div className="copilot-conversation">
          {current ? (
            <>
              <div className="request-bubble">
                <Sparkles size={17} />
                <strong>{current.task}</strong>
                <small>{current.model}</small>
              </div>
              <article className="card response-card">
                <h3>
                  <span className="ai-orb">✦</span> Structured investigation
                  response
                </h3>
                <Badge tone="warning">
                  {current.model === "mock-diagnostic"
                    ? "Mock diagnostic — no live provider"
                    : "AI-generated suggestion"}{" "}
                  · Review required
                </Badge>
                {current.result.error_category ? (
                  <div className="error">
                    Execution failed: {textValue(current.result.error_category)}
                  </div>
                ) : (
                  <Facts
                    data={
                      (current.result.output || {}) as Record<string, unknown>
                    }
                  />
                )}
                <div className="source-citations">
                  <h4>Evidence references</h4>
                  {(
                    ((current.result.output as Record<string, unknown>)
                      ?.citations as string[]) || []
                  ).map((c) => (
                    <code key={c}>{c}</code>
                  ))}
                </div>
                <Facts
                  data={{
                    execution_id: current.result.execution_id,
                    prompt_version: current.result.prompt_version,
                    review_status: current.result.review_status,
                  }}
                />
                {canReview && !!current.result.suggestion_id && (
                  <div className="actions">
                    <Button
                      disabled={review.isPending || !!review.data}
                      onClick={() =>
                        review.mutate({
                          path: `ai/suggestions/${current.result.suggestion_id}/review`,
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
                          path: `ai/suggestions/${current.result.suggestion_id}/review`,
                          body: { decision: "rejected" },
                        })
                      }
                    >
                      Reject suggestion
                    </Button>
                  </div>
                )}
                <ErrorState error={review.error} />
                {review.data && <Status value={review.data.review_status} />}
              </article>
            </>
          ) : (
            <div className="copilot-welcome">
              <span className="ai-orb">✦</span>
              <h2>Investigate with evidence.</h2>
              <p>
                Choose a financial population and an account or journal line.
                <br />
                The approved gateway returns a structured, cited response.
              </p>
              <div className="prompt-grid">
                {tasks.map((t) => (
                  <button key={t.task} onClick={() => setTask(t)}>
                    <t.icon size={19} />
                    <strong>{t.name}</strong>
                    <small>Uses selected financial context</small>
                  </button>
                ))}
              </div>
            </div>
          )}
          {action.isPending && (
            <div className="card" role="status">
              Executing approved AI task against scoped evidence…
            </div>
          )}
        </div>
        <form
          className="copilot-composer"
          onSubmit={(e) => {
            e.preventDefault();
            action.mutate(
              {
                path: "ai/" + task.task,
                body: {
                  snapshot_id: pop.snapshot,
                  model,
                  account_id: account || null,
                  line_ids: line ? [line] : [],
                },
              },
              {
                onSuccess: (r) => {
                  setHistory((h) => [
                    ...h,
                    { task: task.name, result: r, model },
                  ]);
                  setSelected(history.length);
                  review.reset();
                },
              },
            );
          }}
        >
          <div>
            <strong>{task.name}</strong>
            <span>Structured task · no unrestricted SQL or free-form chat</span>
          </div>
          <Button
            primary
            disabled={
              !can ||
              !pop.snapshot ||
              action.isPending ||
              (task.needs === "line" ? !line : !account)
            }
          >
            <Send size={15} /> Execute task
          </Button>
          <ErrorState error={action.error} />
        </form>
      </section>
      <aside className="copilot-context">
        <h3>Financial data context</h3>
        <Badge tone="blue">Authorized snapshot</Badge>
        <label>
          Account
          <select
            aria-label="Copilot account"
            value={account}
            onChange={(e) => {
              setAccount(e.target.value);
              setLine("");
            }}
          >
            <option value="">Select account</option>
            {accounts.data?.items.map((a) => (
              <option key={a.id} value={a.id}>
                {textValue(a.code)} · {textValue(a.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Journal line
          <select
            aria-label="Copilot journal line"
            value={line}
            onChange={(e) => setLine(e.target.value)}
          >
            <option value="">Select journal line</option>
            {lines.data?.items.map((l) => (
              <option key={l.id} value={l.id}>
                {textValue(l.voucher_number)} ·{" "}
                {textValue(l.description).slice(0, 35)}
              </option>
            ))}
          </select>
        </label>
        <small className="subtle">
          First 100 accounts / 50 source lines. Use Ledger for full population
          exploration.
        </small>
        <Facts
          data={{
            population: pop.snapshot || "No committed source",
            entity_id: scope.entity,
            period_id: scope.period,
          }}
        />
        {line && (
          <details>
            <summary>Selected source evidence</summary>
            <LineageDetail id={line} />
          </details>
        )}
        <ErrorState error={models.error || accounts.error || lines.error} />
      </aside>
    </div>
  );
}

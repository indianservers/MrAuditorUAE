"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import * as echarts from "echarts";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import { PageHeader } from "./shared";
import { Button, Empty, ErrorState } from "@/components/ui/primitives";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import type { Engagement, Page, RecordRow } from "@/types/models";

export const mlAreas = [
  ["overview", "ML Overview"],
  ["datasets", "Dataset Explorer"],
  ["features", "Feature Engineering Studio"],
  ["architecture", "Model Architecture Viewer"],
  ["training", "Training Studio"],
  ["evaluation", "Evaluation Dashboard"],
  ["confusion", "Confusion Matrix Explorer"],
  ["investigator", "Transaction Anomaly Investigator"],
  ["registry", "Model Registry"],
  ["deployment", "Model Deployment Center"],
  ["drift", "Model Drift Dashboard"],
  ["feedback", "AI Reviewer Feedback"],
] as const;
export const dmttAreas = [
  ["overview", "Pillar Two Executive Dashboard"],
  ["scope", "MNE Scope Assessment"],
  ["entities", "Constituent Entity Explorer"],
  ["income", "GloBE Income Adjustment Studio"],
  ["taxes", "Covered Taxes Workbench"],
  ["deferred", "Deferred Tax & Transition Studio"],
  ["etr", "Jurisdictional ETR Dashboard"],
  ["sbie", "Substance-Based Income Exclusion"],
  ["topup", "Top-up Tax Calculator"],
  ["elections", "Safe Harbour & Elections"],
  ["reporting", "DMTT Reporting & Documentation"],
  ["ai", "AI Pillar Two Research Assistant"],
] as const;
type Event = RecordRow & {
  kind: string;
  freshness?: { status: string };
  body: Record<string, unknown>;
  created_at: string;
};
type ModelMetrics = {
  config: { family: string };
  history: { epoch: number; loss: number; val_loss: number }[];
  evaluation: Record<string, unknown>;
  architecture: unknown;
  feature_schema: unknown;
  counts: unknown;
  resources: unknown;
};
function Json({ data }: { data: unknown }) {
  return <pre className="p9-json">{JSON.stringify(data, null, 2)}</pre>;
}

function MetricCards({ values }: { values: Record<string, unknown> }) {
  return (
    <div className="p9-metrics">
      {Object.entries(values).map(([label, value]) => (
        <article key={label}>
          <span>{label.replaceAll("_", " ")}</span>
          <strong className={label === "status" ? "p9-status-text" : undefined}>
            {value === null || value === undefined
              ? "Not assessed"
              : typeof value === "number"
                ? value.toLocaleString(undefined, { maximumFractionDigits: 5 })
                : label === "etr" && Number.isFinite(Number(value))
                  ? Number(value).toLocaleString(undefined, {
                      style: "percent",
                      maximumFractionDigits: 2,
                    })
                  : /^-?\d+(\.\d+)?$/.test(String(value))
                    ? Number(value).toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })
                    : String(value).replaceAll("_", " ")}
          </strong>
        </article>
      ))}
    </div>
  );
}
function ConfusionChart({ matrix }: { matrix: number[][] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !matrix.length) return;
    const c = echarts.init(ref.current),
      values = matrix.flatMap((row, y) => row.map((v, x) => [x, y, v]));
    c.setOption({
      tooltip: {},
      grid: { top: 30, left: 80, bottom: 70, right: 100 },
      xAxis: {
        type: "category",
        name: "Predicted",
        nameLocation: "middle",
        nameGap: 35,
        data: matrix.map((_, i) => String(i)),
      },
      yAxis: {
        type: "category",
        name: "Actual",
        data: matrix.map((_, i) => String(i)),
      },
      visualMap: {
        min: 0,
        max: Math.max(...matrix.flat()),
        calculable: true,
        orient: "vertical",
        right: 0,
      },
      series: [{ type: "heatmap", data: values, label: { show: true } }],
    });
    const o = new ResizeObserver(() => c.resize());
    o.observe(ref.current);
    return () => {
      o.disconnect();
      c.dispose();
    };
  }, [matrix]);
  return (
    <div
      ref={ref}
      style={{ height: 380 }}
      aria-label="Held-out confusion matrix"
    />
  );
}
function LossChart({ history }: { history: ModelMetrics["history"] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !history.length) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["Training loss", "Validation loss"] },
      grid: { left: 65, right: 30, bottom: 40, top: 40 },
      xAxis: {
        type: "category",
        data: history.map((x) => x.epoch),
        name: "Epoch",
      },
      yAxis: { type: "value", scale: true },
      series: [
        {
          name: "Training loss",
          type: "line",
          data: history.map((x) => x.loss),
        },
        {
          name: "Validation loss",
          type: "line",
          data: history.map((x) => x.val_loss),
        },
      ],
    });
    const o = new ResizeObserver(() => chart.resize());
    o.observe(ref.current);
    return () => {
      o.disconnect();
      chart.dispose();
    };
  }, [history]);
  return (
    <div
      ref={ref}
      style={{ height: 300 }}
      aria-label="Measured training and validation loss"
    />
  );
}

export function Phase9Studio({
  mode,
  area = "overview",
}: {
  mode: "ml" | "dmtt";
  area?: string;
}) {
  const directory = useAPI<Page<Engagement>>("engagements?limit=100");
  const [eid, setEid] = useState("");
  const areas = mode === "ml" ? mlAreas : dmttAreas;
  const entry = areas.find((x) => x[0] === area);
  return (
    <>
      <PageHeader
        eyebrow={
          mode === "ml"
            ? "Audit ML / governed experiments"
            : "UAE Pillar Two / technical review"
        }
        title={entry?.[1] || "Unknown workspace"}
        description={
          mode === "ml"
            ? "Measured TensorFlow.js signals · Deterministic rules remain separate · No fraud conclusion"
            : "Approved financial sources · Versioned rules · Decimal calculations"
        }
      />
      <nav className="audit-tabs" aria-label="Phase 9 workspaces">
        {areas.map(([key, title]) => (
          <Link
            key={key}
            aria-current={key === area ? "page" : undefined}
            href={`${mode === "ml" ? "/ai-lab" : "/pillar-two"}/${key}`}
          >
            {title}
          </Link>
        ))}
      </nav>
      <div className="p9-body">
        <label>
          Engagement
          <select
            aria-label="Phase 9 engagement"
            value={eid}
            onChange={(e) => setEid(e.target.value)}
          >
            <option value="">Choose authorized engagement</option>
            {directory.data?.items.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        {directory.error && <ErrorState error={directory.error} />}{" "}
        {eid ? (
          mode === "ml" ? (
            <MLPanel key={eid + area} eid={eid} area={area} />
          ) : (
            <DMTTPanel key={eid + area} eid={eid} area={area} />
          )
        ) : (
          <Empty title="Choose an engagement">
            Data access follows the existing engagement team permissions.
          </Empty>
        )}
      </div>
    </>
  );
}

function MLPanel({ eid, area }: { eid: string; area: string }) {
  const events = useAPI<{ items: Event[]; total: number }>(
    `ml/events?eid=${eid}&limit=100`,
  );
  const action = useAction<{ id: string; status?: string }>();
  const canTrain = useCan("ml.train"),
    canApprove = useCan("ml.approve"),
    canDeploy = useCan("ml.deploy");
  const [selected, setSelected] = useState(""),
    [dataset, setDataset] = useState(""),
    [deployment, setDeployment] = useState(""),
    [family, setFamily] = useState("autoencoder"),
    [epochs, setEpochs] = useState(12),
    [batch, setBatch] = useState(128),
    [lr, setLr] = useState(0.003),
    [patience, setPatience] = useState(3),
    [job, setJob] = useState(""),
    [rationale, setRationale] = useState(""),
    [ack, setAck] = useState(false),
    [offset, setOffset] = useState(0),
    [feedback, setFeedback] = useState("false_positive"),
    [transaction, setTransaction] = useState(""),
    [evidence, setEvidence] = useState("");
  const rows = events.data?.items || [],
    models = rows.filter((x) => x.kind === "model"),
    datasets = rows.filter((x) => x.kind === "dataset"),
    model = models.find((x) => x.id === selected),
    metrics = model?.body.metrics as ModelMetrics | undefined;
  const status = useAPI<{
    status: string;
    epochs: ModelMetrics["history"];
    result: { resource_id?: string };
  }>(`ml/jobs/${job}`, !!job, true);
  const inference = rows.find(
    (x) => x.kind === "inference" && x.id === selected,
  );
  const history = status.data?.epochs?.length
    ? status.data.epochs
    : metrics?.history || [];
  const heldout = metrics?.evaluation.test as
    | {
        model?: Record<string, unknown>;
        confusion_matrix?: number[][];
        accuracy?: number;
        n?: number;
      }
    | undefined;
  const measured = (heldout?.model || heldout) as
    Record<string, unknown> | undefined;
  const start = async () => {
    const result = await action.mutateAsync({
      path: "ml/training-jobs",
      body: {
        source_id: dataset,
        family,
        epochs,
        batch_size: batch,
        learning_rate: lr,
        patience,
        seed: 2026,
      },
    });
    setJob(result.id);
  };
  return (
    <>
      {rows.some((r) => r.freshness?.status === "STALE") && (
        <p role="alert">
          Some historical ML results have stale source data. Regenerate
          features, train and review before further use.
        </p>
      )}
      {events.error && <ErrorState error={events.error} />}{" "}
      {action.error && <ErrorState error={action.error} />}
      <div className="source-strip">
        Experimental synthetic validation demonstrates software feasibility.
        Scores are review signals; they are not fraud or audited misstatement
        probabilities.
      </div>
      <div className="toolbar">
        <label>
          Model version
          <select
            aria-label="Model version"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choose model or inference</option>
            {models.map((x) => (
              <option key={x.id} value={x.id}>
                {String((x.body.metrics as ModelMetrics).config.family)} ·{" "}
                {x.id.slice(0, 8)}
              </option>
            ))}
            {rows
              .filter((x) => x.kind === "inference")
              .map((x) => (
                <option key={x.id} value={x.id}>
                  Inference {x.id.slice(0, 8)}
                </option>
              ))}
          </select>
        </label>
        <label>
          Dataset
          <select
            aria-label="Training dataset"
            value={dataset}
            onChange={(e) => setDataset(e.target.value)}
          >
            <option value="">Choose versioned dataset</option>
            {datasets.map((x) => (
              <option key={x.id} value={x.id}>
                {String(x.body.seed_version || x.id)} ·{" "}
                {String(x.body.total_rows)} rows
              </option>
            ))}
          </select>
        </label>
      </div>
      {area === "training" && (
        <section className="p9-card">
          <h2>Train a TensorFlow.js model</h2>
          <div className="toolbar">
            <label>
              Family
              <select
                aria-label="Model family"
                value={family}
                onChange={(e) => setFamily(e.target.value)}
              >
                {[
                  "autoencoder",
                  "journal-classifier",
                  "risk-ranking",
                  "account-classifier",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Epoch limit
              <input
                aria-label="Epoch limit"
                type="number"
                min={1}
                max={100}
                value={epochs}
                onChange={(e) => setEpochs(+e.target.value)}
              />
            </label>
            <label>
              Batch size
              <input
                aria-label="Batch size"
                type="number"
                min={8}
                max={1024}
                value={batch}
                onChange={(e) => setBatch(+e.target.value)}
              />
            </label>
            <label>
              Learning rate
              <input
                aria-label="Learning rate"
                type="number"
                step="0.001"
                value={lr}
                onChange={(e) => setLr(+e.target.value)}
              />
            </label>
            <label>
              Early stopping patience
              <input
                aria-label="Early stopping patience"
                type="number"
                min={1}
                max={20}
                value={patience}
                onChange={(e) => setPatience(+e.target.value)}
              />
            </label>
          </div>
          <Button
            disabled={!dataset || !canTrain || action.isPending}
            onClick={start}
          >
            Start training
          </Button>{" "}
          {job && (
            <Button
              disabled={action.isPending}
              onClick={() => action.mutate({ path: `ml/jobs/${job}/cancel` })}
            >
              Cancel active training
            </Button>
          )}
          <p role="status">
            {status.data?.status || "No active training selected"}
          </p>
          <LossChart history={history} />
          <Json data={status.data || metrics?.resources} />
        </section>
      )}
      {["overview", "datasets", "registry"].includes(area) && (
        <>
          <h2>
            {area === "datasets"
              ? "Private dataset versions"
              : "Immutable registry history"}
          </h2>
          {area === "datasets" && (
            <Button
              disabled={!canTrain}
              onClick={async () => {
                const r = await action.mutateAsync({
                  path: `ml/engagements/${eid}/datasets`,
                });
                setJob(r.id);
              }}
            >
              Build private GL dataset
            </Button>
          )}
          <FinancialDataGrid
            rows={(area === "datasets" ? datasets : rows).map((x) => ({
              id: x.id,
              kind: x.kind,
              created_at: x.created_at,
              parent_id: x.parent_id,
              sha256: x.sha256,
            }))}
            columns={[
              column("kind", "Resource"),
              column("id", "Version"),
              column("created_at", "Created"),
              column("parent_id", "Source"),
            ]}
            exportable={false}
          />
          <Json data={datasets.find((x) => x.id === dataset)?.body} />
        </>
      )}
      {area === "features" && (
        <>
          <h2>Saved feature definition and train-only transformations</h2>
          <Json data={metrics?.feature_schema} />
          <p>
            Labels, outcomes, review status and tenant identifiers are excluded
            from predictive inputs. Missing source attributes are explicit.
          </p>
        </>
      )}
      {area === "architecture" && (
        <>
          <h2>Trained model topology</h2>
          <Json data={metrics?.architecture} />
        </>
      )}
      {["evaluation", "confusion"].includes(area) && (
        <>
          <LossChart history={history} />
          <h2>Held-out and out-of-distribution evaluation</h2>
          <MetricCards
            values={{
              precision: measured?.precision,
              recall: measured?.recall,
              f1: measured?.f1,
              accuracy: measured?.accuracy,
              evaluation_rows: measured?.n,
            }}
          />
          {area === "confusion" && measured?.confusion_matrix && (
            <ConfusionChart matrix={measured.confusion_matrix as number[][]} />
          )}
          <Json data={metrics?.evaluation} />
          <p>
            Compare each metric with its baseline and dataset scope before
            promotion.
          </p>
        </>
      )}
      {area === "deployment" && (
        <section className="p9-card">
          <h2>Independent approval and rollback</h2>
          <label>
            Review rationale
            <textarea
              aria-label="Model review rationale"
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />{" "}
            I acknowledge experimental use and the recorded validation limits
          </label>
          <div className="toolbar">
            {[
              ["approval-requests", "Request approval", canTrain],
              ["approvals", "Approve model", canApprove],
              ["deployments", "Deploy / roll back to this version", canDeploy],
            ].map(([path, title, allowed]) => (
              <Button
                key={String(path)}
                disabled={
                  !selected || !allowed || rationale.length < 20 || !ack
                }
                onClick={() =>
                  action.mutate({
                    path: `ml/models/${selected}/${path}`,
                    body: { rationale, experimental_use_acknowledged: ack },
                  })
                }
              >
                {title}
              </Button>
            ))}
          </div>
          <label>
            Deployment
            <select
              aria-label="Inference deployment"
              value={deployment}
              onChange={(e) => setDeployment(e.target.value)}
            >
              <option value="">Choose deployment</option>
              {rows
                .filter((x) => x.kind === "deployment")
                .map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.id}
                  </option>
                ))}
            </select>
          </label>
          <Button
            disabled={!deployment || !dataset}
            onClick={async () => {
              const r = await action.mutateAsync({
                path: "ml/inference/batches",
                body: {
                  source_id: deployment,
                  dataset_id: dataset,
                  offset,
                  limit: 1000,
                },
              });
              setJob(r.id);
            }}
          >
            Score next 1,000 records
          </Button>
          <label>
            Batch offset
            <input
              aria-label="Batch offset"
              type="number"
              min={0}
              value={offset}
              onChange={(e) => setOffset(+e.target.value)}
            />
          </label>
        </section>
      )}
      {area === "investigator" && (
        <>
          <h2>Source-linked predictions and deterministic signals</h2>
          <FinancialDataGrid
            rows={(
              (inference?.body.predictions || []) as Record<string, unknown>[]
            ).map((p) => ({ id: String(p.transaction_id), ...p }))}
            columns={[
              column("transaction_id", "Source transaction"),
              column("score", "ML score"),
              column("threshold", "Threshold"),
              column("reconstruction_error", "Reconstruction error"),
            ]}
            onSelect={(p) => setTransaction(p.id)}
            exportable={false}
          />
          <label>
            Selected source transaction
            <input
              aria-label="Explanation transaction"
              value={transaction}
              onChange={(e) => setTransaction(e.target.value)}
            />
          </label>
          <Button
            disabled={!inference || !transaction}
            onClick={() =>
              action.mutate({
                path: `ml/predictions/${selected}/explanation`,
                body: { transaction_id: transaction, model: "mock-diagnostic" },
              })
            }
          >
            Explain validated factors
          </Button>
          <Json data={action.data} />
          <p>
            Attribution is approximate and is not a causal explanation. Account
            suggestions never replace approved mappings.
          </p>
        </>
      )}
      {area === "drift" && (
        <>
          <h2>Measured input distribution changes</h2>
          <FinancialDataGrid
            rows={(
              (inference?.body.drift || []) as Record<string, unknown>[]
            ).map((p) => ({ id: String(p.feature), ...p }))}
            columns={[
              column("feature", "Feature index"),
              column("standardized_mean_shift", "Mean shift / baseline SD"),
              column("outside_baseline_range", "Outside baseline"),
              column("missing", "Missing"),
            ]}
            exportable={false}
          />
          <Json data={inference?.body.drift} />
          <p>
            Unlabeled distribution shift does not establish a decline in
            accuracy.
          </p>
        </>
      )}
      {area === "feedback" && (
        <>
          <h2>Evidence-backed reviewer feedback</h2>
          <label>
            Transaction ID
            <input
              aria-label="Feedback transaction"
              value={transaction}
              onChange={(e) => setTransaction(e.target.value)}
            />
          </label>
          <label>
            Approved evidence ID
            <input
              aria-label="Feedback evidence"
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          </label>
          <label>
            Outcome
            <select
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
            >
              {[
                "false_positive",
                "valid_exception",
                "confirmed_misstatement",
                "insufficient_evidence",
                "no_issue",
              ].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label>
            Rationale
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          <Button
            disabled={
              !inference || !evidence || !transaction || rationale.length < 20
            }
            onClick={() =>
              action.mutate({
                path: `ml/predictions/${selected}/feedback`,
                body: {
                  transaction_id: transaction,
                  evidence_id: evidence,
                  label: feedback,
                  rationale,
                },
              })
            }
          >
            Record feedback for curation
          </Button>
          <Json
            data={rows.filter((x) => x.kind === "feedback").map((x) => x.body)}
          />
        </>
      )}
      {!model &&
        !inference &&
        !["datasets", "overview", "training", "registry"].includes(area) && (
          <Empty title="Choose a saved model or inference">
            Only persisted backend measurements are displayed.
          </Empty>
        )}
    </>
  );
}

function DMTTPanel({ eid, area }: { eid: string; area: string }) {
  const base = `dmtt/engagements/${eid}`;
  const kind = ["scope", "overview"].includes(area)
    ? "group"
    : area === "elections"
      ? "election"
      : area === "reporting"
        ? "memo"
        : "entity";
  const records = useAPI<{ items: Event[] }>(`${base}/records/${kind}`),
    groups = useAPI<{ items: Event[] }>(`${base}/records/group`),
    runs = useAPI<{ items: Event[] }>(`${base}/calculations`),
    workspace = useAPI<{ schemas: unknown; rules: unknown; tasks?: string[] }>(
      `${base}/workspace`,
    );
  const action = useAction();
  const [group, setGroup] = useState(""),
    [record, setRecord] = useState(""),
    [body, setBody] = useState("{}"),
    [title, setTitle] = useState(""),
    [reference, setReference] = useState(""),
    [rationale, setRationale] = useState(""),
    [task, setTask] = useState("scope_explanation");
  const chosen = records.data?.items.find((x) => x.id === record);
  const result = runs.data?.items.find((x) => x.body.group_id === group);
  const canPrepare = useCan("dmtt.prepare"),
    canApprove = useCan("dmtt.approve");
  return (
    <>
      {records.error && <ErrorState error={records.error} />}{" "}
      {action.error && <ErrorState error={action.error} />}
      <div className="source-strip">
        Draft technical workbench. Unsupported blending, transition and
        recapture cases block calculation. Safe harbour eligibility requires
        reviewed evidence.
      </div>
      <label>
        Approved group
        <select
          aria-label="DMTT group"
          value={group}
          onChange={(e) => setGroup(e.target.value)}
        >
          <option value="">Choose group</option>
          {groups.data?.items.map((x) => (
            <option key={x.id} value={x.id}>
              {String(x.title)} · {String(x.status)}
            </option>
          ))}
        </select>
      </label>
      <Button
        disabled={!group}
        onClick={() =>
          action.mutate({ path: `${base}/groups/${group}/calculate` })
        }
      >
        Calculate reviewed jurisdiction
      </Button>
      {["overview", "etr", "sbie", "topup"].includes(area) && (
        <>
          <h2>Immutable jurisdictional result</h2>
          <MetricCards
            values={Object.fromEntries(
              [
                "currency",
                "status",
                "net_globe_income",
                "covered_taxes",
                "etr",
                "sbie",
                "uae_dmtt",
              ].map((k) => [
                k,
                (result?.body.results as Record<string, unknown> | undefined)?.[
                  k
                ],
              ]),
            )}
          />
          <Json data={result?.body.results} />
        </>
      )}
      <FinancialDataGrid
        rows={records.data?.items || []}
        columns={[
          column("reference", "Reference"),
          column("title", "Workpaper"),
          column("status", "Review status"),
        ]}
        onSelect={(r) => {
          setRecord(r.id);
          setBody(JSON.stringify(r.body, null, 2));
          setTitle(String(r.title));
          setReference(String(r.reference));
        }}
        exportable={false}
      />
      {area === "ai" ? (
        <section className="p9-card">
          <h2>Source-grounded technical request</h2>
          <select
            aria-label="DMTT AI task"
            value={task}
            onChange={(e) => setTask(e.target.value)}
          >
            {[
              "scope_explanation",
              "revenue_threshold",
              "entity_classification",
              "globe_adjustments",
              "covered_taxes",
              "deferred_tax_review",
              "transition_rules",
              "sbie_review",
              "safe_harbour_review",
              "election_impact",
              "topup_variance",
              "technical_memo",
              "missing_evidence",
              "group_information_request",
              "regulatory_comparison",
            ].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          <Button
            disabled={!group}
            onClick={() =>
              action.mutate({
                path: `${base}/ai`,
                body: { group_id: group, task, model: "mock-diagnostic" },
              })
            }
          >
            Generate technical suggestion
          </Button>
          <Json data={action.data} />
        </section>
      ) : (
        <section className="p9-card">
          <h2>{kind} workpaper · source and approval controls</h2>
          <label>
            Reference
            <input
              aria-label="DMTT reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
          <label>
            Title
            <input
              aria-label="DMTT title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Structured fields
            <textarea
              aria-label="DMTT structured fields"
              className="p9-editor"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
          <div className="toolbar">
            <Button
              disabled={!canPrepare || !reference || !title}
              onClick={() => {
                try {
                  action.mutate({
                    path: `${base}/records/${kind}`,
                    body: { reference, title, body: JSON.parse(body) },
                  });
                } catch {
                  setRationale(
                    "Invalid JSON: correct the structured fields before saving.",
                  );
                }
              }}
            >
              Create reviewed source draft
            </Button>
            <Button
              onClick={() => {
                setRecord("");
                setBody("{}");
                setTitle("");
                setReference("");
              }}
            >
              New draft
            </Button>
          </div>
          <label>
            Review rationale
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
            />
          </label>
          <div className="toolbar">
            {["submit", "approve", "return", "lock"].map((a) => (
              <Button
                key={a}
                disabled={
                  !chosen ||
                  rationale.length < 20 ||
                  (a === "submit" ? !canPrepare : !canApprove)
                }
                onClick={() =>
                  action.mutate({
                    path: `${base}/records/${record}/actions`,
                    body: {
                      action: a,
                      version: chosen?.version,
                      comments: rationale,
                    },
                  })
                }
              >
                {a}
              </Button>
            ))}
          </div>
          <details>
            <summary>Typed field schema and adopted rule sources</summary>
            <Json data={workspace.data} />
          </details>
        </section>
      )}
    </>
  );
}

"use client";
import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Position,
  MiniMap,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { ErrorState, Status, Button, Facts } from "@/components/ui/primitives";
import type { RecordRow } from "@/types/models";

type Item = {
  id: string;
  label: string;
  kind: string;
  type: string;
  status: string;
  freshness: string;
  version?: number;
  url?: string;
  api?: string;
  category?: string;
  description?: string;
  assigned_user?: string;
  last_updated?: string;
  has_exceptions?: boolean;
};
type Edge = {
  id: string;
  source: string;
  target: string;
  path: string;
  freshness: string;
  expected_version?: number;
  edge_type?: string;
};
type Graph = {
  nodes: Item[];
  edges: Edge[];
  package: { country: string; version: string; sha256: string };
  truncated: boolean;
  scope: string;
  graph_version?: string;
  categories?: { id: string; name: string }[];
};
const palette = [
  "#9c683b",
  "#637bad",
  "#bc621b",
  "#148463",
  "#a27b0c",
  "#137f87",
  "#b85f46",
  "#8356b2",
  "#4287ab",
];
export function WorkingPaperGraph({
  eid,
  lifecycle = false,
}: {
  eid: string;
  lifecycle?: boolean;
}) {
  const q = useAPI<Graph>(
    lifecycle
      ? `jurisdictions/engagements/${eid}/lifecycle`
      : `engagements/${eid}/audit/graph`,
    true,
    true,
  );
  const saved = useAPI<{
    version: number;
    graph_version: string;
    positions: Record<string, { x: number; y: number }>;
  }>(`jurisdictions/engagements/${eid}/layout`, lifecycle);
  const action = useAction();
  const [positions, setPositions] = useState<
    Record<string, { x: number; y: number }>
  >({});
  const [useSaved, setUseSaved] = useState(true),
    [dark, setDark] = useState(false),
    [layout, setLayout] = useState(lifecycle ? "radial" : "hierarchy");
  const [collapsed, setCollapsed] = useState(
    new Set(
      lifecycle ? ["01", "02", "03", "04", "05", "06", "07", "08", "09"] : [],
    ),
  );
  const [module, setModule] = useState("ALL"),
    [status, setStatus] = useState("ALL"),
    [exceptions, setExceptions] = useState(false),
    [direction, setDirection] = useState("BOTH");
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null);
  const [selected, setSelected] = useState<string | null>(null),
    [search, setSearch] = useState(""),
    [freshness, setFreshness] = useState("ALL"),
    [trace, setTrace] = useState(false);
  const current = q.data?.nodes.find((n) => n.id === selected);
  const savedPositions = saved.data?.positions;
  const detail = useAPI<RecordRow>(current?.api || "", !!current?.api);
  const view = useMemo(() => {
    const data = q.data;
    if (!data) return { nodes: [], edges: [] };
    const connected = new Set<string>();
    if (trace && selected) {
      connected.add(selected);
      let changed = true;
      while (changed) {
        changed = false;
        for (const e of data.edges.filter((e) => e.edge_type !== "CONTAINS"))
          if (
            (direction !== "UPSTREAM" && connected.has(e.source)) ||
            (direction !== "DOWNSTREAM" && connected.has(e.target))
          ) {
            if (!connected.has(e.source) || !connected.has(e.target))
              changed = true;
            if (direction !== "DOWNSTREAM") connected.add(e.source);
            if (direction !== "UPSTREAM") connected.add(e.target);
          }
      }
    }
    const matched = data.nodes.filter(
      (n) =>
        (module === "ALL" ||
          n.category === module ||
          n.type === "engagement") &&
        (status === "ALL" || n.status === status) &&
        (!exceptions || n.has_exceptions) &&
        (!lifecycle ||
          search ||
          trace ||
          exceptions ||
          n.type === "engagement" ||
          n.type === "category" ||
          !collapsed.has(n.category || "")) &&
        (!trace || !selected || connected.has(n.id)) &&
        (freshness === "ALL" || n.freshness === freshness) &&
        `${n.label} ${n.kind}`.toLowerCase().includes(search.toLowerCase()),
    );
    const displayed = new Set(matched.map((n) => n.id));
    if (lifecycle) {
      let changed = true;
      while (changed) {
        changed = false;
        for (const e of data.edges.filter((e) => e.edge_type === "CONTAINS")) {
          if (displayed.has(e.target) && !displayed.has(e.source)) {
            displayed.add(e.source);
            changed = true;
          }
        }
      }
    }
    const items = data.nodes.filter((n) => displayed.has(n.id)).slice(0, 250);
    const ids = new Set(items.map((n) => n.id));
    const edges = data.edges.filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    );
    const layers = new Map<string, number>(items.map((n) => [n.id, 0]));
    // Bounded relaxation also handles cycles without an infinite layout loop.
    for (let pass = 0; pass < Math.min(items.length, 8); pass++)
      for (const e of edges)
        layers.set(
          e.target,
          Math.min(
            8,
            Math.max(
              layers.get(e.target) || 0,
              (layers.get(e.source) || 0) + 1,
            ),
          ),
        );
    const lanes = new Map<number, number>();
    return {
      nodes: items.map((n) => {
        const layer = layers.get(n.id) || 0;
        const index = lanes.get(layer) || 0;
        lanes.set(layer, index + 1);
        return {
          id: n.id,
          className: "mr-audit-node",
          width: n.type === "engagement" ? 290 : 250,
          height: 112,
          ariaLabel: n.label,
          position:
            positions[n.id] ||
            (useSaved ? savedPositions?.[n.id] : undefined) ||
            (layout === "radial" && ["engagement", "category"].includes(n.type)
              ? n.type === "engagement"
                ? { x: 0, y: 0 }
                : {
                    x: Math.cos(((Number(n.kind) - 1) * Math.PI * 2) / 9) * 470,
                    y: Math.sin(((Number(n.kind) - 1) * Math.PI * 2) / 9) * 300,
                  }
              : { x: layer * 340, y: index * 120 }),
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: {
            label: `${n.label.length > 100 ? n.label.slice(0, 100) + "…" : n.label}\n${n.status} · ${n.freshness}`,
          },
          style: {
            width: n.type === "engagement" ? 290 : 250,
            whiteSpace: "pre-wrap" as const,
            border: `${n.id === selected ? 3 : 2}px solid ${["STALE", "BLOCKED"].includes(n.freshness) ? "#d97706" : palette[Number(n.category || "09") - 1] || "#4287ab"}`,
            background: dark ? "#142338" : "var(--surface)",
            color: dark ? "#eff6ff" : "var(--ink)",
            borderRadius: 12,
            padding: 16,
            fontSize: 15,
          },
        };
      }),
      edges: edges.map((e) => ({
        ...e,
        label:
          !lifecycle || e.source === selected || e.target === selected
            ? e.path
            : undefined,
        style: {
          opacity:
            e.edge_type === "CONTAINS"
              ? 0.3
              : e.source === selected || e.target === selected
                ? 0.95
                : 0.18,
          stroke:
            e.freshness === "STALE" ? "#d97706" : dark ? "#94a3b8" : "#64748b",
        },
        markerEnd: { type: MarkerType.ArrowClosed },
        animated: false,
      })),
    };
  }, [
    q.data,
    search,
    freshness,
    trace,
    selected,
    module,
    status,
    exceptions,
    collapsed,
    lifecycle,
    positions,
    savedPositions,
    useSaved,
    layout,
    dark,
    direction,
  ]);
  return (
    <section className="page-body" aria-label="Working-paper dependency graph">
      <div className="global-heading">
        <div>
          <span className="eyebrow">
            Mr Auditor · connected audit intelligence
          </span>
          <h2>
            {lifecycle
              ? "Audit lifecycle graph"
              : "Working-paper dependency graph"}
          </h2>
        </div>
        <Link href={`/engagements/${eid}/workspace`}>Engagement workspace</Link>
      </div>
      {q.data && (
        <p>
          Engagement package: <strong>{q.data.package.version}</strong>.{" "}
          {q.data.scope}.{" "}
          {q.data.truncated &&
            "This bounded view is incomplete; use the record registers for the full population."}
        </p>
      )}
      <p>
        Links come from saved source references and immutable dependency
        receipts. Staleness is separate from approval status; approved history
        is never silently rewritten.
      </p>
      <div className="toolbar">
        {lifecycle && (
          <>
            <select
              aria-label="Graph module filter"
              value={module}
              onChange={(e) => setModule(e.target.value)}
            >
              <option value="ALL">All modules</option>
              {q.data?.categories?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Graph workflow status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="ALL">All workflow / review states</option>
              {[...new Set(q.data?.nodes.map((n) => n.status))].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <label>
              <input
                type="checkbox"
                checked={exceptions}
                onChange={(e) => setExceptions(e.target.checked)}
              />
              Open exceptions
            </label>
          </>
        )}
        <input
          aria-label="Search graph"
          placeholder="Search records"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Graph freshness filter"
          value={freshness}
          onChange={(e) => setFreshness(e.target.value)}
        >
          {["ALL", "CURRENT", "STALE", "BLOCKED", "UNVERIFIED"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <label>
          <input
            type="checkbox"
            checked={trace}
            onChange={(e) => setTrace(e.target.checked)}
          />{" "}
          Trace selected relationships
        </label>
        <Button onClick={() => q.refetch()}>Refresh graph</Button>
        <select
          aria-label="Dependency direction"
          value={direction}
          onChange={(e) => {
            setDirection(e.target.value);
            setTrace(true);
          }}
        >
          <option value="BOTH">Cross-references</option>
          <option value="UPSTREAM">Upstream sources</option>
          <option value="DOWNSTREAM">Downstream impact</option>
        </select>
        {lifecycle && (
          <>
            <Button
              onClick={() =>
                setCollapsed(
                  collapsed.size
                    ? new Set()
                    : new Set([
                        "01",
                        "02",
                        "03",
                        "04",
                        "05",
                        "06",
                        "07",
                        "08",
                        "09",
                      ]),
                )
              }
            >
              {collapsed.size ? "Expand all categories" : "Collapse categories"}
            </Button>
            <Button onClick={() => setDark(!dark)}>
              {dark ? "Light canvas" : "Dark canvas"}
            </Button>
            <select
              aria-label="Graph layout"
              value={layout}
              onChange={(e) => {
                setLayout(e.target.value);
                setUseSaved(false);
                setPositions({});
              }}
            >
              <option value="radial">Radial overview</option>
              <option value="hierarchy">Dependency columns</option>
            </select>
            <Button
              onClick={() => {
                setPositions({});
                setUseSaved(false);
                flow?.fitView({ duration: 350 });
              }}
            >
              Reset layout
            </Button>
            <Button
              onClick={() =>
                action.mutate({
                  path: `jurisdictions/engagements/${eid}/layout`,
                  method: "PATCH",
                  body: {
                    version: saved.data?.version || 0,
                    graph_version: q.data?.graph_version,
                    positions: Object.fromEntries(
                      view.nodes.map((n) => [n.id, n.position]),
                    ),
                  },
                })
              }
              disabled={!saved.data || action.isPending}
            >
              Save layout
            </Button>
          </>
        )}
      </div>
      <ErrorState error={q.error || saved.error || action.error} />
      {view.nodes.length === 250 && (
        <p role="status">
          Progressive view limited to 250 nodes. Filter or collapse categories
          to explore the rest.
        </p>
      )}
      <div
        style={{
          height: lifecycle ? 650 : 520,
          border: "1px solid var(--border)",
        }}
      >
        <ReactFlow
          nodes={view.nodes}
          edges={view.edges}
          onInit={setFlow}
          onNodesChange={(changes) => {
            if (changes.some((c) => c.type === "position" && c.position))
              setPositions((previous) => {
                const next = { ...previous };
                for (const change of changes)
                  if (change.type === "position" && change.position)
                    next[change.id] = change.position;
                return next;
              });
          }}
          colorMode={dark ? "dark" : "light"}
          onlyRenderVisibleElements
          onNodeClick={(_, node) => setSelected(node.id)}
          nodesDraggable={lifecycle}
          nodesConnectable={false}
          edgesReconnectable={false}
          fitView
          maxZoom={1.2}
          minZoom={0.1}
        >
          <Background />
          <Controls />
          <MiniMap
            pannable
            zoomable
            bgColor={dark ? "#10243c" : "#f2f7fb"}
            maskColor={dark ? "rgba(8,15,25,.35)" : "rgba(215,226,239,.35)"}
            nodeStrokeColor={dark ? "#dbeafe" : "#405a76"}
            nodeColor={(node) =>
              palette[
                Number(
                  q.data?.nodes.find((n) => n.id === node.id)?.category || "09",
                ) - 1
              ] || "#4287ab"
            }
          />
        </ReactFlow>
      </div>
      <details>
        <summary>Accessible record list ({view.nodes.length})</summary>
        {q.data?.nodes
          .filter((n) => view.nodes.some((v) => v.id === n.id))
          .map((n) => (
            <p key={n.id}>
              <Button onClick={() => setSelected(n.id)}>{n.label}</Button>{" "}
              <Status value={n.freshness} />
            </p>
          ))}
      </details>
      {current && (
        <aside aria-label="Selected graph record">
          <h3>{current.label}</h3>
          <p>{current.description}</p>
          {current.type === "category" && (
            <Button
              onClick={() =>
                setCollapsed((previous) => {
                  const next = new Set(previous);
                  if (next.has(current.kind)) next.delete(current.kind);
                  else next.add(current.kind);
                  return next;
                })
              }
            >
              {collapsed.has(current.kind)
                ? "Expand category"
                : "Collapse category"}
            </Button>
          )}
          <Button
            onClick={() =>
              flow?.fitView({
                nodes: [{ id: current.id }],
                duration: 350,
                padding: 0.5,
                maxZoom: 1.1,
              })
            }
          >
            Focus selected node
          </Button>
          {current.assigned_user && (
            <p>
              Assigned user: {current.assigned_user} · Last updated:{" "}
              {current.last_updated} · Source version: {current.version}
            </p>
          )}
          <Status value={current.status} /> <Status value={current.freshness} />
          {current.url && (
            <p>
              <Link href={current.url}>
                Open working paper and review history
              </Link>
            </p>
          )}
          <p>
            {current.freshness === "CONTEXT"
              ? "Configured containment only; not an evidence dependency or a completed audit procedure."
              : current.freshness === "UNVERIFIED"
                ? "Legacy record: saved source-version receipts are unavailable. Reassess it through the normal draft and review workflow."
                : current.freshness !== "CURRENT"
                  ? "Reassess changed sources and save a new draft through the normal review workflow. Historical approved versions remain retained."
                  : "Sources verified against the saved dependency receipts."}
          </p>
          <ul>
            {q.data?.edges
              .filter((e) => e.source === current.id || e.target === current.id)
              .map((e) => (
                <li key={e.id}>
                  {e.source === current.id ? "Used by" : "Depends on"}{" "}
                  {
                    q.data?.nodes.find(
                      (n) =>
                        n.id ===
                        (e.source === current.id ? e.target : e.source),
                    )?.label
                  }
                  : {e.path} ({e.freshness})
                </li>
              ))}
          </ul>
          <ErrorState error={detail.error} />
          {detail.data && <Facts data={detail.data} />}
        </aside>
      )}
    </section>
  );
}

"use client";
import { useEffect, useMemo, useRef } from "react";
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import * as echarts from "echarts";
import { useAPI } from "@/hooks/use-api";
import { Empty, ErrorState } from "@/components/ui/primitives";

export function TPGraph({
  base,
  profile,
  on,
}: {
  base: string;
  profile: string;
  on: string;
}) {
  const graph = useAPI<{
    nodes: { id: string; name: string; jurisdiction: string }[];
    edges: {
      id: string;
      from_party_id: string;
      to_party_id: string;
      relationship_type: string;
      ownership?: string;
      decision: string;
    }[];
  }>(`${base}/graph/${profile}${on ? `?on=${on}` : ""}`, !!profile);
  if (graph.error) return <ErrorState error={graph.error} />;
  if (!graph.data?.nodes.length)
    return (
      <Empty title="No approved relationship graph">
        Approve parties and dated relationships to display their source facts.
      </Empty>
    );
  const nodes = graph.data.nodes.map((n, i) => ({
    id: n.id,
    data: { label: `${n.name} (${n.jurisdiction})` },
    position: { x: (i % 3) * 290, y: Math.floor(i / 3) * 160 },
  }));
  const edges = graph.data.edges.map((e) => ({
    id: e.id,
    source: e.from_party_id,
    target: e.to_party_id,
    label: `${e.relationship_type}${e.ownership ? ` ${Number(e.ownership) * 100}%` : ""} · ${e.decision}`,
    markerEnd: { type: MarkerType.ArrowClosed },
    animated: false,
  }));
  return (
    <div
      style={{ height: 430 }}
      aria-label="Approved related party relationship graph"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodesDraggable
        nodesConnectable={false}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function TPRangeChart({ result }: { result: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  const values = [
    result.minimum,
    result.lower_quartile,
    result.median,
    result.upper_quartile,
    result.maximum,
  ];
  const valid = values.every(
    (x) => x !== null && x !== undefined && Number.isFinite(Number(x)),
  );
  const serialized = JSON.stringify(values.map(Number));
  const data = useMemo<number[]>(() => JSON.parse(serialized), [serialized]);
  useEffect(() => {
    if (!ref.current || !valid) return;
    const c = echarts.init(ref.current);
    c.setOption({
      animation: false,
      tooltip: { trigger: "item" },
      grid: { left: 70, right: 30, bottom: 45 },
      xAxis: { type: "category", data: [String(result.pli || "Benchmark")] },
      yAxis: { type: "value", scale: true },
      series: [
        {
          type: "boxplot",
          data: [data],
          itemStyle: { color: "#dceeff", borderColor: "#0788ff" },
        },
      ],
    });
    const obs = new ResizeObserver(() => c.resize());
    obs.observe(ref.current);
    return () => {
      obs.disconnect();
      c.dispose();
    };
  }, [valid, result.pli, data]);
  if (!valid) return null;
  return (
    <section>
      <h2>Accepted population range</h2>
      <p>
        Minimum · lower quartile · median · upper quartile · maximum. Ratios use
        decimal units; no automatic arm’s length conclusion.
      </p>
      <div
        ref={ref}
        style={{ height: 270 }}
        role="img"
        aria-label={`Benchmark range ${data.join(", ")}`}
      />
      <TPAggregateCharts result={result} />
    </section>
  );
}

function TPAggregateCharts({ result }: { result: Record<string, unknown> }) {
  const histogram = useRef<HTMLDivElement>(null);
  const funnel = useRef<HTMLDivElement>(null);
  const annual = useRef<HTMLDivElement>(null);
  const serialized = JSON.stringify({
    histogram: result.histogram || [],
    annual: result.annual || {},
    total: Number(result.total_imported || 0),
    accepted: Number(result.accepted || 0),
    pending: Number(result.pending || 0),
  });
  const data = useMemo(
    () =>
      JSON.parse(serialized) as {
        histogram: { lower: string; upper: string; count: number }[];
        annual: Record<string, { median: string | null }>;
        total: number;
        accepted: number;
        pending: number;
      },
    [serialized],
  );
  useEffect(() => {
    const charts: echarts.ECharts[] = [];
    const mount = (
      el: HTMLDivElement | null,
      option: echarts.EChartsOption,
    ) => {
      if (!el) return;
      const chart = echarts.init(el);
      chart.setOption({
        animation: false,
        tooltip: { trigger: "item" },
        ...option,
      });
      charts.push(chart);
    };
    mount(histogram.current, {
      grid: { left: 50, right: 20, bottom: 55 },
      xAxis: {
        type: "category",
        data: data.histogram.map(
          (x) =>
            `${Number(x.lower).toPrecision(3)}–${Number(x.upper).toPrecision(3)}`,
        ),
        axisLabel: { rotate: 25 },
      },
      yAxis: { type: "value", minInterval: 1 },
      series: [
        {
          type: "bar",
          data: data.histogram.map((x) => x.count),
          itemStyle: { color: "#0788ff" },
        },
      ],
    });
    mount(funnel.current, {
      series: [
        {
          type: "funnel",
          left: "20%",
          width: "60%",
          top: 15,
          bottom: 15,
          label: { position: "inside", formatter: "{b}: {c}" },
          data: [
            { name: "Imported", value: data.total },
            { name: "Reviewed", value: data.total - data.pending },
            { name: "Accepted", value: data.accepted },
          ],
        },
      ],
    });
    const years = Object.keys(data.annual).sort();
    mount(annual.current, {
      grid: { left: 65, right: 20, bottom: 40 },
      xAxis: { type: "category", data: years },
      yAxis: { type: "value", scale: true },
      series: [
        {
          type: "line",
          data: years.map((y) =>
            data.annual[y].median === null
              ? null
              : Number(data.annual[y].median),
          ),
          showSymbol: true,
          itemStyle: { color: "#0788ff" },
        },
      ],
    });
    const observer = new ResizeObserver(() =>
      charts.forEach((c) => c.resize()),
    );
    for (const el of [histogram.current, funnel.current, annual.current])
      if (el) observer.observe(el);
    return () => {
      observer.disconnect();
      charts.forEach((c) => c.dispose());
    };
  }, [data]);
  return (
    <>
      <h3>Accepted distribution</h3>
      <div
        ref={histogram}
        style={{ height: 250 }}
        role="img"
        aria-label="Accepted benchmark histogram"
      />
      <h3>Screening progression</h3>
      <div
        ref={funnel}
        style={{ height: 250 }}
        role="img"
        aria-label="Comparable screening funnel"
      />
      <h3>Annual median</h3>
      <p>A single year is one observation, without an inferred trend.</p>
      <div
        ref={annual}
        style={{ height: 230 }}
        role="img"
        aria-label="Annual median trend"
      />
    </>
  );
}

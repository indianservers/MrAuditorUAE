"use client";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
export function LineageGraph({
  source,
  snapshot,
  line,
}: {
  source: string;
  snapshot: string;
  line: string;
}) {
  const nodes: Node[] = [
    {
      id: "source",
      position: { x: 0, y: 0 },
      data: { label: "Source record · " + source.slice(0, 8) },
    },
    {
      id: "snapshot",
      position: { x: 0, y: 100 },
      data: { label: "Immutable snapshot · " + snapshot.slice(0, 8) },
    },
    {
      id: "line",
      position: { x: 0, y: 200 },
      data: { label: "Journal line · " + line.slice(0, 8) },
    },
  ];
  const edges: Edge[] = [
    { id: "a", source: "source", target: "snapshot" },
    { id: "b", source: "snapshot", target: "line" },
  ];
  return (
    <div
      className="lineage-graph"
      aria-label="Source record to immutable snapshot to journal line"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

"use client";
import { useState } from "react";
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Paper } from "./grc-forms";

export function ControlGraph({
  rows,
}: {
  rows: { id: string; risk: Paper; control: Paper; status: unknown }[];
}) {
  const [focus, setFocus] = useState("");
  const risks = [...new Map(rows.map((x) => [x.risk.id, x.risk])).values()];
  const selected = rows
    .filter((x) => !focus || x.risk.id === focus)
    .slice(0, 30);
  const left = [...new Map(selected.map((x) => [x.risk.id, x.risk])).values()];
  const right = [
    ...new Map(selected.map((x) => [x.control.id, x.control])).values(),
  ];
  const nodes = [
    ...left.map((x, i) => ({
      id: x.id,
      data: { label: `${x.reference}: ${x.title} · ${x.status}` },
      position: { x: 0, y: i * 110 },
      style: { background: "#e4f1ef", width: 250 },
    })),
    ...right.map((x, i) => ({
      id: x.id,
      data: { label: `${x.reference}: ${x.title} · ${x.status}` },
      position: { x: 480, y: i * 110 },
      style: { background: "#e8eef7", width: 250 },
    })),
  ];
  const edges = selected.map((x) => ({
    id: x.id,
    source: x.risk.id,
    target: x.control.id,
    label: String(x.status),
    markerEnd: { type: MarkerType.ArrowClosed },
    animated: false,
  }));
  return (
    <section>
      <label>
        Focus risk
        <select value={focus} onChange={(e) => setFocus(e.target.value)}>
          <option value="">First 30 mappings</option>
          {risks.map((x) => (
            <option key={x.id} value={x.id}>
              {x.reference} · {x.title}
            </option>
          ))}
        </select>
      </label>
      <div
        style={{ height: 480 }}
        aria-label="Risk and control relationship graph"
      >
        <ReactFlow
          key={focus + rows.length}
          defaultNodes={nodes}
          defaultEdges={edges}
          fitView
          nodesConnectable={false}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <p>
        Approved and draft statuses remain visible. Drag nodes to inspect dense
        relationships; focus a risk to inspect its mapped controls.
      </p>
    </section>
  );
}

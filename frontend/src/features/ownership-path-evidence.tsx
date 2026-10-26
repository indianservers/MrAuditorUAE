"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Row = Record<string, unknown>;
const collections = {
  paths: {
    field: "ownership_paths",
    parameter: "ownership_path_offset",
    title: "Ownership calculation paths",
    columns: [
      "path_id",
      "subject_company",
      "person_id",
      "kind",
      "economic_fraction",
      "gap_reason",
      "source_graph_complete",
      "company_owner_chain",
    ],
  },
  steps: {
    field: "ownership_path_steps",
    parameter: "ownership_step_offset",
    title: "Ownership source edge steps",
    columns: [
      "path_id",
      "step",
      "edge_source_id",
      "company",
      "owner",
      "owner_kind",
      "fraction",
      "effective_from",
      "effective_to",
      "evidence_reference",
    ],
  },
};

function PathTable({
  prefix,
  selected,
  initial,
  total,
  kind,
}: {
  prefix: string;
  selected: string;
  initial: Row[];
  total: number;
  kind: keyof typeof collections;
}) {
  const [offset, setOffset] = useState(0);
  const config = collections[kind];
  const page = useAPI<{ body: Record<string, Row[]> }>(
    `${prefix}/events/${selected}?limit=1&${config.parameter}=${offset}`,
    offset > 0,
  );
  const rows = offset ? page.data?.body[config.field] || [] : initial;
  return (
    <details style={{ margin: "16px 0" }}>
      <summary>
        {config.title} · {total} records
      </summary>
      <ErrorState error={page.error} />
      <div className="table-wrap">
        <table aria-label={config.title}>
          <caption>
            {total
              ? `Rows ${offset + 1}–${offset + rows.length} of ${total}`
              : "No retained records in this collection"}
          </caption>
          <thead>
            <tr>
              {config.columns.map((field) => (
                <th key={field}>{field.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {config.columns.map((field) => (
                  <td
                    key={field}
                    style={{ maxWidth: 240, overflowWrap: "anywhere" }}
                  >
                    {row[field] == null
                      ? "Not supplied"
                      : Array.isArray(row[field])
                        ? JSON.stringify(row[field])
                        : String(row[field])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        disabled={offset === 0 || page.isFetching}
        onClick={() => setOffset(Math.max(0, offset - 100))}
      >
        Previous ownership {kind}
      </Button>
      <Button
        disabled={offset + rows.length >= total || page.isFetching}
        onClick={() => setOffset(offset + 100)}
      >
        Next ownership {kind}
      </Button>
    </details>
  );
}

export function OwnershipPathEvidence({
  prefix,
  selected,
  scope,
  paths,
  steps,
  pathTotal,
  stepTotal,
}: {
  prefix: string;
  selected: string;
  scope: Row;
  paths: Row[];
  steps: Row[];
  pathTotal: number;
  stepTotal: number;
}) {
  return (
    <section aria-label="Economic ownership path evidence">
      <p>
        Policy country: {String(scope.country ?? "Not supplied")} · As of:{" "}
        {String(scope.as_of ?? "Not supplied")} · Threshold:{" "}
        {String(scope.threshold ?? "Not supplied")} · Operator:{" "}
        {String(scope.comparison ?? "Not supplied")} · Policy reference:{" "}
        {String(scope.policy_evidence_reference ?? "Not supplied")}
      </p>
      <p>
        Fractions describe the supplied economic graph. Voting rights, nominees,
        trusts, registry verification and legal UBO conclusions need separate
        assessment. Incomplete graphs retain partial observed paths and block
        approval.
      </p>
      <PathTable
        key={selected + ":paths"}
        prefix={prefix}
        selected={selected}
        initial={paths}
        total={pathTotal}
        kind="paths"
      />
      <PathTable
        key={selected + ":steps"}
        prefix={prefix}
        selected={selected}
        initial={steps}
        total={stepTotal}
        kind="steps"
      />
    </section>
  );
}

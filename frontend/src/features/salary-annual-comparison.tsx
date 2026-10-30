"use client";

import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Source = {
  id: string;
  label: string;
  kind: string;
  table_type?: string;
  freshness: string;
  review_status: string;
};
type Evidence = {
  id: string;
  label: string;
  scan_status: string;
  sha256?: string;
};
const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;

export function SalaryAnnualComparison({
  eid,
  sources,
  evidence,
  onCreated,
}: {
  eid: string;
  sources: Source[];
  evidence: Evidence[];
  onCreated: (id: string) => void;
}) {
  const [quarters, setQuarters] = useState<Record<string, string>>({
    Q1: "",
    Q2: "",
    Q3: "",
    Q4: "",
  });
  const [nil, setNil] = useState<Record<string, string>>({});
  const [document, setDocument] = useState("");
  const [employees, setEmployees] = useState("");
  const [assessment, setAssessment] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState("");
  const action = useAction<{ id: string }>();
  const choices = sources.filter(
    (s) =>
      s.kind === "workflow-source" &&
      s.table_type === "withholding-records" &&
      s.freshness === "CURRENT" &&
      s.review_status === "REVIEWED",
  );
  const selected = evidence.find(
    (e) => e.id === document && e.scan_status === "CLEAN",
  );
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>
        Compare four salary quarters with annual current-employer tax
      </summary>
      <p>
        Choose current independently reviewed historical native 24Q sources for
        one TAN and financial year, from FY2013-14 through FY2025-26. Q4 must
        contain the controlled annual records. Match annual SD field 36 to
        quarterly party tax; previous employers and other credits remain
        separate. A missing quarter is not nil. Retain independent employee
        mapping and nil-quarter support.
      </p>
      <ErrorState error={action.error} />
      {error && <p role="alert">{error}</p>}
      <label>
        Annual salary comparison title
        <input value={label} onChange={(e) => setLabel(e.target.value)} />
      </label>
      {QUARTERS.map((q) => (
        <div key={q}>
          <label>
            Salary {q} native source
            <select
              value={quarters[q]}
              onChange={(e) =>
                setQuarters({ ...quarters, [q]: e.target.value })
              }
            >
              <option value="">Select the reviewed {q} source</option>
              {q !== "Q4" && (
                <option value="NIL">Explicitly assessed nil quarter</option>
              )}
              {choices.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          {quarters[q] === "NIL" && (
            <label>
              Salary {q} nil assessment
              <textarea
                value={nil[q] || ""}
                onChange={(e) => setNil({ ...nil, [q]: e.target.value })}
              />
            </label>
          )}
        </div>
      ))}
      <label>
        Independent annual employee and nil-quarter crosswalk
        <select value={document} onChange={(e) => setDocument(e.target.value)}>
          <option value="">Select separate clean retained evidence</option>
          {evidence
            .filter((e) => e.scan_status === "CLEAN" && e.sha256)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
        </select>
      </label>
      <p>
        Map every SD/batch/record key once. Each party link uses its original
        quarter and batch/challan/party key. Unassigned quarterly parties remain
        exceptions, including specified-senior records. Identity requires an
        explicit assessment even if amounts agree.
      </p>
      <label>
        Annual salary employee mapping (JSON)
        <textarea
          value={employees}
          onChange={(e) => setEmployees(e.target.value)}
          placeholder={
            '[{"annual_key":"SD/1/1","parties":[{"quarter":"Q1","party_key":"1/1/1"}],"identity_status":"unresolved","assessment":"Explain the retained identity evidence"}]'
          }
        />
      </label>
      <label>
        Annual salary full-population assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          !label.trim() ||
          !selected?.sha256 ||
          !employees.trim() ||
          assessment.trim().length < 10 ||
          QUARTERS.some(
            (q) =>
              !quarters[q] ||
              (quarters[q] === "NIL" && (nil[q] || "").trim().length < 10),
          )
        }
        onClick={async () => {
          setError("");
          let mapped: unknown;
          try {
            mapped = JSON.parse(employees);
            if (!Array.isArray(mapped)) throw new Error();
          } catch {
            setError("Enter an array of complete annual employee mappings.");
            return;
          }
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/salary-annual-comparison`,
              body: {
                label,
                quarter_source_ids: Object.fromEntries(
                  QUARTERS.map((q) => [
                    q,
                    quarters[q] === "NIL" ? null : quarters[q],
                  ]),
                ),
                nil_quarter_assessments: Object.fromEntries(
                  QUARTERS.filter((q) => quarters[q] === "NIL").map((q) => [
                    q,
                    nil[q],
                  ]),
                ),
                crosswalk_document_version_id: document,
                crosswalk_sha256: selected!.sha256,
                employees: mapped,
                assessment,
              },
            });
            onCreated(result.id);
          } catch {
            /* Server error is retained above. */
          }
        }}
      >
        Prepare annual salary comparison
      </Button>
    </details>
  );
}

export function SalaryAnnualLinks({
  prefix,
  selected,
}: {
  prefix: string;
  selected: string;
}) {
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState("salary_quarterly_links");
  const result = useAPI<{
    body: Record<string, unknown>;
    collection_totals?: Record<string, number>;
  }>(
    `${prefix}/events/${selected}?salary_link_offset=${offset}&salary_link_limit=100`,
  );
  const rows = (result.data?.body[view] || []) as Record<string, unknown>[];
  const total = result.data?.collection_totals?.[view] || 0;
  const fields =
    view === "salary_quarterly_links"
      ? [
          "annual_key",
          "quarter",
          "source_event_id",
          "party_key",
          "source_line",
          "pan",
          "total_tax",
          "identity_status",
          "identity_assessment",
        ]
      : [
          "quarter",
          "source_event_id",
          "party_key",
          "source_line",
          "pan",
          "native_section_code",
          "total_tax",
        ];
  return (
    <section aria-label="Annual salary quarter lineage">
      <h3>Annual salary quarterly party coverage</h3>
      <p>
        TAN {String(result.data?.body.tan ?? "Loading")} · financial year{" "}
        {String(result.data?.body.financial_year ?? "Loading")}. This compares
        recorded current-employer tax, not annual mixed credits or recomputed
        salary tax.
      </p>
      <ErrorState error={result.error} />
      <label>
        Salary party coverage view
        <select
          value={view}
          onChange={(e) => {
            setView(e.target.value);
            setOffset(0);
          }}
        >
          <option value="salary_quarterly_links">
            Assigned salary parties
          </option>
          <option value="unassigned_quarterly_parties">
            Unassigned quarterly parties
          </option>
        </select>
      </label>
      <p>
        Parties {total ? offset + 1 : 0}–{offset + rows.length} of {total}.
        Unassigned parties prevent complete coverage. XLSX retains every
        original link and exception.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <caption>Annual salary party links</caption>
          <thead>
            <tr>
              {fields.map((f) => (
                <th key={f}>{f.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {fields.map((f) => (
                  <td key={f}>{String(r[f] ?? "Not recorded")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button
        disabled={!offset || result.isFetching}
        onClick={() => setOffset(Math.max(0, offset - 100))}
      >
        Previous salary parties
      </Button>
      <Button
        disabled={
          offset + rows.length >= total || !rows.length || result.isFetching
        }
        onClick={() => setOffset(offset + 100)}
      >
        Next salary parties
      </Button>
    </section>
  );
}

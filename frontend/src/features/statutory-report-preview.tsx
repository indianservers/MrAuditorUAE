"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/primitives";

const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const rows = (value: unknown) =>
  Array.isArray(value) ? value.map(object) : [];
const text = (value: unknown, fallback = "Not supplied") =>
  value === null || value === undefined || value === ""
    ? fallback
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);

/** Read-only retained report body. Approval and freshness remain server decisions. */
export function StatutoryReportPreview({
  body,
  freshness,
  eid,
}: {
  body: Record<string, unknown>;
  freshness: string;
  eid: string;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [blockPage, setBlockPage] = useState(0);
  const coverage = object(body.requirements_coverage);
  const pack = object(coverage.requirements_pack);
  const items = rows(coverage.items);
  const fields = new Map(
    rows(pack.fields).map((field) => [text(field.key), field]),
  );
  const filtered = items.filter((item) =>
    `${text(item.key, "")} ${text(item.title, "")} ${text(item.disposition, "")} ${text(item.status, "")}`
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 20));
  const current = Math.min(page, pages - 1);
  const blocks = rows(body.blocks);
  const blockPages = Math.max(1, Math.ceil(blocks.length / 5));
  const currentBlock = Math.min(blockPage, blockPages - 1);
  const scope = object(body.tax_audit_scope);
  return (
    <section aria-label="Saved statutory report preview">
      <h2>{text(body.title, "Generated report draft")}</h2>
      <p>{text(body.document_status, "Draft status not supplied")}</p>
      {freshness !== "CURRENT" && (
        <p role="alert">
          This saved report is {freshness}. Its retained content is historical;
          revalidate changed sources before preparing a new report.
        </p>
      )}
      <p>
        This preview displays the saved report. Declared coverage does not
        establish statutory completeness, legal sufficiency, a signed opinion or
        a filing.
      </p>
      <dl>
        <div>
          <dt>Report category</dt>
          <dd>{text(body.category)}</dd>
        </div>
        <div>
          <dt>Template version</dt>
          <dd>{text(body.template_version)}</dd>
        </div>
        <div>
          <dt>Template reference</dt>
          <dd>{text(body.template_id)}</dd>
        </div>
        <div>
          <dt>Template SHA-256</dt>
          <dd style={{ overflowWrap: "anywhere" }}>
            {text(body.template_sha256)}
          </dd>
        </div>
        <div>
          <dt>Requirement preset</dt>
          <dd>{text(pack.id, "Custom declared scope")}</dd>
        </div>
        <div>
          <dt>Scope assessment</dt>
          <dd>{text(body.requirements_basis)}</dd>
        </div>
      </dl>
      {!!Object.keys(scope).length && (
        <section aria-label="Saved tax audit scope">
          <h3>Saved tax audit scope</h3>
          <p>
            Form {text(scope.form)} · Report part{" "}
            {text(scope.audit_report_part, "Not supplied for this form")} ·{" "}
            {text(scope.tax_period_start)} to {text(scope.tax_period_end)}
          </p>
          <p>
            Other-law audit assessment: {text(scope.audited_under_other_law)}.
            Form content is not qualified by this preview.
          </p>
        </section>
      )}
      <section aria-label="Saved report requirement coverage">
        <h3>Saved requirement coverage</h3>
        <label>
          Search saved report requirements
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <p>
          {filtered.length} of {items.length} saved requirements match. Page{" "}
          {current + 1} of {pages}. Saved source validation at generation:{" "}
          {text(coverage.source_validation)}.
        </p>
        <Button
          type="button"
          disabled={current === 0}
          onClick={() => setPage(current - 1)}
        >
          Previous saved requirements
        </Button>
        <Button
          type="button"
          disabled={current + 1 >= pages}
          onClick={() => setPage(current + 1)}
        >
          Next saved requirements
        </Button>
        <table>
          <caption>Saved requirement references and block coverage</caption>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Requirement</th>
              <th>Disposition</th>
              <th>Coverage</th>
              <th>Report blocks</th>
              <th>Published source page</th>
            </tr>
          </thead>
          <tbody>
            {filtered
              .slice(current * 20, (current + 1) * 20)
              .map((item, index) => (
                <tr key={`${text(item.key)}:${index}`}>
                  <td>{text(item.key)}</td>
                  <td>{text(item.title)}</td>
                  <td>{text(item.disposition)}</td>
                  <td>{text(item.status)}</td>
                  <td>
                    {Array.isArray(item.block_keys)
                      ? item.block_keys.map((key) => text(key)).join(", ") ||
                        "No block links"
                      : "No block links"}
                  </td>
                  <td>{text(fields.get(text(item.key))?.page)}</td>
                </tr>
              ))}
          </tbody>
        </table>
        {!filtered.length && <p>No saved requirements match this search.</p>}
      </section>
      <section aria-label="Saved report blocks">
        <h3>Saved report blocks</h3>
        <p>
          {blocks.length} retained blocks. Page {currentBlock + 1} of{" "}
          {blockPages}. Saved source versions are historical references; their
          presence does not authenticate external documents.
        </p>
        <Button
          type="button"
          disabled={currentBlock === 0}
          onClick={() => setBlockPage(currentBlock - 1)}
        >
          Previous saved blocks
        </Button>
        <Button
          type="button"
          disabled={currentBlock + 1 >= blockPages}
          onClick={() => setBlockPage(currentBlock + 1)}
        >
          Next saved blocks
        </Button>
        {blocks
          .slice(currentBlock * 5, (currentBlock + 1) * 5)
          .map((block, index) => {
            const receipt = object(block.source_receipt);
            const data = object(block.data);
            return (
              <article key={`${text(block.key)}:${index}`}>
                <h4>
                  {text(block.number)}. {text(block.title)}
                </h4>
                <p>
                  Block reference: {text(block.key)} · Content:{" "}
                  {text(block.kind)} · Narrative origin:{" "}
                  {text(block.narrative_origin)}
                </p>
                {typeof block.text === "string" && block.text && (
                  <p style={{ whiteSpace: "pre-wrap" }}>{block.text}</p>
                )}
                <p>
                  Source: {text(block.source_kind)} · {text(block.source_id)} ·
                  Saved version {text(receipt.version)} · SHA-256{" "}
                  {text(receipt.sha256, "Not included in this source receipt")}
                </p>
                {typeof block.source_id === "string" &&
                  ["record", "intelligence"].includes(
                    text(block.source_kind),
                  ) && (
                    <Link
                      href={
                        block.source_kind === "intelligence"
                          ? `/intelligence/${eid}/lead?event=${encodeURIComponent(block.source_id)}`
                          : `/engagements/${eid}/lifecycle`
                      }
                    >
                      Review saved block source
                    </Link>
                  )}
                {rows(data.sections).map((section, sectionIndex) => (
                  <div key={sectionIndex}>
                    <h5>{text(section.heading)}</h5>
                    <p style={{ whiteSpace: "pre-wrap" }}>
                      {text(section.text)}
                    </p>
                  </div>
                ))}
                {typeof data.conclusion === "string" && (
                  <p>Saved source conclusion: {data.conclusion}</p>
                )}
                {Array.isArray(data.rows) && (
                  <RetainedRows
                    name={`Saved source rows for ${text(block.key)}`}
                    values={data.rows}
                  />
                )}
                {rows(data.financial_tables).map((table, tableIndex) => {
                  const values = object(table.values);
                  return (
                    <section
                      key={tableIndex}
                      aria-label={`Saved financial table ${text(table.title, String(tableIndex + 1))}`}
                    >
                      <h5>{text(table.title, "Retained financial table")}</h5>
                      {Object.keys(values).length > 0 && (
                        <dl>
                          {Object.entries(values).map(([key, value]) => (
                            <div key={key}>
                              <dt>{key}</dt>
                              <dd>{text(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                      {Array.isArray(table.values) && (
                        <RetainedRows
                          name={`Saved financial rows for ${text(block.key)} table ${tableIndex + 1}`}
                          values={table.values}
                        />
                      )}
                    </section>
                  );
                })}
                {Object.keys(data).length > 0 && (
                  <RetainedSourceContent name={text(block.key)} data={data} />
                )}
              </article>
            );
          })}
      </section>
    </section>
  );
}

function RetainedSourceContent({
  name,
  data,
}: {
  name: string;
  data: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Complete retained source content for {name}</summary>
      {open && (
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </details>
  );
}

function RetainedRows({ name, values }: { name: string; values: unknown[] }) {
  const [page, setPage] = useState(0);
  const records = values.map((value) =>
    value && typeof value === "object" && !Array.isArray(value)
      ? object(value)
      : { "Retained value": value },
  );
  const columns = Array.from(
    new Set(records.flatMap((row) => Object.keys(row))),
  );
  const pages = Math.max(1, Math.ceil(records.length / 20));
  const current = Math.min(page, pages - 1);
  return (
    <section aria-label={name}>
      <p>
        {records.length} saved source rows. Page {current + 1} of {pages}.
        Values are shown as retained; no totals or rates are inferred.
      </p>
      <Button
        type="button"
        disabled={current === 0}
        onClick={() => setPage(current - 1)}
      >
        Previous source rows
      </Button>
      <Button
        type="button"
        disabled={current + 1 >= pages}
        onClick={() => setPage(current + 1)}
      >
        Next source rows
      </Button>
      <div style={{ overflowX: "auto" }}>
        <table>
          <caption>{name}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records
              .slice(current * 20, (current + 1) * 20)
              .map((row, index) => (
                <tr key={current * 20 + index}>
                  {columns.map((column) => (
                    <td key={column}>{text(row[column])}</td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

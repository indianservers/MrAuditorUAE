"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { Page, RecordRow } from "@/types/models";

export function ReportingRecordSelect({
  path,
  label,
  value,
  onChange,
  runs = false,
}: {
  path: string;
  label: string;
  value: string;
  onChange: (id: string) => void;
  runs?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const limit = 50;
  const query = useAPI<Page<RecordRow>>(
    `${path}?offset=${offset}&limit=${limit}`,
  );
  const page = query.data;
  const items = page?.items || [];
  const display = (row: RecordRow) =>
    runs
      ? `${String(row.kind)} · ${row.id.slice(0, 8)}`
      : `${String(row.reference)} · ${String(row.status)}`;
  const outside = value && !items.some((row) => row.id === value);
  return (
    <div>
      <label>
        {label}{" "}
        <select
          aria-label={label}
          value={value}
          onChange={(event) => {
            const id = event.target.value;
            setSelected(items.find((row) => row.id === id) || null);
            onChange(id);
          }}
        >
          <option value="">
            {runs ? "Choose run" : "Choose approved record"}
          </option>
          {outside && (
            <option value={value}>
              {selected?.id === value ? display(selected) : value} · selected
            </option>
          )}
          {items.map((row) => (
            <option key={row.id} value={row.id}>
              {display(row)}
            </option>
          ))}
        </select>
      </label>
      <ErrorState error={query.error} />
      <div className="toolbar" aria-label={`${label} pages`}>
        <Button
          disabled={offset === 0 || query.isLoading}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          Previous {label.toLowerCase()}
        </Button>
        <span aria-live="polite">
          {query.error
            ? "Records unavailable"
            : page
              ? `${items.length ? offset + 1 : 0}–${items.length ? offset + items.length : 0} of ${page.total}`
              : "Loading records"}
        </span>
        <Button
          disabled={
            !page ||
            query.isLoading ||
            offset + items.length >= page.total ||
            items.length === 0
          }
          onClick={() => setOffset(offset + limit)}
        >
          Next {label.toLowerCase()}
        </Button>
      </div>
    </div>
  );
}

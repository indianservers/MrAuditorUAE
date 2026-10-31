"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export type EvidenceChoice = { id: string; label: string; sha256: string };

/** Current clean versions only; preserve an explicit choice outside the viewed page. */
export function RetainedEvidenceSelect({
  eid,
  label,
  value,
  onChange,
  sha256,
}: {
  eid: string;
  label: string;
  value: EvidenceChoice | null;
  onChange: (value: EvidenceChoice | null) => void;
  sha256?: string;
}) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const query = new URLSearchParams({
    offset: String(offset),
    limit: "25",
    search,
  });
  if (sha256) query.set("sha256", sha256);
  const result = useAPI<{ items: EvidenceChoice[]; total: number }>(
    `intelligence/engagements/${eid}/evidence-choices?${query}`,
  );
  const choices = result.data?.items || [];
  const options =
    value && !choices.some((item) => item.id === value.id)
      ? [value, ...choices]
      : choices;
  return (
    <div>
      <ErrorState error={result.error} />
      <label>
        {label}
        <select
          value={value?.id || ""}
          onChange={(e) =>
            onChange(options.find((item) => item.id === e.target.value) || null)
          }
        >
          <option value="">Select a current clean original</option>
          {options.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} · {item.id}
            </option>
          ))}
        </select>
      </label>
      <label>
        Search {label.toLowerCase()}
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      <p>
        {result.isLoading
          ? "Loading original evidence…"
          : `Choices ${choices.length ? offset + 1 : 0}–${offset + choices.length} of ${result.data?.total || 0}.`}
        {value && ` Selected: ${value.label}.`}
      </p>
      <Button
        disabled={offset === 0 || result.isFetching}
        onClick={() => setOffset(Math.max(0, offset - 25))}
      >
        Previous {label.toLowerCase()}
      </Button>
      <Button
        disabled={
          result.isFetching || !result.data || offset + 25 >= result.data.total
        }
        onClick={() => setOffset(offset + 25)}
      >
        Next {label.toLowerCase()}
      </Button>
    </div>
  );
}

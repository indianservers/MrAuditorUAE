"use client";

import { useState } from "react";
import { useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Link = { kind: string; id: string };
type Mapping = {
  key: string;
  disposition: "REQUIRED" | "NOT_APPLICABLE";
  section_index: number;
  supporting_sources: Link[];
  assessment: string;
};
type Scope = {
  preset_id: string;
  period_start: string;
  period_end: string;
  items: Mapping[];
};
const list = (value: unknown): unknown[] => {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

export function WorkpaperReportScopeEditor({
  base,
  value,
  sections,
  sources,
  onChange,
}: {
  base: string;
  value: unknown;
  sections: unknown;
  sources: unknown;
  onChange: (value: Scope | null) => void;
}) {
  const saved = value && typeof value === "object" ? (value as Scope) : null;
  const eid = base.match(/engagements\/([^/]+)\/audit/)?.[1] || "";
  const presets = useAPI<{
    items: {
      id: string;
      title: string;
      kind: string;
      requirements: { key: string; title: string }[];
      not_applicable_keys: string[];
    }[];
  }>(`regulatory/engagements/${eid}/report-presets`, !!eid);
  const labels = useAPI<{ items: (Link & { label: string })[] }>(
    `${base}/linkable-sources`,
  );
  const available = (presets.data?.items || []).filter(
    (p) => p.kind === "form26-index" || p.kind === "caro-index",
  );
  const preset = available.find((p) => p.id === saved?.preset_id);
  const protectedLinks = list(sources) as Link[];
  const sectionRows = list(sections) as { heading: string; text: string }[];
  const [keys, setKeys] = useState<string[]>([]);
  const [itemSearch, setItemSearch] = useState("");
  const [section, setSection] = useState("");
  const [refs, setRefs] = useState<string[]>([]);
  const [disposition, setDisposition] =
    useState<Mapping["disposition"]>("REQUIRED");
  const [assessment, setAssessment] = useState("");
  const keyFor = (s: Link) => `${s.kind}:${s.id}`;
  const selectedRefs = protectedLinks.filter((s) => refs.includes(keyFor(s)));
  const invalid =
    !saved ||
    !preset ||
    !keys.length ||
    saved.items.length + keys.length > 100 ||
    section === "" ||
    (sectionRows[Number(section)]?.text || "").trim().length < 10 ||
    !selectedRefs.length ||
    assessment.trim().length < 10 ||
    !saved.period_start ||
    !saved.period_end ||
    saved.period_start > saved.period_end ||
    keys.some(
      (k) =>
        saved.items.some((i) => i.key === k) ||
        !preset.requirements.some((r) => r.key === k) ||
        (disposition === "NOT_APPLICABLE" &&
          !preset.not_applicable_keys.includes(k)),
    );
  if (!saved && !available.length)
    return presets.error ? <ErrorState error={presets.error} /> : null;
  return (
    <fieldset>
      <legend>Report item coverage declared in this workpaper</legend>
      <p>
        Declare only items supported by the work performed. Each mapping names a
        substantive section and existing protected source links. Manager/partner
        review covers these declarations; report authors cannot expand them
        later.
      </p>
      <ErrorState error={presets.error || labels.error} />
      <label>
        Declare report inventory coverage
        <select
          value={saved ? "yes" : "no"}
          onChange={(e) => {
            onChange(
              e.target.value === "yes"
                ? {
                    preset_id: "",
                    period_start: "",
                    period_end: "",
                    items: [],
                  }
                : null,
            );
            setKeys([]);
          }}
        >
          <option value="no">No report item declaration</option>
          <option value="yes">Declare for independent workpaper review</option>
        </select>
      </label>
      {saved && (
        <>
          <label>
            Workpaper report preset
            <select
              required
              value={saved.preset_id}
              onChange={(e) => {
                onChange({ ...saved, preset_id: e.target.value, items: [] });
                setKeys([]);
              }}
            >
              <option value="">Choose the assessed report part</option>
              {available.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <p>
            Changing preset clears item mappings. Match the exact covered period
            of the intended report; statutory applicability and legal
            sufficiency are separately assessed.
          </p>
          <label>
            Workpaper report period start
            <input
              type="date"
              required
              value={saved.period_start}
              onChange={(e) =>
                onChange({ ...saved, period_start: e.target.value })
              }
            />
          </label>
          <label>
            Workpaper report period end
            <input
              type="date"
              required
              value={saved.period_end}
              onChange={(e) =>
                onChange({ ...saved, period_end: e.target.value })
              }
            />
          </label>
          <label>
            Search workpaper report items
            <input
              value={itemSearch}
              onChange={(e) => setItemSearch(e.target.value)}
            />
          </label>
          <p>
            {keys.length} selected; {saved.items.length} of 100 mappings in this
            workpaper. Use additional independently reviewed workpapers for the
            remaining fields.
          </p>
          <label>
            Report items supported by this section
            <select
              multiple
              size={5}
              style={{ height: 140 }}
              value={keys}
              onChange={(e) =>
                setKeys(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {preset?.requirements
                .filter((r) => !saved.items.some((i) => i.key === r.key))
                .filter(
                  (r) =>
                    keys.includes(r.key) ||
                    `${r.key} ${r.title}`
                      .toLocaleLowerCase()
                      .includes(itemSearch.trim().toLocaleLowerCase()),
                )
                .map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.title}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Supporting workpaper section
            <select
              value={section}
              onChange={(e) => setSection(e.target.value)}
            >
              <option value="">Choose a completed section</option>
              {sectionRows.map((s, i) => (
                <option key={i} value={i}>
                  {i + 1} · {s.heading}
                </option>
              ))}
            </select>
          </label>
          <label>
            Existing protected supporting sources
            <select
              multiple
              size={5}
              style={{ height: 120 }}
              value={refs}
              onChange={(e) =>
                setRefs(Array.from(e.target.selectedOptions, (o) => o.value))
              }
            >
              {protectedLinks.map((s, i) => (
                <option key={keyFor(s)} value={keyFor(s)}>
                  {labels.data?.items.find(
                    (l) => l.kind === s.kind && l.id === s.id,
                  )?.label || `Linked source ${i + 1} (${s.kind})`}
                </option>
              ))}
            </select>
          </label>
          {selectedRefs.map((source) => (
            <p key={keyFor(source)} style={{ overflowWrap: "anywhere" }}>
              {labels.data?.items.find(
                (l) => l.kind === source.kind && l.id === source.id,
              )?.label || `Linked source (${source.kind})`}
            </p>
          ))}
          <label>
            Workpaper item applicability
            <select
              value={disposition}
              onChange={(e) =>
                setDisposition(e.target.value as Mapping["disposition"])
              }
            >
              <option value="REQUIRED">
                Required, supported by this workpaper
              </option>
              <option value="NOT_APPLICABLE">
                Not applicable, supported by reviewed evidence
              </option>
            </select>
          </label>
          <label>
            Item support and applicability assessment
            <textarea
              value={assessment}
              onChange={(e) => setAssessment(e.target.value)}
            />
          </label>
          <Button
            type="button"
            disabled={invalid}
            onClick={() => {
              if (!saved) return;
              onChange({
                ...saved,
                items: [
                  ...saved.items,
                  ...keys.map((key) => ({
                    key,
                    disposition,
                    section_index: Number(section),
                    supporting_sources: selectedRefs,
                    assessment,
                  })),
                ],
              });
              setKeys([]);
              setAssessment("");
            }}
          >
            Add declared item mappings
          </Button>
          <p>
            Selected report/identity/audit-basis items cannot be marked
            not-applicable. Removing a section or source used here requires
            updating the mappings before saving.
          </p>
          {!saved.items.length && (
            <p>
              Add at least one complete item mapping before saving this declared
              workpaper scope, or clear the declaration.
            </p>
          )}
          {saved.items.map((item) => (
            <details key={item.key}>
              <summary>
                {preset?.requirements.find((r) => r.key === item.key)?.title ||
                  item.key}{" "}
                · {item.disposition}
              </summary>
              <p>
                Section {item.section_index + 1}:{" "}
                {sectionRows[item.section_index]?.heading ||
                  "Section missing — amend mapping"}
              </p>
              <p>{item.assessment}</p>
              <p>
                {item.supporting_sources.length} protected supporting source
                links
              </p>
              <Button
                type="button"
                onClick={() =>
                  onChange({
                    ...saved,
                    items: saved.items.filter((i) => i.key !== item.key),
                  })
                }
              >
                Remove item mapping
              </Button>
            </details>
          ))}
        </>
      )}
    </fieldset>
  );
}

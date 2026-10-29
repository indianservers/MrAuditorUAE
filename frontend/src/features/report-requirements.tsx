"use client";
import { useState } from "react";
import { Button } from "@/components/ui/primitives";
export type ReportRequirement = {
  key: string;
  title: string;
  disposition: "REQUIRED" | "NOT_APPLICABLE" | "UNASSESSED";
  source_required: boolean;
  basis: string;
};
export function ReportRequirementsEditor({
  items,
  assessed,
  basis,
  onItems,
  onAssessed,
  onBasis,
  locked = false,
  allowNotApplicable = false,
  notApplicableKeys,
}: {
  items: ReportRequirement[];
  assessed: boolean;
  basis: string;
  onItems: (items: ReportRequirement[]) => void;
  onAssessed: (value: boolean) => void;
  onBasis: (value: string) => void;
  locked?: boolean;
  allowNotApplicable?: boolean;
  notApplicableKeys?: string[];
}) {
  const [query, setQuery] = useState("");
  const [disposition, setDisposition] = useState("ALL");
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const needle = query.trim().toLocaleLowerCase();
  const filtered = items
    .map((item, index) => ({ item, index }))
    .filter(
      ({ item }) =>
        (disposition === "ALL" || item.disposition === disposition) &&
        (!needle ||
          `${item.key} ${item.title} ${item.basis}`
            .toLocaleLowerCase()
            .includes(needle)),
    );
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize,
  );
  function change(index: number, field: Partial<ReportRequirement>) {
    onItems(
      items.map((item, i) => (i === index ? { ...item, ...field } : item)),
    );
  }
  return (
    <fieldset>
      <legend>Declared report requirements</legend>
      <p>
        Declare the items required for this engagement, then link each item to
        report blocks. Source requirements need current reviewed evidence or
        calculations. Not-applicable items also need a reviewed source. This
        records your declared scope; it does not certify a complete statutory
        form pack.
      </p>
      <label>
        Requirement scope completeness assessment
        <select
          value={assessed ? "assessed" : "unassessed"}
          onChange={(e) => onAssessed(e.target.value === "assessed")}
        >
          <option value="unassessed">Not yet assessed</option>
          <option value="assessed">
            Declared scope assessed for independent review
          </option>
        </select>
      </label>
      <label>
        Requirement scope basis
        <textarea value={basis} onChange={(e) => onBasis(e.target.value)} />
      </label>
      <label>
        Search report requirements
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
      </label>
      <label>
        Filter requirement assessment
        <select
          value={disposition}
          onChange={(e) => {
            setDisposition(e.target.value);
            setPage(0);
          }}
        >
          <option value="ALL">All assessments</option>
          <option value="UNASSESSED">Unassessed</option>
          <option value="REQUIRED">Required</option>
          <option value="NOT_APPLICABLE">Not applicable</option>
        </select>
      </label>
      <p role="status">
        {filtered.length} of {items.length} requirements match. Page{" "}
        {currentPage + 1} of {pages}. All {items.length} requirements remain in
        the report scope.
      </p>
      <nav aria-label="Report requirement pages">
        <Button
          type="button"
          disabled={currentPage === 0}
          onClick={() => setPage(currentPage - 1)}
        >
          Previous requirements
        </Button>
        <Button
          type="button"
          disabled={currentPage + 1 >= pages}
          onClick={() => setPage(currentPage + 1)}
        >
          Next requirements
        </Button>
      </nav>
      {visible.length === 0 && <p>No requirements match these filters.</p>}
      {visible.map(({ item, index: i }) => (
        <fieldset key={i}>
          <legend>Requirement {i + 1}</legend>
          <label>
            Requirement reference {i + 1}
            <input
              value={item.key}
              disabled={locked}
              onChange={(e) => change(i, { key: e.target.value })}
            />
          </label>
          <label>
            Requirement title {i + 1}
            <input
              value={item.title}
              disabled={locked}
              onChange={(e) => change(i, { title: e.target.value })}
            />
          </label>
          <label>
            Requirement disposition {i + 1}
            <select
              value={item.disposition}
              onChange={(e) =>
                change(i, {
                  disposition: e.target
                    .value as ReportRequirement["disposition"],
                })
              }
            >
              <option value="UNASSESSED">Unassessed</option>
              <option value="REQUIRED">Required</option>
              <option
                value="NOT_APPLICABLE"
                disabled={
                  locked &&
                  (!allowNotApplicable ||
                    (!!notApplicableKeys &&
                      !notApplicableKeys.includes(item.key)))
                }
              >
                Not applicable with reviewed basis
              </option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={item.source_required}
              disabled={locked}
              onChange={(e) => change(i, { source_required: e.target.checked })}
            />
            Evidence/calculation source required for item {i + 1}
          </label>
          <label>
            Applicability and source basis {i + 1}
            <textarea
              value={item.basis}
              onChange={(e) => change(i, { basis: e.target.value })}
            />
          </label>
          <Button
            disabled={locked}
            onClick={() => onItems(items.filter((_, index) => index !== i))}
          >
            Remove requirement {i + 1}
          </Button>
        </fieldset>
      ))}
      <Button
        disabled={locked || items.length >= 100}
        onClick={() => {
          setQuery("");
          setDisposition("ALL");
          setPage(Math.floor(items.length / pageSize));
          onItems([
            ...items,
            {
              key: Array.from(
                { length: 101 },
                (_, index) => `item-${index + 1}`,
              ).find((key) => !items.some((item) => item.key === key))!,
              title: "",
              disposition: "UNASSESSED",
              source_required: true,
              basis: "",
            },
          ]);
        }}
      >
        Add declared requirement
      </Button>
    </fieldset>
  );
}

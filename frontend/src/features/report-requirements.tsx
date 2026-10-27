"use client";
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
      {items.map((item, i) => (
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
        onClick={() =>
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
          ])
        }
      >
        Add declared requirement
      </Button>
    </fieldset>
  );
}

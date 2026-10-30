"use client";

export const UN_COUNT_FIELDS = [
  "individuals",
  "entities",
  "original_script_names",
  "individual_alias_names",
  "entity_alias_names",
  "empty_alias_records",
] as const;

export type UNSnapshotDraft = Record<
  (typeof UN_COUNT_FIELDS)[number] | "generated_at" | "assessment",
  string
>;

export const EMPTY_UN_SNAPSHOT: UNSnapshotDraft = {
  generated_at: "",
  assessment: "",
  individuals: "",
  entities: "",
  original_script_names: "",
  individual_alias_names: "",
  entity_alias_names: "",
  empty_alias_records: "",
};

export function buildUNSnapshot(draft: UNSnapshotDraft, expectedRows: string) {
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      draft.generated_at,
    ) ||
    !Number.isFinite(Date.parse(draft.generated_at))
  )
    throw new Error(
      "Enter the exact UN XML generated timestamp including timezone.",
    );
  const counts = Object.fromEntries(
    UN_COUNT_FIELDS.map((field) => {
      if (!/^\d+$/.test(draft[field]) || Number(draft[field]) > 5000)
        throw new Error(
          `Enter an independent whole-number control for ${field.replaceAll("_", " ")}.`,
        );
      return [field, Number(draft[field])];
    }),
  ) as Record<(typeof UN_COUNT_FIELDS)[number], number>;
  const expanded =
    counts.individuals +
    counts.entities +
    counts.original_script_names +
    counts.individual_alias_names +
    counts.entity_alias_names;
  if (
    !/^\d+$/.test(expectedRows) ||
    expanded !== Number(expectedRows) ||
    expanded > 5000 ||
    counts.individuals + counts.entities === 0
  )
    throw new Error(
      "Expanded UN name rows must equal the subject, original-script and named-alias controls (at most 5,000). Empty aliases are counted separately.",
    );
  if (draft.assessment.trim().length < 10 || draft.assessment.length > 2000)
    throw new Error(
      "Record the independent UN snapshot population assessment.",
    );
  return {
    ...counts,
    generated_at: draft.generated_at,
    assessment: draft.assessment,
  };
}

export function UNSanctionsSource({
  value,
  onChange,
}: {
  value: UNSnapshotDraft;
  onChange: (value: UNSnapshotDraft) => void;
}) {
  return (
    <fieldset>
      <legend>Independent UN snapshot controls</legend>
      <p>
        Retain the exact uploaded XML. Count every primary name, identifying
        original-script name and named alias, including duplicate spellings and
        low-quality aliases. Blank or literal “na” aliases have a separate
        control. These are uploaded source observations requiring human
        adjudication, not identity clearance, PEP screening or proof of a
        current authentic list.
      </p>
      <label>
        UN XML generated timestamp with timezone
        <input
          value={value.generated_at}
          placeholder="2026-06-29T23:00:00Z"
          onChange={(e) => onChange({ ...value, generated_at: e.target.value })}
        />
      </label>
      {UN_COUNT_FIELDS.map((field) => (
        <label key={field}>
          UN {field.replaceAll("_", " ")}
          <input
            inputMode="numeric"
            value={value[field]}
            onChange={(e) => onChange({ ...value, [field]: e.target.value })}
          />
        </label>
      ))}
      <label>
        UN snapshot population assessment
        <textarea
          maxLength={2000}
          value={value.assessment}
          onChange={(e) => onChange({ ...value, assessment: e.target.value })}
        />
      </label>
      <p>
        Expected source rows must equal individuals + entities + original-script
        names + individual named aliases + entity named aliases. No monetary
        totals apply. Generated date measures snapshot age; it is not the
        designation date.
      </p>
    </fieldset>
  );
}

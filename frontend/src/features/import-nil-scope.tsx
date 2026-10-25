"use client";

export type ImportNilDraft = {
  registration: string;
  period_start: string;
  period_end: string;
  kinds: string[];
  context_evidence_version_id: string;
  context_sha256: string;
  assessment: string;
};

export function ImportNilScopeForm({
  value,
  onChange,
  evidence,
}: {
  value: ImportNilDraft | null;
  onChange: (value: ImportNilDraft | null) => void;
  evidence: {
    id: string;
    label: string;
    scan_status: string;
    sha256?: string;
  }[];
}) {
  const update = (fields: Partial<ImportNilDraft>) =>
    value && onChange({ ...value, ...fields });
  return (
    <fieldset
      style={{
        display: "grid",
        gap: 12,
        padding: 16,
        border: "1px solid var(--border, #d8e0eb)",
        borderRadius: 8,
      }}
    >
      <legend>Explicit nil import populations</legend>
      <label
        style={{
          display: "flex",
          flexDirection: "row",
          justifyContent: "flex-start",
          alignItems: "center",
          gap: 8,
        }}
      >
        <input
          style={{
            width: 16,
            height: 16,
            minHeight: 16,
            margin: 0,
            flex: "0 0 16px",
          }}
          type="checkbox"
          checked={value !== null}
          onChange={(event) =>
            onChange(
              event.target.checked
                ? {
                    registration: "",
                    period_start: "",
                    period_end: "",
                    kinds: [],
                    context_evidence_version_id: "",
                    context_sha256: "",
                    assessment: "",
                  }
                : null,
            )
          }
        />
        Declare an evidenced nil import population
      </label>
      <p>
        Missing rows do not prove zero. Review all three retained sources and
        select separate supporting evidence. Declare Box 6 and Box 7
        individually; any observed history contradicts nil for that population.
      </p>
      {value && (
        <>
          {(
            [
              ["registration", "Nil import TRN", "text"],
              ["period_start", "Nil import period start", "date"],
              ["period_end", "Nil import period end", "date"],
            ] as const
          ).map(([field, label, type]) => (
            <label key={field}>
              {label}
              <input
                required
                type={type}
                value={value[field]}
                onChange={(event) => update({ [field]: event.target.value })}
              />
            </label>
          ))}
          {(
            [
              ["declaration", "Box 6 declarations are nil"],
              ["adjustment", "Box 7 adjustments are nil"],
            ] as const
          ).map(([kind, label]) => (
            <label
              key={kind}
              style={{
                display: "flex",
                flexDirection: "row",
                justifyContent: "flex-start",
                alignItems: "center",
                gap: 8,
              }}
            >
              <input
                style={{
                  width: 16,
                  height: 16,
                  minHeight: 16,
                  margin: 0,
                  flex: "0 0 16px",
                }}
                type="checkbox"
                checked={value.kinds.includes(kind)}
                onChange={(event) =>
                  update({
                    kinds: event.target.checked
                      ? [...value.kinds, kind]
                      : value.kinds.filter((item) => item !== kind),
                  })
                }
              />
              {label}
            </label>
          ))}
          <label>
            Nil import supporting evidence
            <select
              required
              value={value.context_evidence_version_id}
              onChange={(event) =>
                update({
                  context_evidence_version_id: event.target.value,
                  context_sha256:
                    evidence.find((item) => item.id === event.target.value)
                      ?.sha256 || "",
                })
              }
            >
              <option value="">Select separate clean evidence</option>
              {evidence
                .filter((item) => item.scan_status === "CLEAN" && item.sha256)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Nil import assessment
            <textarea
              required
              minLength={10}
              maxLength={2000}
              value={value.assessment}
              onChange={(event) => update({ assessment: event.target.value })}
            />
          </label>
          <p>
            Enter independent zero detail-count, taxable-base and tax controls
            when deriving each nil VAT201 box. The derived source needs its own
            independent review.
          </p>
        </>
      )}
    </fieldset>
  );
}

"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Choice = {
  selected: boolean;
  due_date: string;
  due_date_reference: string;
};
type Props = {
  eid: string;
  resultId: string;
  rows: Record<string, unknown>[];
  evidence: { id: string; label: string; scan_status: string }[];
  onCreated: (id: string) => void;
};

export function BenefitSettlementSource({
  eid,
  resultId,
  rows,
  evidence,
  onCreated,
}: Props) {
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [employer, setEmployer] = useState("");
  const [document, setDocument] = useState("");
  const [count, setCount] = useState("");
  const [total, setTotal] = useState("");
  const [title, setTitle] = useState("");
  const [assessment, setAssessment] = useState("");
  const action = useAction<{ id: string }>();
  const eligible = rows.filter(
    (row) =>
      row.expected_benefit != null &&
      row.service_start &&
      row.service_end &&
      row.scheme === "gratuity",
  );
  const selections = Object.entries(choices)
    .filter(([, choice]) => choice.selected)
    .map(([result_row_id, choice]) => ({
      result_row_id,
      due_date: choice.due_date,
      due_date_reference: choice.due_date_reference.trim(),
    }));
  const valid =
    selections.length > 0 &&
    Number(count) === selections.length &&
    selections.every(
      (item) => item.due_date && item.due_date_reference.length >= 3,
    ) &&
    /^\d+(\.\d{1,8})?$/.test(total) &&
    employer.trim() &&
    document &&
    title.trim().length >= 3 &&
    assessment.trim().length >= 10;
  function update(id: string, change: Partial<Choice>) {
    setChoices((previous) => ({
      ...previous,
      [id]: {
        ...(previous[id] ?? {
          selected: false,
          due_date: "",
          due_date_reference: "",
        }),
        ...change,
      },
    }));
  }
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label="Expected gratuity settlement"
    >
      <h3>Prepare expected gratuity for bank settlement review</h3>
      <p>
        Select employee service spans and provide independent count, AED total
        and supported due dates. Declared paid amounts are not bank evidence.
        The prepared source needs independent review; reported settlements and
        bank movements remain separate inputs.
      </p>
      <p>
        Selections may span result pages. Controls cover selected rows only.
        Older results without service dates must be regenerated.
      </p>
      <ErrorState error={action.error} />
      <label>
        Gratuity expectation title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label>
        Assessed employer registration
        <input
          value={employer}
          onChange={(event) => setEmployer(event.target.value)}
        />
      </label>
      <label>
        Retained settlement scope and due-date evidence
        <select
          aria-label="Retained settlement scope and due-date evidence"
          value={document}
          onChange={(event) => setDocument(event.target.value)}
        >
          <option value="">Select clean retained evidence</option>
          {evidence
            .filter((item) => item.scan_status === "CLEAN")
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
        </select>
      </label>
      {eligible.map((row) => {
        const id = String(row.id);
        const choice = choices[id];
        return (
          <fieldset key={id} style={{ marginTop: 12, padding: 12 }}>
            <legend>Employee {id}</legend>
            <label>
              <input
                type="checkbox"
                aria-label={`Select gratuity ${id}`}
                checked={choice?.selected || false}
                onChange={(event) =>
                  update(id, { selected: event.target.checked })
                }
              />
              Include this service span
            </label>
            <p>
              {String(row.service_start)} to {String(row.service_end)} ·{" "}
              {String(row.work_model)} · {String(row.regime)} /{" "}
              {String(row.cohort)} · Expected AED {String(row.expected_benefit)}
            </p>
            {choice?.selected && (
              <>
                <label>
                  Assessed due date for {id}
                  <input
                    type="date"
                    min={String(row.service_end)}
                    value={choice.due_date}
                    onChange={(event) =>
                      update(id, { due_date: event.target.value })
                    }
                  />
                </label>
                <label>
                  Due-date evidence reference for {id}
                  <input
                    value={choice.due_date_reference}
                    onChange={(event) =>
                      update(id, { due_date_reference: event.target.value })
                    }
                  />
                </label>
              </>
            )}
          </fieldset>
        );
      })}
      <p>{selections.length} employee service span(s) selected.</p>
      <label>
        Independent selected employee count
        <input
          inputMode="numeric"
          value={count}
          onChange={(event) => setCount(event.target.value)}
        />
      </label>
      <label>
        Independent expected gratuity total (AED)
        <input
          inputMode="decimal"
          value={total}
          onChange={(event) => setTotal(event.target.value)}
        />
      </label>
      <label>
        Employer, employee scope and due-date assessment
        <textarea
          value={assessment}
          onChange={(event) => setAssessment(event.target.value)}
        />
      </label>
      <Button
        disabled={!valid || action.isPending}
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/benefit-settlement-source`,
              body: {
                result_id: resultId,
                employer_registration: employer.trim(),
                settlement_evidence_version_id: document,
                selections,
                expected_rows: Number(count),
                control_total: total,
                label: title.trim(),
                assessment: assessment.trim(),
              },
            });
            onCreated(result.id);
          } catch {
            /* useAction exposes the API error above. */
          }
        }}
      >
        Prepare expected gratuity source
      </Button>
    </section>
  );
}

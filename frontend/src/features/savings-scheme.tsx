"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Evidence = { id: string; label: string; scan_status: string };
type Group = { registration: string; period: string; fund_id: string };
type Choice = Group & {
  selected: boolean;
  count: string;
  amount: string;
  due: string;
  reference: string;
};
const money = (value: string) => /^\d+(\.\d{1,8})?$/.test(value);
const count = (value: string, minimum: number) =>
  /^\d+$/.test(value) && Number(value) >= minimum && Number(value) <= 5000;

export function SavingsEnrolmentDocument({
  value,
  onChange,
  evidence,
}: {
  value: string;
  onChange: (value: string) => void;
  evidence: Evidence[];
}) {
  return (
    <>
      <label>
        Retained savings enrolment document (optional shared document)
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">
            Use enrolment document references from the CSV
          </option>
          {evidence
            .filter((e) => e.scan_status === "CLEAN")
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.label} · {e.id.slice(0, 8)}
              </option>
            ))}
        </select>
      </label>
      <p>
        Enrolment dates, fund, participant reference, assessed service band and
        contributory salary remain explicit source facts. This binds retained
        document bytes; it does not verify a live fund registry. Basic-wage
        controls sum contract or assessed comparator bases before hours ratios
        and contribution rates; they are not gross payroll or fund
        contributions.
      </p>
    </>
  );
}

export function SavingsFundReportedSource({
  eid,
  sourceId,
  onCreated,
}: {
  eid: string;
  sourceId: string;
  onCreated: (id: string) => void;
}) {
  const [rows, setRows] = useState("");
  const [total, setTotal] = useState("");
  const [title, setTitle] = useState("");
  const [assessment, setAssessment] = useState("");
  const action = useAction<{ id: string }>();
  const valid =
    count(rows, 0) &&
    money(total) &&
    title.trim().length >= 3 &&
    assessment.trim().length >= 10;
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label="Preserve fund-reported remittances"
    >
      <h3>Prepare fund observations for bank allocation</h3>
      <p>
        Retain the complete original participant, fund, enrolment and coverage
        population as reported amounts. This creates an unverified reported
        source; expected contributions and bank payments remain separate. An
        empty population requires the original reviewed nil declaration.
      </p>
      <ErrorState error={action.error} />
      <label>
        Fund observation source title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Independent original fund row count
        <input
          inputMode="numeric"
          value={rows}
          onChange={(e) => setRows(e.target.value)}
        />
      </label>
      <label>
        Independent original fund contribution total (AED)
        <input
          inputMode="decimal"
          value={total}
          onChange={(e) => setTotal(e.target.value)}
        />
      </label>
      <label>
        Original fund population assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <Button
        disabled={!valid || action.isPending}
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/savings-reported-obligation-source`,
              body: {
                source_id: sourceId,
                expected_rows: Number(rows),
                control_total: total,
                label: title.trim(),
                assessment: assessment.trim(),
              },
            });
            onCreated(result.id);
          } catch {
            /* useAction renders the API error. */
          }
        }}
      >
        Prepare reported fund remittances
      </Button>
    </section>
  );
}

export function SavingsContributionExpectations({
  eid,
  resultId,
  rows,
  evidence,
  onCreated,
}: {
  eid: string;
  resultId: string;
  rows: Record<string, unknown>[];
  evidence: Evidence[];
  onCreated: (id: string) => void;
}) {
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [document, setDocument] = useState("");
  const [title, setTitle] = useState("");
  const [assessment, setAssessment] = useState("");
  const action = useAction<{ id: string }>();
  const groups: Record<string, Group> = {};
  for (const row of rows) {
    const group = {
      registration: String(row.registration),
      period: String(row.period),
      fund_id: String(row.fund_id),
    };
    groups[JSON.stringify([group.registration, group.period, group.fund_id])] =
      group;
  }
  for (const [key, value] of Object.entries(choices))
    if (value.selected) groups[key] = value;
  const selected = Object.values(choices).filter((c) => c.selected);
  const valid =
    selected.length > 0 &&
    selected.every(
      (c) =>
        count(c.count, 1) &&
        money(c.amount) &&
        c.due &&
        c.reference.trim().length >= 3,
    ) &&
    document &&
    title.trim().length >= 3 &&
    assessment.trim().length >= 10;
  function update(key: string, group: Group, change: Partial<Choice>) {
    setChoices((old) => ({
      ...old,
      [key]: {
        ...group,
        ...(old[key] || {
          selected: false,
          count: "",
          amount: "",
          due: "",
          reference: "",
        }),
        ...change,
      },
    }));
  }
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label="Expected savings basic remittances"
    >
      <h3>Prepare fund-specific expected basic contributions</h3>
      <p>
        Enter independent participant counts, contribution totals and evidenced
        due dates for each selected employer, month and fund. Membership and
        coverage remain separate on every employee row. Controls cover the full
        selected group, including other result pages; selected groups persist
        across pages. Funds cannot share a pooled amount control.
      </p>
      <ErrorState error={action.error} />
      <label>
        Savings expectation title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Retained savings remittance due-date evidence
        <select value={document} onChange={(e) => setDocument(e.target.value)}>
          <option value="">Select retained due-date support</option>
          {evidence
            .filter((e) => e.scan_status === "CLEAN")
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.label} · {e.id.slice(0, 8)}
              </option>
            ))}
        </select>
      </label>
      {Object.entries(groups).map(([key, group]) => {
        const choice = choices[key];
        const name = `${group.fund_id} / ${group.registration} / ${group.period}`;
        return (
          <fieldset key={key}>
            <legend>{name}</legend>
            <label>
              <input
                type="checkbox"
                aria-label={`Select savings group ${name}`}
                checked={!!choice?.selected}
                onChange={(e) =>
                  update(key, group, { selected: e.target.checked })
                }
              />
              Include this fund group
            </label>
            {choice?.selected && (
              <>
                <label>
                  Independent participant count
                  <input
                    aria-label={`Independent participant count ${name}`}
                    inputMode="numeric"
                    value={choice.count}
                    onChange={(e) =>
                      update(key, group, { count: e.target.value })
                    }
                  />
                </label>
                <label>
                  Independent expected total (AED)
                  <input
                    aria-label={`Independent expected total ${name}`}
                    inputMode="decimal"
                    value={choice.amount}
                    onChange={(e) =>
                      update(key, group, { amount: e.target.value })
                    }
                  />
                </label>
                <label>
                  Assessed remittance due date
                  <input
                    aria-label={`Assessed due date ${name}`}
                    type="date"
                    value={choice.due}
                    onChange={(e) =>
                      update(key, group, { due: e.target.value })
                    }
                  />
                </label>
                <label>
                  Due-date evidence reference
                  <input
                    aria-label={`Due-date reference ${name}`}
                    value={choice.reference}
                    onChange={(e) =>
                      update(key, group, { reference: e.target.value })
                    }
                  />
                </label>
              </>
            )}
          </fieldset>
        );
      })}
      <label>
        Savings remittance scope assessment
        <textarea
          value={assessment}
          onChange={(e) => setAssessment(e.target.value)}
        />
      </label>
      <Button
        disabled={!valid || action.isPending}
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/contribution-obligation-source`,
              body: {
                result_id: resultId,
                due_date_evidence_version_id: document,
                groups: selected.map((c) => ({
                  registration: c.registration,
                  period: c.period,
                  fund_id: c.fund_id,
                  component: "SAVINGS:EMPLOYER_BASIC",
                  expected_rows: Number(c.count),
                  amount: c.amount,
                  due_date: c.due,
                  due_date_reference: c.reference.trim(),
                })),
                label: title.trim(),
                assessment: assessment.trim(),
              },
            });
            onCreated(result.id);
          } catch {
            /* useAction renders the API error. */
          }
        }}
      >
        Prepare expected savings remittances
      </Button>
    </section>
  );
}

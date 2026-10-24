"use client";
import { useState } from "react";
import Link from "next/link";
import { useAction, useCan } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
type Contract = {
  name: string;
  fields: { name: string; type: string }[];
  required_evidence: string[];
  limitation: string;
};
type Source = {
  kind?: string;
  id: string;
  reference: string;
  title: string;
  status: string;
  advanced_case_id?: number | null;
};
export function UAEAdvancedInputs({
  eid,
  caseId,
  contract,
  sources,
  onResult,
  onSaved,
}: {
  eid: string;
  caseId: number;
  contract: Contract;
  sources: Source[];
  onResult: (r: Record<string, unknown>) => void;
  onSaved: () => void;
}) {
  const action = useAction<Record<string, unknown>>();
  const canPrepare = useCan("workingpaper.create"),
    canRun = useCan("ai.workflow.run");
  const [rows, setRows] = useState<Record<string, string>[]>([{}]);
  const [policy, setPolicy] = useState<Record<string, string>>({
    kind:
      caseId <= 61 || (caseId >= 63 && caseId <= 70) || caseId === 80
        ? "legislation"
        : "accounting_requirement",
  });
  const [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [currency, setCurrency] = useState("AED"),
    [assumptions, setAssumptions] = useState(""),
    [questions, setQuestions] = useState(""),
    [inputId, setInputId] = useState(""),
    [error, setError] = useState<Error>();
  const approved = sources.filter((s) =>
    ["APPROVED", "LOCKED"].includes(s.status),
  );
  function setRow(index: number, key: string, value: string) {
    setRows((old) =>
      old.map((r, i) => (i === index ? { ...r, [key]: value } : r)),
    );
  }
  async function prepare() {
    setError(undefined);
    try {
      const parsed = rows.map((row) => {
        const r: Record<string, unknown> = {
          reference: row.reference,
          evidence_id: row.evidence_id,
        };
        for (const f of contract.fields) {
          if (!row[f.name] && f.type !== "y") throw new Error(`Provide ${f.name} for each row`);
          r[f.name] = f.type === "b" ? row[f.name] === "true" : f.type === "y" ? row[f.name] || null : row[f.name];
        }
        return r;
      });
      const ids = [
        ...new Set([policy.source_id, ...rows.map((r) => r.evidence_id)]),
      ];
      if (ids.some((i) => !i))
        throw new Error("Select policy and row evidence");
      const result = await action.mutateAsync({
        path: `ai/engagements/${eid}/use-cases/${caseId}/actions`,
        body: {
          action: "draft-workpaper",
          idempotency_key: crypto.randomUUID(),
          payload: {
            reference: `UAE-${caseId}-${crypto.randomUUID().slice(0, 8)}`,
            title: contract.name,
            body: {
              folder: `UAE ${caseId}`,
              sections: [{ heading: "Scope", text: contract.limitation }],
              conclusion:
                "Unreviewed input schedule; independent approval required before execution.",
              sources: ids.map((id) => ({ kind: "record", id })),
              advanced_input: {
                use_case_id: caseId,
                period_start: start,
                period_end: end,
                currency,
                policy,
                assumptions: assumptions.split("\n").filter(Boolean),
                unresolved_questions: questions.split("\n").filter(Boolean),
                rows: parsed,
              },
            },
          },
        },
      });
      onResult(result);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Schedule rejected"));
    }
  }
  async function fileReadiness() {
    setError(undefined);
    try {
      onResult(
        await action.mutateAsync({
          path: `ai/engagements/${eid}/use-cases/${caseId}/actions`,
          body: {
            action: "file-readiness",
            idempotency_key: crypto.randomUUID(),
          },
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e : new Error("File checks failed"));
    }
  }
  async function scan() {
    setError(undefined);
    try {
      onResult(
        await action.mutateAsync({
          path: `ai/engagements/${eid}/use-cases/97/actions`,
          body: {
            action: "workbook-integrity",
            record_id: inputId,
            idempotency_key: crypto.randomUUID(),
          },
        }),
      );
    } catch (e) {
      setError(
        e instanceof Error ? e : new Error("Workbook inspection failed"),
      );
    }
  }
  async function run() {
    setError(undefined);
    try {
      onResult(
        await action.mutateAsync({
          path: `ai/engagements/${eid}/use-cases/${caseId}/actions`,
          body: {
            action: "advanced-review",
            record_id: inputId,
            idempotency_key: crypto.randomUUID(),
          },
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Review rejected"));
    }
  }
  return (
    <section aria-label="Structured review schedule">
      <h3>{contract.name}</h3>
      {[99, 100].includes(caseId) && (
        <>
          <Button
            disabled={!canRun || action.isPending}
            onClick={fileReadiness}
          >
            Check current engagement file and reporting issues
          </Button>
          <p>
            Reads the actual authorized file population, completion checks,
            misstatement register and stale papers. No audit opinion is selected
            and no file is sealed.
          </p>
        </>
      )}
      {caseId === 97 && (
        <fieldset>
          <legend>Inspect original workbook</legend>
          <label>
            Approved XLSX evidence
            <select
              value={inputId}
              onChange={(e) => setInputId(e.target.value)}
            >
              <option value="">Select original evidence</option>
              {approved
                .filter((s) => s.kind === "evidence")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.reference} · {s.title}
                  </option>
                ))}
            </select>
          </label>
          <Button
            disabled={!canRun || !inputId || action.isPending}
            onClick={scan}
          >
            Inspect workbook formulas
          </Button>
          <p>
            Static inspection preserves the original and never executes macros,
            formulas or external links.
          </p>
        </fieldset>
      )}
      <p>{contract.limitation}</p>
      <p>
        Enter reviewed source values. Numbers use decimal strings and rates use
        fractions. The engine does not infer facts from uploaded text. Save an
        input paper, obtain independent approval, then execute its immutable
        inputs.
      </p>
      <label>
        Period start
        <input
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </label>
      <label>
        Period end
        <input
          type="date"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <label>
        Schedule currency
        <input
          value={currency}
          maxLength={3}
          onChange={(e) => setCurrency(e.target.value.toUpperCase())}
        />
      </label>
      <fieldset>
        <legend>Adopted policy or contract</legend>
        {[
          "source_id",
          "source_locator",
          "version",
          "kind",
          "effective_from",
          "effective_to",
          "adoption_assessment",
        ].map((key) => (
          <label key={key}>
            {key.replaceAll("_", " ")}
            {key === "source_id" ? (
              <select
                value={policy[key] || ""}
                onChange={(e) =>
                  setPolicy((p) => ({ ...p, [key]: e.target.value }))
                }
              >
                <option value="">Select approved policy evidence</option>
                {approved.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.reference} · {s.title}
                  </option>
                ))}
              </select>
            ) : key === "kind" ? (
              <select
                value={policy[key]}
                onChange={(e) =>
                  setPolicy((p) => ({ ...p, [key]: e.target.value }))
                }
              >
                {[
                  "legislation",
                  "official_guidance",
                  "accounting_requirement",
                  "firm_policy",
                  "contract",
                ].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            ) : (
              <input
                type={key.startsWith("effective_") ? "date" : "text"}
                value={policy[key] || ""}
                onChange={(e) =>
                  setPolicy((p) => ({ ...p, [key]: e.target.value }))
                }
              />
            )}
          </label>
        ))}
      </fieldset>
      {rows.map((row, index) => (
        <fieldset key={index}>
          <legend>Source item {index + 1}</legend>
          <label>
            Unique reference
            <input
              value={row.reference || ""}
              onChange={(e) => setRow(index, "reference", e.target.value)}
            />
          </label>
          <label>
            Row evidence
            <select
              value={row.evidence_id || ""}
              onChange={(e) => setRow(index, "evidence_id", e.target.value)}
            >
              <option value="">Select approved source</option>
              {approved.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.reference} · {s.title}
                </option>
              ))}
            </select>
          </label>
          {contract.fields.map((f) => (
            <label key={f.name}>
              {f.name.replaceAll("_", " ")}
              {f.type === "b" ? (
                <select
                  value={row[f.name] || ""}
                  onChange={(e) => setRow(index, f.name, e.target.value)}
                >
                  <option value="">Unresolved: select observed fact</option>
                  <option value="true">Yes, supported</option>
                  <option value="false">No</option>
                </select>
              ) : (
                <input
                  type={f.type === "x" || f.type === "y" ? "date" : "text"}
                  inputMode={
                    f.type === "n" || f.type === "d" ? "decimal" : undefined
                  }
                  value={row[f.name] || ""}
                  onChange={(e) => setRow(index, f.name, e.target.value)}
                />
              )}
            </label>
          ))}
          {rows.length > 1 && (
            <Button
              onClick={() =>
                setRows((old) => old.filter((_, i) => i !== index))
              }
            >
              Remove item {index + 1}
            </Button>
          )}
        </fieldset>
      ))}
      <Button
        disabled={rows.length >= 500}
        onClick={() => setRows((old) => [...old, {}])}
      >
        Add source item
      </Button>
      <label>
        Assumptions, one per line
        <textarea
          value={assumptions}
          onChange={(e) => setAssumptions(e.target.value)}
        />
      </label>
      <label>
        Unresolved questions, one per line
        <textarea
          value={questions}
          onChange={(e) => setQuestions(e.target.value)}
        />
      </label>
      <Button disabled={!canPrepare || action.isPending} onClick={prepare}>
        Save input paper for independent approval
      </Button>
      <Link href={`/engagements/${eid}/working-papers`}>
        Review and approve input papers
      </Link>
      <label>
        Approved case-specific input paper
        <select value={inputId} onChange={(e) => setInputId(e.target.value)}>
          <option value="">Select approved input</option>
          {approved
            .filter((s) => s.advanced_case_id === caseId)
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.reference} · {s.title}
              </option>
            ))}
        </select>
      </label>
      <Button disabled={!canRun || !inputId || action.isPending} onClick={run}>
        Run structured review
      </Button>
      {error && <ErrorState error={error} />}
    </section>
  );
}

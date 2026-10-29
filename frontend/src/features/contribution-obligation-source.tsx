"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type Props = {
  eid: string;
  resultId: string;
  pension: boolean;
  evidence: { id: string; label: string; scan_status: string }[];
  onCreated: (id: string) => void;
};

export function ContributionObligationSource({
  eid,
  resultId,
  pension,
  evidence,
  onCreated,
}: Props) {
  const [groups, setGroups] = useState("[]");
  const [scope, setScope] = useState("{}");
  const [document, setDocument] = useState("");
  const [title, setTitle] = useState("");
  const [assessment, setAssessment] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const action = useAction<{ id: string }>();
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label="Expected contribution remittances"
    >
      <h3>Prepare expected contributions for settlement review</h3>
      <p>
        Supply independent row counts, amounts and evidenced due dates for each
        registration, wage month and component. Each assessed row remains
        separate. The prepared source needs independent review and can establish
        only expected remittances; authority returns and bank payments require
        separate evidence.
      </p>
      {pension && (
        <p>
          Government pension support is a separate payer. Select one assessed
          pension scope and only employee or net-employer components.
        </p>
      )}
      <ErrorState error={error || action.error} />
      <label>
        Expected remittance source title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label>
        Retained due-date evidence version
        <input
          list={`contribution-documents-${resultId}`}
          value={document}
          onChange={(event) => setDocument(event.target.value)}
        />
      </label>
      <datalist id={`contribution-documents-${resultId}`}>
        {evidence
          .filter((item) => item.scan_status === "CLEAN")
          .map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
      </datalist>
      <p>
        Select a clean retained version, or enter its version ID. Each due-date
        reference must identify the relevant support in that document.
      </p>
      <label>
        Independent contribution group controls (JSON)
        <textarea
          rows={9}
          style={{
            height: Math.min(
              640,
              Math.max(240, (groups.split("\n").length + 1) * 18),
            ),
          }}
          value={groups}
          onChange={(event) => setGroups(event.target.value)}
          spellCheck={false}
        />
      </label>
      <Button
        onClick={() =>
          setGroups(
            JSON.stringify(
              [
                {
                  registration: "",
                  period: "",
                  component: "",
                  expected_rows: null,
                  amount: null,
                  due_date: "",
                  due_date_reference: "",
                },
              ],
              null,
              2,
            ),
          )
        }
      >
        Show contribution control format
      </Button>
      {pension && (
        <>
          <label>
            Assessed pension scope (JSON)
            <textarea
              rows={6}
              style={{
                height: Math.min(
                  320,
                  Math.max(180, (scope.split("\n").length + 1) * 18),
                ),
              }}
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              spellCheck={false}
            />
          </label>
          <Button
            onClick={() =>
              setScope(
                JSON.stringify(
                  {
                    authority: "",
                    scheme: "",
                    membership_cohort: "",
                    pension_country: "",
                    nationality: "",
                    employment_sector: "",
                    jurisdiction: "",
                  },
                  null,
                  2,
                ),
              )
            }
          >
            Show pension scope fields
          </Button>
        </>
      )}
      <label>
        Remittance scope and due-date assessment
        <textarea
          value={assessment}
          style={{ height: 80 }}
          onChange={(event) => setAssessment(event.target.value)}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          !document.trim() ||
          title.trim().length < 3 ||
          assessment.trim().length < 10
        }
        onClick={async () => {
          setError(null);
          try {
            const controls: unknown = JSON.parse(groups);
            const pensionScope: unknown = pension ? JSON.parse(scope) : null;
            if (
              !Array.isArray(controls) ||
              !controls.length ||
              controls.length > 1000
            )
              throw new Error(
                "Supply one to one thousand independent contribution group controls",
              );
            if (
              pension &&
              (!pensionScope ||
                typeof pensionScope !== "object" ||
                Array.isArray(pensionScope))
            )
              throw new Error(
                "Supply the explicitly assessed pension scope as a JSON object",
              );
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/contribution-obligation-source`,
              body: {
                result_id: resultId,
                due_date_evidence_version_id: document.trim(),
                groups: controls,
                pension_scope: pensionScope,
                label: title.trim(),
                assessment: assessment.trim(),
              },
            });
            onCreated(result.id);
          } catch (failure) {
            setError(failure as Error);
          }
        }}
      >
        Prepare expected remittance source
      </Button>
    </section>
  );
}

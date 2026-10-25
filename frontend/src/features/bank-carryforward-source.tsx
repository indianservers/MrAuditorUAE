"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export function BankCarryforwardSource({
  prefix,
  selected,
  onCreated,
}: {
  prefix: string;
  selected: string;
  onCreated: (id: string) => void;
}) {
  const action = useAction();
  const [label, setLabel] = useState("");
  const [count, setCount] = useState("");
  const [positive, setPositive] = useState("");
  const [negative, setNegative] = useState("");
  const [assessment, setAssessment] = useState("");
  return (
    <details>
      <summary>
        Carry reviewed bank residuals into the next clearance window
      </summary>
      <p>
        Carry every nonzero residual to this result&apos;s review-through date.
        Original item dates remain unchanged. Supply independent row, positive
        and negative controls, including explicit zeros. This excludes
        new-period outstanding items and is not a complete new-period BRS.
        Assess the retained statement window and unresolved reversals before
        preparing the source.
      </p>
      <label>
        Carry-forward source title
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
        />
      </label>
      <label>
        Independent residual row count
        <input
          type="number"
          min="0"
          max="5000"
          value={count}
          onChange={(event) => setCount(event.target.value)}
        />
      </label>
      <label>
        Independent positive residual total
        <input
          value={positive}
          onChange={(event) => setPositive(event.target.value)}
        />
      </label>
      <label>
        Independent negative residual total
        <input
          value={negative}
          onChange={(event) => setNegative(event.target.value)}
        />
      </label>
      <label>
        Carry-forward window and reversal assessment
        <textarea
          value={assessment}
          onChange={(event) => setAssessment(event.target.value)}
        />
      </label>
      {action.error && <ErrorState error={action.error} />}
      <Button
        disabled={
          action.isPending ||
          !label.trim() ||
          count === "" ||
          positive === "" ||
          negative === "" ||
          assessment.trim().length < 10
        }
        onClick={async () => {
          const created = await action
            .mutateAsync({
              path: `${prefix}/events/${selected}/bank-carryforward-source`,
              body: {
                label,
                expected_rows: Number(count),
                positive_total: positive,
                negative_total: negative,
                assessment,
              },
            })
            .catch(() => null);
          if (created) onCreated(created.id);
        }}
      >
        Prepare carried bank residuals
      </Button>
    </details>
  );
}

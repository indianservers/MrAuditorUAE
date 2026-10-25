"use client";

import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export type FixtureReceipt = {
  passed: boolean;
  case_count: number;
  receipt_sha256: string;
  implementation_sha256?: string;
  support?: string;
  message?: string;
  outcomes: unknown[];
};

export function RuleFixtureEditor({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [format, setFormat] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [preview, setPreview] = useState<{
    input: string;
    result: FixtureReceipt;
  } | null>(null);
  const contract = useAPI<{
    schema: Record<string, unknown>;
    template: Record<string, unknown>[];
  }>(`regulatory/rules/${id}/validation-contract`, format);
  const action = useAction<FixtureReceipt>();
  const shown = preview?.input === value ? preview.result : null;
  return (
    <section aria-label="Independent rule fixtures">
      <h3>Independent validation fixtures</h3>
      <p>
        Use anonymized test inputs and independently determined expected
        outcomes. Enter money as decimal strings. These examples are shared at
        firm rule-library scope. Passing fixtures test the supplied cases and
        current implementation; legal qualification is separate.
      </p>
      <label>
        Validation fixture cases (JSON)
        <textarea
          aria-label="Validation fixture cases (JSON)"
          rows={10}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
        />
      </label>
      <ErrorState error={error || action.error || contract.error} />
      <div className="toolbar">
        <Button
          disabled={action.isPending}
          onClick={async () => {
            setError(null);
            try {
              const cases: unknown = JSON.parse(value);
              if (
                !Array.isArray(cases) ||
                cases.length < 1 ||
                cases.length > 20
              )
                throw new Error("Provide one to twenty fixture cases");
              const result = await action.mutateAsync({
                path: `regulatory/rules/${id}/validate`,
                body: { cases },
              });
              setPreview({ input: value, result });
            } catch (failure) {
              setError(failure as Error);
            }
          }}
        >
          Check supplied fixtures
        </Button>
        <Button onClick={() => setFormat((previous) => !previous)}>
          Show fixture input format
        </Button>
        {contract.data && (
          <Button
            onClick={() =>
              onChange(JSON.stringify(contract.data!.template, null, 2))
            }
          >
            Insert incomplete fixture skeleton
          </Button>
        )}
      </div>
      {format && contract.data && (
        <details open>
          <summary>Typed fixture input contract</summary>
          <p>
            Fill every required input and expected outcome. The skeleton
            contains no calculated expected amounts.
          </p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(contract.data.schema, null, 2)}
          </pre>
        </details>
      )}
      {shown && (
        <section aria-label="Fixture check result">
          <p role="status">
            {shown.passed
              ? "All supplied fixtures passed"
              : "Fixture validation failed"}{" "}
            · {shown.case_count} cases
          </p>
          <p>
            {shown.message ||
              (shown.support === "BLOCKING_ONLY_NO_COMPLETE_WAGE_MONTH"
                ? "These fixtures verify refusal of split-month calculation; no whole-month calculation was demonstrated."
                : "The supplied cases exercised an applicable result; this is not legal qualification.")}{" "}
            · Receipt SHA-256: {shown.receipt_sha256}
          </p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(shown.outcomes, null, 2)}
          </pre>
        </section>
      )}
    </section>
  );
}

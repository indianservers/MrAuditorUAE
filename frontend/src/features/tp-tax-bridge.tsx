"use client";
import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState, Facts } from "@/components/ui/primitives";
import type { RecordRow } from "@/types/models";

export function TPTaxBridge({
  base,
  runId,
  authorized,
}: {
  base: string;
  runId: string;
  authorized: boolean;
}) {
  const [fields, setFields] = useState({
    judgment_id: "",
    tax_profile_id: "",
    tax_rule_id: "",
    account_codes: "",
    rationale: "",
  });
  const [result, setResult] = useState<RecordRow | null>(null);
  const action = useAction();
  return (
    <details>
      <summary>Corporate Tax adjustment bridge</summary>
      <p>
        Use an independently approved TP judgment. The bridge creates a CT draft
        for separate review against the same approved financial source.
      </p>
      {Object.entries(fields).map(([key, value]) => (
        <label key={key}>
          {key.replaceAll("_", " ")}
          <input
            value={value}
            onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
          />
        </label>
      ))}
      <p>
        Account codes are comma-separated statement line codes. Downward
        adjustments require reviewed FTA approval.
      </p>
      <Button
        disabled={
          !authorized ||
          !runId ||
          Object.values(fields).some((x) => !x.trim()) ||
          action.isPending
        }
        onClick={async () => {
          try {
            setResult(
              await action.mutateAsync({
                path: `${base}/runs/${runId}/tax-adjustment`,
                body: {
                  ...fields,
                  account_codes: fields.account_codes
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                },
              }),
            );
          } catch {}
        }}
      >
        Prepare CT adjustment draft
      </Button>
      {action.error && <ErrorState error={action.error} />}
      {result && <Facts data={result} />}
    </details>
  );
}

"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

export function WithholdingObligationSource({
  eid,
  sourceId,
  onCreated,
}: {
  eid: string;
  sourceId: string;
  onCreated: (id: string) => void;
}) {
  const action = useAction<{ id: string }>();
  const [purpose, setPurpose] = useState("");
  const [role, setRole] = useState("");
  const [fields, setFields] = useState({
    cutoff_date: "",
    expected_current_rows: "",
    amount: "",
    label: "",
    assessment: "",
  });
  const [error, setError] = useState<Error | null>(null);
  return (
    <section aria-label="Withholding bank-allocation source">
      <details>
        <summary>
          Prepare withholding obligations for split bank allocations
        </summary>
        <p>
          Select the purpose of this independent source. Deductor and collector
          liabilities remain separate from beneficiary tax credits. Every
          retained identity needs one current observation; cancelled-only
          records cannot become zero.
        </p>
        <label>
          Withholding obligation purpose
          <select
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
          >
            <option value="">Select the source purpose</option>
            <option value="expected">
              Expected liability from assessed rules
            </option>
            <option value="reported">Independently reported liability</option>
          </select>
        </label>
        <label>
          Withholding payer role
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
          >
            <option value="">Select the legal payer role</option>
            <option value="deductor">TDS deductor</option>
            <option value="collector">TCS collector</option>
          </select>
        </label>
        {(
          [
            ["cutoff_date", "Withholding obligation cutoff", "date"],
            [
              "expected_current_rows",
              "Independent current withholding rows",
              "text",
            ],
            ["amount", "Independent current withholding total (INR)", "text"],
            ["label", "Withholding obligation source title", "text"],
          ] as const
        ).map(([key, label, type]) => (
          <label key={key}>
            {label}
            <input
              type={type}
              value={fields[key]}
              onChange={(event) =>
                setFields({ ...fields, [key]: event.target.value })
              }
            />
          </label>
        ))}
        <label>
          Withholding allocation scope assessment
          <textarea
            value={fields.assessment}
            onChange={(event) =>
              setFields({ ...fields, assessment: event.target.value })
            }
          />
        </label>
        <p>
          Expected rows need a current retained rule assessment and explicit due
          dates. Payment dates in the source cannot substitute for bank
          evidence. Tax year, section and transaction references stay separate
          in the allocation review. Use the same cutoff for preparation and
          allocation.
        </p>
        <ErrorState error={error || action.error} />
        <Button
          disabled={action.isPending}
          onClick={async () => {
            if (
              !purpose ||
              !role ||
              !/^[1-9][0-9]*$/.test(fields.expected_current_rows) ||
              !fields.amount.trim() ||
              !fields.cutoff_date ||
              fields.assessment.trim().length < 10 ||
              fields.label.trim().length < 3
            ) {
              setError(
                new Error(
                  "Enter the source purpose, payer role, cutoff and independent row/amount controls, with a title and scope assessment.",
                ),
              );
              return;
            }
            setError(null);
            const created = await action
              .mutateAsync({
                path: `intelligence/engagements/${eid}/events/${sourceId}/withholding-obligation-source`,
                body: {
                  ...fields,
                  expected_current_rows: Number(fields.expected_current_rows),
                  purpose,
                  legal_role: role,
                },
              })
              .catch(() => null);
            if (created) onCreated(created.id);
          }}
        >
          Prepare withholding bank-allocation source
        </Button>
        <p>
          The source starts unverified and needs independent review. Bank cash
          allocations do not prove government challan posting, return filing or
          beneficiary credit.
        </p>
      </details>
    </section>
  );
}

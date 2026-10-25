"use client";

import { useState } from "react";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type EmployeeChoice = {
  id: string;
  label: string;
  table_type?: string;
  kind: string;
  freshness: string;
  review_status: string;
};
type Profile = {
  id: string;
  rule_key: string;
  version: number;
  state: string;
  body: {
    title: string;
    method: string;
    effective_from: string;
    effective_to?: string | null;
  };
};

type SourceProps = {
  eid: string;
  employees: EmployeeChoice[];
  onCreated: (id: string) => void;
};

export function PublishedBenefitSource(props: SourceProps) {
  return <PublishedProfiles {...props} country="AE" profileKind="benefit" />;
}

export function PublishedPayrollSource(props: SourceProps) {
  return <PublishedProfiles {...props} country="IN" profileKind="payroll" />;
}

export function PublishedPensionSource(props: SourceProps) {
  return <PublishedProfiles {...props} country="AE" profileKind="pension" />;
}

function PublishedProfiles({
  eid,
  employees,
  onCreated,
  country,
  profileKind,
}: SourceProps & {
  country: "AE" | "IN";
  profileKind: "benefit" | "payroll" | "pension";
}) {
  const payroll = profileKind !== "benefit";
  const noun = profileKind;
  const region = `${country === "IN" ? "India" : "UAE"} ${noun}`;
  const sourceLabel = payroll
    ? `Reviewed ${noun} basis source`
    : "Reviewed benefit employee source";
  const countLabel = payroll
    ? "Independent wage-basis row count"
    : "Independent employee row count";
  const titleLabel = `Published ${noun} source title`;
  const assessmentLabel = payroll
    ? `${noun === "pension" ? "Pension" : "Payroll"} profile applicability assessment`
    : "Benefit profile applicability assessment";
  const [employee, setEmployee] = useState("");
  const [selected, setSelected] = useState<Profile[]>([]);
  const [offset, setOffset] = useState(0);
  const [count, setCount] = useState("");
  const [label, setLabel] = useState("");
  const [assessment, setAssessment] = useState("");
  const profiles = useAPI<{ items: Profile[] }>(
    `regulatory/rules?country=${country}&offset=${offset}&limit=50`,
  );
  const action = useAction<{ id: string }>();
  const eligible = employees.filter(
    (item) =>
      item.kind === "workflow-source" &&
      item.table_type === (payroll ? `${noun}-bases` : "benefit-employees") &&
      item.freshness === "CURRENT" &&
      item.review_status === "REVIEWED",
  );
  const shown =
    profiles.data?.items.filter(
      (item) =>
        item.state === "PUBLISHED" && item.body.method === `${noun}_profile`,
    ) || [];
  return (
    <section
      className="main-panel"
      style={{ padding: 20, marginTop: 16 }}
      aria-label={`Published ${region} profiles`}
    >
      <h2>Prepare rules from published {region} profiles</h2>
      <p>
        {noun === "pension"
          ? "Select reviewed pension salary bases and profiles covering every complete wage month, authority, scheme and membership cohort."
          : payroll
            ? "Select reviewed assessed wage bases and profiles covering every complete wage month and slab."
            : "Select a reviewed employee population and the published profiles covering its service-end dates."}{" "}
        The prepared source needs independent review before calculation.
      </p>
      <Link href="/settings/regulatory-rules">Review the rule library</Link>
      <ErrorState error={profiles.error || action.error} />
      <label>
        {sourceLabel}
        <select
          aria-label={sourceLabel}
          value={employee}
          onChange={(event) => setEmployee(event.target.value)}
        >
          <option value="">
            {payroll
              ? "Select reviewed wage bases"
              : "Select reviewed employees"}
          </option>
          {eligible.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <p>
        Older population sources can be loaded using the source history controls
        below.
      </p>
      <fieldset>
        <legend>Published {noun} profile versions</legend>
        {!shown.length && (
          <p>No published {noun} profiles on this library page.</p>
        )}
        {shown.map((profile) => (
          <label key={profile.id} style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={selected.some((item) => item.id === profile.id)}
              disabled={
                selected.length >= 20 &&
                !selected.some((item) => item.id === profile.id)
              }
              onChange={(event) =>
                setSelected((previous) =>
                  event.target.checked
                    ? [...previous, profile]
                    : previous.filter((item) => item.id !== profile.id),
                )
              }
            />
            {profile.rule_key} · v{profile.version} · {profile.body.title} ·{" "}
            {profile.body.effective_from} to{" "}
            {profile.body.effective_to || "open ended"}
          </label>
        ))}
        <div className="toolbar">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous profile page
          </Button>
          <Button
            disabled={profiles.data?.items.length !== 50}
            onClick={() => setOffset(offset + 50)}
          >
            Next profile page
          </Button>
        </div>
        {!!selected.length && (
          <ul aria-label={`Selected ${noun} profiles`}>
            {selected.map((profile) => (
              <li key={profile.id}>
                {profile.rule_key} v{profile.version}{" "}
                <Button
                  onClick={() =>
                    setSelected((previous) =>
                      previous.filter((item) => item.id !== profile.id),
                    )
                  }
                >
                  Remove {profile.rule_key} v{profile.version}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </fieldset>
      <label>
        {countLabel}
        <input
          aria-label={countLabel}
          type="number"
          min={1}
          max={5000}
          value={count}
          onChange={(event) => setCount(event.target.value)}
        />
      </label>
      <label>
        {titleLabel}
        <input
          aria-label={titleLabel}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
        />
      </label>
      <label>
        {assessmentLabel}
        <textarea
          aria-label={assessmentLabel}
          value={assessment}
          onChange={(event) => setAssessment(event.target.value)}
        />
      </label>
      <Button
        disabled={
          action.isPending ||
          !eligible.some((item) => item.id === employee) ||
          !selected.length ||
          !Number.isInteger(Number(count)) ||
          Number(count) < 1 ||
          Number(count) > 5000 ||
          label.trim().length < 3 ||
          assessment.trim().length < 10
        }
        onClick={async () => {
          const result = await action
            .mutateAsync({
              path: `intelligence/engagements/${eid}/${noun}-rule-source`,
              body: {
                ...(payroll
                  ? {
                      basis_source_id: employee,
                      expected_basis_rows: Number(count),
                    }
                  : {
                      employee_source_id: employee,
                      expected_employee_rows: Number(count),
                    }),
                rule_version_ids: selected.map((item) => item.id),
                label: label.trim(),
                assessment: assessment.trim(),
              },
            })
            .catch(() => null);
          if (result) onCreated(result.id);
        }}
      >
        Prepare published {noun} rule source
      </Button>
    </section>
  );
}

"use client";
import { useState } from "react";
import { useAction, useCan } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { RecordRow } from "@/types/models";

export function SoDImport({ base }: { base: string }) {
  const action = useAction<RecordRow>();
  const [file, setFile] = useState<File>();
  const [reference, setReference] = useState("");
  const [title, setTitle] = useState("");
  const [system, setSystem] = useState("");
  const [rule, setRule] = useState("");
  const [asOf, setAsOf] = useState("");
  const [evidence, setEvidence] = useState("");
  const [basis, setBasis] = useState("point-in-time-export");
  const [periodStart, setPeriodStart] = useState("");
  const [coverageStart, setCoverageStart] = useState("");
  const [coverageEnd, setCoverageEnd] = useState("");
  const [assessment, setAssessment] = useState("");
  const [assignmentCount, setAssignmentCount] = useState("");
  const [principalCount, setPrincipalCount] = useState("");
  const [controlEvidence, setControlEvidence] = useState("");
  const [controlReference, setControlReference] = useState("");
  const history = basis === "validity-history";
  const controls =
    history ||
    Boolean(
      assignmentCount || principalCount || controlEvidence || controlReference,
    );
  return (
    <details>
      <summary>Import an ERP permission population</summary>
      <form
        className="grc-editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (!file) return;
          const body = new FormData();
          body.append("file", file);
          body.append(
            "metadata",
            JSON.stringify({
              reference,
              title,
              body: {
                system,
                rule_id: rule,
                as_of: asOf,
                source_evidence_id: evidence,
                population_basis: basis,
                ...(history
                  ? {
                      ...(periodStart ? { period_start: periodStart } : {}),
                      coverage_start: coverageStart,
                      coverage_end: coverageEnd,
                      history_scope_assessment: assessment,
                    }
                  : {}),
                ...(controls
                  ? {
                      expected_assignment_count: Number(assignmentCount),
                      expected_principal_count: Number(principalCount),
                      population_control_evidence_id: controlEvidence,
                      population_control_reference: controlReference,
                    }
                  : {}),
              },
            }),
          );
          action.mutate({ path: `${base}/sod/import`, body });
        }}
      >
        <p>
          CSV columns: principal, permission, scope, valid_from, optional
          valid_to. Maximum 4 MiB and 10,000 assignments. The file must match
          its clean, independently approved evidence version.
        </p>
        <label>
          Access population reference
          <input
            required
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
        <label>
          Access population title
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          ERP system
          <input
            required
            value={system}
            onChange={(e) => setSystem(e.target.value)}
          />
        </label>
        <label>
          Approved SoD rule reference
          <input
            required
            value={rule}
            onChange={(e) => setRule(e.target.value)}
          />
        </label>
        <label>
          Assessment date
          <input
            required
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <label>
          Approved CSV evidence reference
          <input
            required
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
          />
        </label>
        <label>
          Population basis
          <select value={basis} onChange={(e) => setBasis(e.target.value)}>
            <option value="point-in-time-export">Point-in-time export</option>
            <option value="validity-history">
              Grant and revocation history
            </option>
          </select>
        </label>
        <p>
          Dates are inclusive calendar dates. A current export cannot establish
          historical completeness. Roles, wildcard scopes and scope hierarchies
          are not inferred. Period analysis requires a policy effective
          throughout the requested period. Reviewed scope overlaps require
          separate population controls below.
        </p>
        {history && (
          <>
            <label>
              Analysis period start (optional; otherwise assessment date)
              <input
                type="date"
                value={periodStart}
                max={asOf || undefined}
                onChange={(e) => setPeriodStart(e.target.value)}
              />
            </label>
            <label>
              Verified history coverage start
              <input
                required
                type="date"
                value={coverageStart}
                onChange={(e) => setCoverageStart(e.target.value)}
              />
            </label>
            <label>
              Verified history coverage end
              <input
                required
                type="date"
                value={coverageEnd}
                onChange={(e) => setCoverageEnd(e.target.value)}
              />
            </label>
            <label>
              History population scope assessment
              <textarea
                required
                minLength={10}
                maxLength={4000}
                value={assessment}
                onChange={(e) => setAssessment(e.target.value)}
              />
            </label>
          </>
        )}
        <fieldset>
          <legend>Independent population controls</legend>
          <p>
            Use counts checked against a separate approved control record. These
            declarations do not automatically prove source completeness. Enter
            approved record IDs for evidence references.
          </p>
          <label>
            Expected assignment count
            <input
              type="number"
              min={1}
              max={10000}
              step={1}
              required={controls}
              value={assignmentCount}
              onChange={(e) => setAssignmentCount(e.target.value)}
            />
          </label>
          <label>
            Expected principal count
            <input
              type="number"
              min={1}
              max={10000}
              step={1}
              required={controls}
              value={principalCount}
              onChange={(e) => setPrincipalCount(e.target.value)}
            />
          </label>
          <label>
            Approved population control evidence reference
            <input
              required={controls}
              value={controlEvidence}
              onChange={(e) => setControlEvidence(e.target.value)}
            />
          </label>
          <label>
            Population control memo reference
            <input
              required={controls}
              minLength={10}
              maxLength={4000}
              value={controlReference}
              onChange={(e) => setControlReference(e.target.value)}
            />
          </label>
        </fieldset>
        <label>
          ERP access CSV
          <input
            required
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </label>
        <Button primary disabled={!file || action.isPending}>
          Import for review
        </Button>
        {action.data && (
          <p>
            Imported {String(action.data.reference)} ·{" "}
            {String(action.data.status)}. Independent approval remains required.
          </p>
        )}
        {action.error && <ErrorState error={action.error} />}
      </form>
    </details>
  );
}

export function MLFeedback({
  inference,
  transaction,
}: {
  inference: unknown;
  transaction: string;
}) {
  const allowed = useCan("ml.feedback");
  const action = useAction();
  const [label, setLabel] = useState("insufficient_evidence");
  const [evidence, setEvidence] = useState("");
  const [rationale, setRationale] = useState("");
  if (!allowed || typeof inference !== "string") return null;
  return (
    <details>
      <summary>Record evidence-backed model feedback</summary>
      <label>
        Reviewer label
        <select value={label} onChange={(e) => setLabel(e.target.value)}>
          {[
            "false_positive",
            "valid_exception",
            "confirmed_misstatement",
            "insufficient_evidence",
            "no_issue",
          ].map((x) => (
            <option key={x} value={x}>
              {x.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
      <label>
        Approved evidence reference
        <input value={evidence} onChange={(e) => setEvidence(e.target.value)} />
      </label>
      <label>
        Feedback rationale
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
      </label>
      <Button
        disabled={!evidence || rationale.length < 20 || action.isPending}
        onClick={() =>
          action.mutate({
            path: `ml/predictions/${inference}/feedback`,
            body: {
              transaction_id: transaction,
              label,
              evidence_id: evidence,
              rationale,
            },
          })
        }
      >
        Record reviewer feedback
      </Button>
      <p>
        Feedback requires separate curation. Monitoring holdout rows remain
        outside training.
      </p>
      {action.error && <ErrorState error={action.error} />}
    </details>
  );
}

export function BoardDownloads({
  eid,
  identifier,
}: {
  eid: string;
  identifier: string;
}) {
  const tenant = useScope((s) => s.tenant);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function download(format: string) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/grc/engagements/${eid}/board/packages/${identifier}/export/${format}`,
        { headers: { "X-Tenant-ID": tenant }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          "Package unavailable; verify audience, source approval and validity.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `governance-${identifier}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <div className="grc-toolbar">
        <Button disabled={busy} onClick={() => download("pdf")}>
          Download reviewed PDF
        </Button>
        <Button disabled={busy} onClick={() => download("docx")}>
          Download reviewed Word report
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

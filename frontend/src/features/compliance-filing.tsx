"use client";

import { useState } from "react";
import { useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import type { Paper } from "./grc-forms";

export type FilingVerification =
  | { state: "pending" | "unavailable" }
  | {
      state: "known";
      freshness: string;
      calendar_state: string;
      reassessment_required: boolean;
    };

const stages = [
  "not_started",
  "preparing",
  "under_review",
  "approved_for_submission",
  "submitted",
  "acknowledged",
];

export function ComplianceFiling({
  base,
  paper,
  canManage = true,
  canApprove = true,
  verification,
}: {
  base: string;
  paper: Paper;
  canManage?: boolean;
  canApprove?: boolean;
  verification?: FilingVerification;
}) {
  const current = String(paper.body.filing_stage || "not_started");
  const next = stages[Math.min(stages.indexOf(current) + 1, stages.length - 1)];
  const [stage, setStage] = useState(next);
  const [receipt, setReceipt] = useState("");
  const action = useAction();
  const receiptRequired = stage === "submitted" || stage === "acknowledged";
  const locked = paper.status === "LOCKED";
  const verificationBlocked =
    verification &&
    (verification.state !== "known" ||
      verification.freshness !== "CURRENT" ||
      verification.reassessment_required);
  const countryScope =
    paper.body.jurisdiction_scope &&
    typeof paper.body.jurisdiction_scope === "object" &&
    !Array.isArray(paper.body.jurisdiction_scope)
      ? (paper.body.jurisdiction_scope as Record<string, unknown>)
      : null;
  const scopePending =
    countryScope &&
    countryScope.applicability !== "assessed_applicable" &&
    ["approved_for_submission", "submitted", "acknowledged"].includes(stage);
  const deadlineRule =
    paper.body.deadline_rule && typeof paper.body.deadline_rule === "object"
      ? (paper.body.deadline_rule as Record<string, unknown>)
      : null;
  const businessCalendar =
    deadlineRule?.day_count_basis === "business" &&
    deadlineRule.business_calendar &&
    typeof deadlineRule.business_calendar === "object" &&
    !Array.isArray(deadlineRule.business_calendar)
      ? (deadlineRule.business_calendar as Record<string, unknown>)
      : null;
  const periodMissing = Boolean(
    countryScope &&
    [
      deadlineRule,
      ...(Array.isArray(deadlineRule?.later_of) ? deadlineRule.later_of : []),
    ].some((candidate) => candidate?.date_basis === "period_end") &&
    (!paper.body.obligation_period_start || !paper.body.obligation_period_end),
  );
  const permitted =
    stage === "approved_for_submission" ? canApprove : canManage;
  const validReceipt =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      receipt,
    );
  return (
    <section aria-label="Filing readiness">
      <h3>Filing readiness</h3>
      <p>
        {paper.reference} · version {paper.version} ·{" "}
        {current.replaceAll("_", " ")}
      </p>
      <p>
        Deadline:{" "}
        {String(
          paper.body.extension_deadline || paper.body.deadline || "Unresolved",
        )}
        . Record an evidenced human decision; this does not submit to an
        authority.
      </p>
      {Array.isArray(deadlineRule?.later_of) &&
        deadlineRule.later_of.length > 0 && (
          <section aria-label="Later-of deadline comparison">
            <h4>Later-of deadline comparison</h4>
            <p>
              The calculation selects the latest calendar date from these
              triggers, then applies the retained date-rolling convention.
              Entity facts and legal applicability require independent review.
            </p>
            <p>
              Rule evidence:{" "}
              {String(paper.body.rule_evidence_id ?? "Not supplied")}. Timezone:{" "}
              {String(deadlineRule.timezone ?? "Not supplied")}.
            </p>
            <div style={{ overflowX: "auto" }}>
              <table aria-label="Deadline triggering events">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Date basis</th>
                    <th>Trigger</th>
                    <th>Months after</th>
                    <th>Days after</th>
                  </tr>
                </thead>
                <tbody>
                  {[deadlineRule, ...deadlineRule.later_of].map(
                    (candidate, index) => (
                      <tr key={index}>
                        <td>
                          {String(candidate?.identifier ?? "Not supplied")}
                        </td>
                        <td>
                          {String(candidate?.date_basis ?? "Not supplied")}
                        </td>
                        <td>{String(candidate?.trigger ?? "Not supplied")}</td>
                        <td>{String(candidate?.months_after ?? 0)}</td>
                        <td>{String(candidate?.days_after ?? 0)}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      <p>
        Jurisdiction: {String(paper.body.jurisdiction || "Not recorded")}.
        Changes to approved country scope, obligation criteria or existing
        receipts require a return to preparing and independent reassessment.
      </p>
      {deadlineRule?.day_count_basis === "business" && (
        <section aria-label="Business-day deadline basis">
          <h4>Business-day deadline basis</h4>
          <p>
            Count {String(deadlineRule.days_after ?? "Not supplied")} working
            days from {String(deadlineRule.trigger ?? "Not supplied")}. Trigger
            treatment:{" "}
            {deadlineRule.business_trigger_policy === "exclude"
              ? "exclude the triggering day"
              : deadlineRule.business_trigger_policy === "include_if_working"
                ? "include the triggering day only if it is a working day"
                : "not supplied"}
            . Timezone: {String(deadlineRule.timezone ?? "Not supplied")}.
          </p>
          <p>
            Assessed calendar coverage:{" "}
            {String(businessCalendar?.coverage_start ?? "Not supplied")} to{" "}
            {String(businessCalendar?.coverage_end ?? "Not supplied")}.
            Independently counted holidays:{" "}
            {String(
              businessCalendar?.independent_holiday_count ?? "Not supplied",
            )}
            .
          </p>
          <p>
            Excluded weekdays:{" "}
            {Array.isArray(businessCalendar?.weekend_days)
              ? businessCalendar.weekend_days
                  .map(
                    (day) =>
                      [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                      ][Number(day)] ?? "Invalid weekday",
                  )
                  .join(", ")
              : "Not supplied"}
            . Declared holidays:{" "}
            {Array.isArray(businessCalendar?.holidays)
              ? businessCalendar.holidays.length
                ? businessCalendar.holidays.map(String).join(", ")
                : businessCalendar.independent_holiday_count === 0
                  ? "Explicitly none"
                  : "Empty list without an independent zero control"
              : "Not supplied"}
            .
          </p>
          <p>
            Calendar evidence:{" "}
            {String(paper.body.calendar_evidence_id ?? "Not supplied")}.{" "}
            {String(
              businessCalendar?.assessment ??
                "Calendar assessment not supplied",
            )}
            . This counts the assessed calendar; it does not verify national
            holidays or legal applicability.
          </p>
        </section>
      )}
      {countryScope && (
        <p>
          Declared entity country: {String(countryScope.entity_country)} ·
          Obligation country: {String(countryScope.obligation_country)} ·{" "}
          {String(countryScope.relationship)} · Applicability:{" "}
          {String(countryScope.applicability).replaceAll("_", " ")}. This
          assessment does not change the entity country or activate a foreign
          tax engine.
        </p>
      )}
      {Boolean(
        countryScope ||
        paper.body.obligation_period_start ||
        paper.body.obligation_period_end,
      ) && (
        <p>
          Obligation period:{" "}
          {paper.body.obligation_period_start &&
          paper.body.obligation_period_end
            ? `${String(paper.body.obligation_period_start)} to ${String(paper.body.obligation_period_end)}`
            : "Not specified"}
          . This period is separate from the engagement financial period.
        </p>
      )}
      {periodMissing && (
        <p role="status">
          Record the explicit obligation period and return to preparing for
          reassessment.
        </p>
      )}
      {scopePending && (
        <p role="status">
          Assess country applicability before approving or recording submission.
        </p>
      )}
      {Boolean(
        paper.body.submission_evidence_id ||
        paper.body.acknowledgment_evidence_id,
      ) && (
        <dl aria-label="Retained filing receipts">
          <dt>Recorded submission evidence</dt>
          <dd>{String(paper.body.submission_evidence_id || "Not recorded")}</dd>
          <dt>Recorded acknowledgment evidence</dt>
          <dd>
            {String(paper.body.acknowledgment_evidence_id || "Not recorded")}
          </dd>
        </dl>
      )}
      {locked && (
        <p role="status">
          Reopen the locked record before changing its filing stage.
        </p>
      )}
      {!permitted && (
        <p role="status">
          {stage === "approved_for_submission"
            ? "A user with filing approval permission must record this stage."
            : "A user with filing management permission must record this stage."}
        </p>
      )}
      {verification?.state === "pending" && (
        <p role="status">Checking current obligation sources…</p>
      )}
      {verification?.state === "unavailable" && (
        <p role="status">
          Current obligation sources could not be verified. Reload the record
          before recording a filing stage.
        </p>
      )}
      {verification?.state === "known" && (
        <p role="status">
          Source freshness: {verification.freshness} · Calendar:{" "}
          {verification.calendar_state.replaceAll("_", " ")}.
          {verificationBlocked &&
            " Reassessment required before recording a filing stage."}
        </p>
      )}
      <label>
        Next filing stage
        <select
          value={stage}
          disabled={locked || action.isPending}
          onChange={(e) => {
            setStage(e.target.value);
            setReceipt("");
          }}
        >
          {[...new Set([next, "preparing"])].map((value) => (
            <option key={value} value={value}>
              {value.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
      {receiptRequired && (
        <label>
          {stage === "submitted"
            ? "Actual submission evidence record ID"
            : "Separate acknowledgment evidence record ID"}
          <input value={receipt} onChange={(e) => setReceipt(e.target.value)} />
        </label>
      )}
      <p>
        Approval for submission requires the designated independent reviewer and
        current approved readiness evidence. Generated returns and exports do
        not establish submission.
      </p>
      <Button
        disabled={
          action.isPending ||
          locked ||
          Boolean(verificationBlocked) ||
          Boolean(scopePending) ||
          periodMissing ||
          !permitted ||
          stage === current ||
          (receiptRequired && !validReceipt)
        }
        onClick={() =>
          action.mutate({
            path: `${base}/obligations/${paper.id}/filing-stage`,
            body: {
              version: paper.version,
              stage,
              ...(receiptRequired
                ? {
                    [stage === "submitted"
                      ? "submission_evidence_id"
                      : "acknowledgment_evidence_id"]: receipt,
                  }
                : {}),
            },
          })
        }
      >
        Record evidenced filing stage
      </Button>
      <ErrorState error={action.error} />
    </section>
  );
}

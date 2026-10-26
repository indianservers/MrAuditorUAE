"use client";
import {
  RetainedEvidenceDocuments,
  type RetainedEvidenceDocument,
} from "./retained-evidence-documents";

export function MediaMentionAssessments({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  const mentions = rows.filter((row) => row.kind === "media-mention");
  if (!mentions.length) return null;
  return (
    <section aria-label="Retained media assessments">
      <h3>Article identity and risk assessments on this page</h3>
      {mentions.map((row) => (
        <details
          key={String(row.id)}
          style={{ margin: "12px 0", overflowWrap: "anywhere" }}
        >
          <summary>
            {String(row.article_id)} · {String(row.identity_status)} ·{" "}
            {String(row.risk)} · {String(row.disposition)}
          </summary>
          <p>
            {String(row.title)} — {String(row.publisher)}
          </p>
          <p>Reference: {String(row.url)}</p>
          <p>
            Reported stage: {String(row.reported_stage)}. Publication:{" "}
            {String(row.published_on ?? "Unknown")}. Retrieved:{" "}
            {String(row.retrieved_on)}. Reviewed: {String(row.reviewed_on)}.
          </p>
          <p>Identity rationale: {String(row.identity_rationale)}</p>
          <p>Risk rationale: {String(row.risk_rationale)}</p>
          <p>
            Subject: {String(row.subject_id ?? "Unknown")}. Search:{" "}
            {String(row.search_id)}. Follow-up:{" "}
            {String(row.followup_on ?? "Not recorded")}.
          </p>
          <p>
            Article file version: {String(row.source_evidence_version_id)} ·
            SHA-256: {String(row.source_sha256)}
          </p>
          <p>
            Identity file version:{" "}
            {String(row.identity_evidence_version_id ?? "Not recorded")} ·
            SHA-256: {String(row.identity_source_sha256 ?? "Not recorded")}
          </p>
        </details>
      ))}
    </section>
  );
}

export type MediaScope = {
  country: string;
  coverage_from: string;
  coverage_through: string;
  maximum_query_age_days: number;
  expected_subjects: number;
  assessment: string;
};
export function AdverseMediaEvidence({
  eid,
  tenant,
  documents,
  scope,
}: {
  eid: string;
  tenant: string;
  documents: RetainedEvidenceDocument[];
  scope?: MediaScope;
}) {
  return (
    <section aria-label="Adverse-media review scope">
      <h3>Adverse-media search and identity review</h3>
      {scope && (
        <>
          <p>
            {scope.country} · Declared coverage {scope.coverage_from} through{" "}
            {scope.coverage_through} · {scope.expected_subjects} subjects ·
            Maximum query age {scope.maximum_query_age_days} days
          </p>
          <p>{scope.assessment}</p>
        </>
      )}
      <p>
        No mentions is not clearance. Unavailable, partial, stale or incomplete
        searches and unresolved identities block approval. Name similarity
        cannot establish identity.
      </p>
      <p>
        Reported allegations, charges, convictions and retractions are source
        descriptions requiring human assessment. This review does not
        authenticate legal facts, authorize onboarding or automatically reject a
        subject.
      </p>
      <p>
        Follow-up dates are recorded for review; automatic monitoring is off.
      </p>
      <RetainedEvidenceDocuments
        eid={eid}
        tenant={tenant}
        documents={documents}
        summary="Retained search, article, identity and policy evidence"
        label="media"
      />
    </section>
  );
}

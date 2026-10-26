"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";

export function ScreeningCandidates({
  rows,
}: {
  rows: Record<string, unknown>[];
}) {
  const [subjectIndex, setSubjectIndex] = useState(0);
  const [offset, setOffset] = useState(0);
  const subject = rows[subjectIndex];
  if (!subject) return null;
  const candidates = Array.isArray(subject.candidates)
    ? (subject.candidates as Record<string, unknown>[])
    : [];
  const page = candidates.slice(offset, offset + 100);
  const fields = [
    "source_id",
    "list_subject_id",
    "list_name",
    "list_version",
    "published_on",
    "evidence_reference",
    "name_similarity",
  ];
  return (
    <section aria-label="Screening candidate review">
      <h3>Review name-screening candidates</h3>
      <p>
        Every candidate needs independent adjudication. Name similarity is a
        baseline score, not a probability or sanctions clearance. Select a
        subject from this schedule page; use the schedule pages to reach other
        subjects.
      </p>
      <label>
        Screening subject
        <select
          value={subjectIndex}
          onChange={(event) => {
            setSubjectIndex(Number(event.target.value));
            setOffset(0);
          }}
        >
          {rows.map((row, index) => (
            <option key={String(row.id)} value={index}>
              {String(row.id)} ·{" "}
              {String(row.subject_name ?? "Name not retained")}
            </option>
          ))}
        </select>
      </label>
      <p>
        Subject evidence reference:{" "}
        {String(
          subject.subject_evidence_reference ??
            "Not retained in this historical result",
        )}
      </p>
      {(subject.candidate_preview_truncated === true ||
        (subject.candidate_count !== undefined &&
          subject.candidate_count !== candidates.length)) && (
        <p role="alert">
          This historical result retained only {candidates.length} of{" "}
          {String(subject.candidate_count)} candidates. Rerun against current
          reviewed evidence before relying on complete candidate coverage.
        </p>
      )}
      <p>
        {candidates.length
          ? `Candidates ${offset + 1}–${offset + page.length} of ${candidates.length}`
          : "No retained candidates. This does not clear the subject."}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table aria-label="Name-screening candidates">
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field} scope="col">
                  {field.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.map((candidate, index) => (
              <tr key={`${candidate.source_id}:${offset + index}`}>
                {fields.map((field) => (
                  <td key={field}>
                    {String(candidate[field] ?? "Not retained")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar" aria-label="Screening candidate pages">
        <Button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Previous candidates
        </Button>
        <Button
          disabled={offset + page.length >= candidates.length}
          onClick={() => setOffset(offset + 100)}
        >
          Next candidates
        </Button>
      </div>
      <p>
        Use the subject row disposition to document the assessment of all its
        candidates. XLSX includes a separate Screening candidates sheet.
      </p>
    </section>
  );
}

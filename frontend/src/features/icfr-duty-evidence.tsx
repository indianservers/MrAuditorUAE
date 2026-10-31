"use client";

import {
  RetainedEvidenceDocuments,
  type RetainedEvidenceDocument,
} from "./retained-evidence-documents";

export function ICFRDutyEvidence({
  eid,
  tenant,
  documents,
  binding,
}: {
  eid: string;
  tenant: string;
  documents: RetainedEvidenceDocument[];
  binding?: string;
}) {
  return (
    <section aria-label="ICFR duty scope and evidence">
      <h3>Separate management and auditor scope</h3>
      <p>
        Management 404(a) and auditor 404(b) decisions are assessed separately
        for each declared subject and reporting issuer. Component instructions
        do not establish a separate statutory attestation duty for that
        component.
      </p>
      <p>
        This review covers the declared plan and retained evidence. Legal
        applicability, a complete testing method, control effectiveness and an
        audit opinion need separate professional assessment. India IFC and UAE
        local duties remain separate.
      </p>
      <p>
        {binding === "RETAINED_DOCUMENT_BYTES_VERIFIED"
          ? "Authority and scope-assessment files were checked against retained originals."
          : "Retained authority and scope-assessment checks are incomplete."}
      </p>
      <RetainedEvidenceDocuments
        eid={eid}
        tenant={tenant}
        documents={documents}
        summary="Retained ICFR authority and scope assessments"
        label="ICFR supporting"
      />
    </section>
  );
}

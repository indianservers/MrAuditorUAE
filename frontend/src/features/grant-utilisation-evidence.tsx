"use client";

import {
  RetainedEvidenceDocuments,
  type RetainedEvidenceDocument,
} from "./retained-evidence-documents";

export type GrantDocument = RetainedEvidenceDocument;
export function GrantSourceNotice({ kind }: { kind: string }) {
  return (
    <p role="note">
      {kind === "grant-budgets"
        ? "The file total sums category ceilings for import control. Whole-fund ceilings are tested separately; neither total establishes cash available or permission to spend."
        : kind === "grant-utilisation-controls"
          ? "The file total combines opening balances and period account controls solely to check this file. Business comparisons separate each fund/category opening from each account’s net, gross and row-count controls."
          : kind === "grant-expenses"
            ? "Amounts are signed book expenditure observations. Recognition, capitalisation, source completeness and cash settlement need separate assessment."
            : "Allocations distribute the declared expenditure population. A credit needs a retained original-reference recovery assessment and always remains subject to review."}
    </p>
  );
}
export function GrantUtilisationEvidence({
  eid,
  tenant,
  documents,
  currencies,
  reviewWindow,
}: {
  eid: string;
  tenant: string;
  documents: GrantDocument[];
  currencies?: string[];
  reviewWindow?: { from: string; through: string };
}) {
  return (
    <section aria-label="Grant utilisation scope">
      <h3>Grant expenditure and budget review</h3>
      {reviewWindow && (
        <p>
          {reviewWindow.from} through {reviewWindow.through} ·{" "}
          {(currencies || []).join(", ")}
        </p>
      )}
      <p>
        Opening utilisation plus this period’s signed expenditure is compared
        separately with each category ceiling and the whole fund ceiling.
        Currencies remain separate. Missing opening balances and account
        controls block approval.
      </p>
      <p>
        Remaining amounts describe the signed expenditure schedule. They do not
        establish cash available, donor permission, legal eligibility or a
        utilisation certificate. Credits always require a separate recovery
        review.
      </p>
      <RetainedEvidenceDocuments
        eid={eid}
        tenant={tenant}
        documents={documents}
        summary="Retained grant mandate and recovery evidence"
        label="grant"
      />
    </section>
  );
}

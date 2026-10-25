"use client";

import { Button } from "@/components/ui/primitives";

export type BankAccountLink = {
  status: string;
  review_receipt?: { id: string; version: number; sha256: string };
  account?: string;
  currency?: string;
  original_bank_source_account?: string;
  window_start?: string;
  window_end?: string;
  assessment?: string;
  source_account_binding?: string;
  account_label_mapping_applied?: boolean;
  bank_authentication_status: string;
};
export function BankAccountLinkReview({
  link,
  open,
}: {
  link: BankAccountLink;
  open: (id: string) => void;
}) {
  const receipt = link.review_receipt;
  const linked = link.status === "REVIEWED_ACCOUNT_DOCUMENTS_LINKED";
  const facts: [string, string | undefined][] = [
    ["Selected ledger account", `${link.account} · ${link.currency}`],
    ["Original bank source account", link.original_bank_source_account],
    [
      "Account label mapping",
      link.account_label_mapping_applied
        ? "Applied using the reviewed account number"
        : "No label change",
    ],
    [
      "Evidence scope",
      link.source_account_binding === "DECLARED_LEDGER_ACCOUNT_LABEL_ONLY"
        ? "Canonical source declares the ledger label; a native bank account number was not checked"
        : "Source account number agrees to the reviewed documents",
    ],
    [
      "Covered review window",
      `${link.window_start} through ${link.window_end}`,
    ],
    ["Scope assessment", link.assessment],
  ];
  return (
    <section aria-label="Linked bank account evidence">
      <h3>Bank account evidence link</h3>
      <p>
        {linked
          ? "This result retains the selected account-document review. Check result freshness before relying on it."
          : link.status === "LINK_REQUESTED_NOT_VERIFIED"
            ? "The requested account link has not been verified. Independent approval requires a verified link."
            : "No account-document review is linked. This result compares arithmetic and declared account labels only."}
      </p>
      {linked && (
        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))",
            gap: 16,
          }}
        >
          {facts.map(([label, value]) => (
            <div
              key={label}
              style={{
                minWidth: 0,
                ...(label === "Scope assessment"
                  ? { gridColumn: "1 / -1" }
                  : {}),
              }}
            >
              <dt style={{ fontSize: 12, fontWeight: 600 }}>{label}</dt>
              <dd
                style={{
                  margin: 0,
                  paddingTop: 4,
                  textAlign: "left",
                  overflowWrap: "anywhere",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p>
        Document agreement does not authenticate a bank account, establish
        signing authority or confirm payment execution.
      </p>
      {linked && receipt && (
        <Button onClick={() => open(receipt.id)}>
          Open linked account review
        </Button>
      )}
    </section>
  );
}

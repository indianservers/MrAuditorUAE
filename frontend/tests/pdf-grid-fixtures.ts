import { emptyPDFGrid } from "@/features/pdf-grid-editor";

export function validPDFDraft() {
  const draft = emptyPDFGrid();
  Object.assign(draft, {
    account: "BANK-1",
    currency: "AED",
    amount_basis: "credit-positive",
    scope_assessment:
      "Reviewed synthetic complete row grid and header identity",
  });
  for (const [field, left, right] of [
    ["date", "5", "19"],
    ["reference", "19", "39"],
    ["debit", "39", "54"],
    ["credit", "54", "69"],
    ["counterparty", "69", "96"],
  ] as const)
    draft.columns[field] = { left, right };
  Object.assign(draft.pages[0], {
    top: "11.25",
    row_height: "2.5",
    row_count: "2",
    account_header: { left: "16", right: "28", top: "6.25", bottom: "8.75" },
    currency_header: { left: "45", right: "52", top: "6.25", bottom: "8.75" },
  });
  return draft;
}

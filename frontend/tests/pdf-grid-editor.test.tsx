import { describe, expect, it } from "vitest";
import { buildPDFGrid } from "@/features/pdf-grid-editor";
import { validPDFDraft } from "./pdf-grid-fixtures";

describe("explicit PDF grid", () => {
  it("serializes declared geometry and sign convention without adding unused columns", () => {
    const profile = buildPDFGrid(validPDFDraft());
    expect(profile).toMatchObject({
      account: "BANK-1",
      currency: "AED",
      amount_basis: "credit-positive",
      pages: [{ page: 1, row_count: 2, row_height: 2.5, top: 11.25 }],
    });
    expect(profile.columns).not.toHaveProperty("amount");
    expect(profile.columns).not.toHaveProperty("currency");
    expect(profile.columns.credit).toEqual({ left: 54, right: 69 });
  });
  it.each([
    "blank",
    "overlap",
    "duplicate-page",
    "row-bound",
    "missing-convention",
  ])("rejects %s mappings before queuing", (kind) => {
    const draft = validPDFDraft();
    if (kind === "blank") draft.columns.date.left = "";
    else if (kind === "overlap")
      draft.ignored_columns = [{ left: "0", right: "10" }];
    else if (kind === "duplicate-page")
      draft.pages.push(structuredClone(draft.pages[0]));
    else if (kind === "row-bound") draft.pages[0].row_count = "5000";
    else draft.amount_basis = "";
    expect(() => buildPDFGrid(draft)).toThrow();
  });
});

import { render, screen, within } from "@testing-library/react";
import { it, expect } from "vitest";
import { BankAccountEvidenceReview } from "@/features/bank-account-evidence";

it("keeps three source identities and leading zeros visible without claiming bank authentication", () => {
  const rows = ["register", "ledger", "bank"].map((role) => ({
    source_role: role,
    account: "SYN-BANK",
    account_number: "000123456789",
    owner_identifier: "00123",
    owner_name: "Synthetic Entity",
    assertion_status: "confirmed",
    exceptions: role === "bank" ? ["OWNER_IDENTIFIER_UNRESOLVED"] : [],
    state: role === "bank" ? "EXCEPTIONS" : "MATCHED",
  }));
  render(<BankAccountEvidenceReview rows={rows} />);
  const table = screen.getByRole("table", {
    name: "Bank account identity observations",
  });
  expect(within(table).getAllByText("000123456789")).toHaveLength(3);
  expect(within(table).getAllByText("00123")).toHaveLength(3);
  expect(within(table).getByText("owner identifier unresolved")).toBeVisible();
  expect(screen.getByText(/do not authenticate a bank account/)).toBeVisible();
  expect(
    within(table).getByRole("columnheader", { name: "Retained bank evidence" }),
  ).toBeVisible();
});

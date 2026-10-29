import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { BankAccountLinkReview } from "@/features/bank-account-link";

describe("bank account evidence link", () => {
  it("shows the original number, ledger alias, scope and retained review action", () => {
    const open = vi.fn();
    render(
      <BankAccountLinkReview
        open={open}
        link={{
          status: "REVIEWED_ACCOUNT_DOCUMENTS_LINKED",
          account: "BANK-1",
          currency: "AED",
          original_bank_source_account: "AE070331234567890123456",
          window_start: "2026-06-01",
          window_end: "2026-06-30",
          assessment: "Independent synthetic scope assessment",
          review_as_of: "2026-06-30",
          source_account_binding:
            "NATIVE_ACCOUNT_NUMBER_AGREES_TO_REVIEWED_DOCUMENTS",
          account_label_mapping_applied: true,
          bank_authentication_status: "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
          review_receipt: { id: "review", version: 2, sha256: "a".repeat(64) },
        }}
      />,
    );
    expect(screen.getByText("AE070331234567890123456")).toBeVisible();
    expect(screen.getByText("BANK-1 · AED")).toBeVisible();
    expect(
      screen.getByText("Account comparison date").parentElement,
    ).toHaveTextContent("2026-06-30");
    expect(screen.getByText("2026-06-01 through 2026-06-30")).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Open linked account review" }),
    );
    expect(open).toHaveBeenCalledWith("review");
  });
  it.each(["NOT_LINKED_ARITHMETIC_SCOPE_ONLY", "LINK_REQUESTED_NOT_VERIFIED"])(
    "does not present %s as reviewed bank evidence",
    (status) => {
      render(
        <BankAccountLinkReview
          open={vi.fn()}
          link={{
            status,
            bank_authentication_status:
              "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
          }}
        />,
      );
      expect(
        screen.queryByRole("button", { name: "Open linked account review" }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/does not authenticate a bank account/),
      ).toBeVisible();
    },
  );
});

it("distinguishes the linked annual cutoff from post-year document coverage", () => {
  render(
    <BankAccountLinkReview
      open={vi.fn()}
      link={{
        status: "REVIEWED_ACCOUNT_DOCUMENTS_LINKED",
        review_as_of: "2027-03-31",
        window_start: "2026-03-01",
        window_end: "2027-04-05",
        observation_scope: {
          contract: "bank-account-observation-window/1",
          from: "2026-03-01",
          through: "2027-04-05",
          assessment: "Assessed original and post-year account evidence",
        },
        bank_authentication_status: "NOT_ESTABLISHED_BY_DOCUMENT_COMPARISON",
      }}
    />,
  );
  expect(
    screen.getByText("Financial cutoff of account review").parentElement,
  ).toHaveTextContent("2027-03-31");
  expect(
    screen.getByText("Assessed document coverage").parentElement,
  ).toHaveTextContent("2026-03-01 through 2027-04-05");
});

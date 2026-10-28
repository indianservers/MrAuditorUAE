import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { MerchantSettlementDetails } from "@/features/merchant-settlement-details";

it("keeps missing components distinct from an explicit zero", () => {
  render(
    <MerchantSettlementDetails
      rows={[
        {
          id: "P",
          kind: "MERCHANT_SETTLEMENT",
          batch: "B",
          merchant: "M",
          processor: "PSP",
          currency: "AED",
          fees: "0",
          book_activity_ids: ["SALE-1", "REFUND-2"],
          allocation_ids: ["LINK-1"],
          book_differences: { sales: "0", refunds: "-1", chargebacks: "0" },
        },
      ]}
    />,
  );
  fireEvent.click(screen.getByText("Batch B · M · PSP · AED"));
  const fees = screen.getByText("Less processor fees").closest("tr")!;
  const tax = screen.getByText("Less assessed fee tax").closest("tr")!;
  expect(within(fees).getByText("0")).toBeVisible();
  expect(within(tax).getByText("Not supplied")).toBeVisible();
  expect(screen.getByText(/SALE-1, REFUND-2/)).toBeVisible();
  expect(screen.getByText(/Bank allocation rows: LINK-1/)).toBeVisible();
  expect(screen.getByText("-1")).toBeVisible();
});

it("identifies the original unallocated bank movement with its signed residual", () => {
  render(
    <MerchantSettlementDetails
      rows={[
        {
          id: "R",
          kind: "BANK_RESIDUAL",
          bank_transaction_id: "ORIGINAL-BANK-ROW",
          currency: "INR",
          amount: "-20.25",
        },
      ]}
    />,
  );
  expect(
    screen.getByText(
      "Unallocated bank movement ORIGINAL-BANK-ROW: INR -20.25.",
    ),
  ).toBeVisible();
});

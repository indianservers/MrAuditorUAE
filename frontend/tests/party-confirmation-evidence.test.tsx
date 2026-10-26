import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PartyConfirmationEvidence } from "@/features/party-confirmation-evidence";

function position(party: string, count = 3) {
  return {
    id: party,
    account: "AR",
    counterparty: party,
    side: "receivable",
    currency: "AED",
    open_item_source_ids: Array.from(
      { length: count },
      (_, index) => `${party}-ITEM-${index}`,
    ),
    confirmation_evidence: {
      scope_assessment:
        "SYNTHETIC positive party balance scope, contact and direct receipt assessment",
      status: "received",
      requested_on: "2026-07-01",
      responded_on: "2026-07-05",
      contact_verified: true,
      independently_received: true,
      request_reference: "SYN-REQUEST-PAGE-1",
      request_evidence_version_id: "REQUEST-1",
      request_source_sha256: "a".repeat(64),
      response_reference: "SYN-RESPONSE-PAGE-2",
      response_evidence_version_id: "RESPONSE-1",
      response_source_sha256: "b".repeat(64),
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("positive party confirmation evidence", () => {
  it("pages all linked item IDs and resets the item page when party changes", () => {
    render(
      <PartyConfirmationEvidence
        eid="eng"
        tenant="tenant"
        rows={[position("PARTY-1", 121), position("PARTY-2", 1)]}
        dependencies={[]}
      />,
    );
    fireEvent.click(
      screen.getByText("Request, response and follow-up evidence"),
    );
    expect(screen.getByText("2026-07-05")).toBeVisible();
    fireEvent.click(screen.getByText("Linked open items · 121"));
    expect(screen.getByText("PARTY-1-ITEM-0")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next item links" }));
    expect(screen.getByText("PARTY-1-ITEM-120")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next item links" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Party evidence position"), {
      target: { value: "1" },
    });
    expect(screen.getByText("PARTY-2-ITEM-0")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Previous item links" }),
    ).toBeDisabled();
  });

  it("requires a matching retained hash receipt for download and surfaces permission failures", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal("fetch", fetcher);
    render(
      <PartyConfirmationEvidence
        eid="eng"
        tenant="tenant"
        rows={[position("PARTY-1")]}
        dependencies={[
          {
            type: "evidence",
            id: "REQUEST-1",
            record_id: "REQ-RECORD",
            sha256: "a".repeat(64),
          },
          {
            type: "evidence",
            id: "RESPONSE-1",
            record_id: "RESP-RECORD",
            sha256: "c".repeat(64),
          },
        ]}
      />,
    );
    fireEvent.click(
      screen.getByText("Request, response and follow-up evidence"),
    );
    expect(
      screen.getByRole("button", { name: "Download response evidence" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Download request evidence" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Retained document download denied or unavailable",
      ),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/backend/engagements/eng/audit/evidence-files/REQ-RECORD/REQUEST-1/download",
      { headers: { "X-Tenant-ID": "tenant" } },
    );
  });
});

it("keeps blank request amounts absent and exposes partial reply membership", () => {
  const row = {
    ...position("PARTIAL"),
    confirmation_status: "partially-received",
    covered_item_source_ids: ["PARTIAL-ITEM-0"],
    uncovered_item_source_ids: ["PARTIAL-ITEM-1", "PARTIAL-ITEM-2"],
    covered_book_balance: "100",
    uncovered_book_balance: "50",
    covered_response_difference: "0",
  };
  Object.assign(row.confirmation_evidence, {
    request_basis: "blank-positive",
    requested_amount: null,
    scope_balance: "150",
  });
  render(
    <PartyConfirmationEvidence
      eid="eng"
      tenant="tenant"
      rows={[row]}
      dependencies={[]}
    />,
  );
  fireEvent.click(screen.getByText("Request, response and follow-up evidence"));
  expect(screen.getByText("Intentionally blank")).toBeVisible();
  fireEvent.click(screen.getByText("Linked open items · 3"));
  fireEvent.change(screen.getByLabelText("Linked item scope"), {
    target: { value: "uncovered" },
  });
  expect(screen.queryByText("PARTIAL-ITEM-0")).not.toBeInTheDocument();
  expect(screen.getByText("PARTIAL-ITEM-2")).toBeVisible();
  expect(screen.getByText(/full balance has not been confirmed/)).toBeVisible();
});

it("does not invent membership for an unmapped partial reply", () => {
  const row = {
    ...position("UNMAPPED"),
    confirmation_status: "partially-received",
  };
  render(
    <PartyConfirmationEvidence
      eid="eng"
      tenant="tenant"
      rows={[row]}
      dependencies={[]}
    />,
  );
  fireEvent.click(screen.getByText("Request, response and follow-up evidence"));
  fireEvent.click(screen.getByText("Linked open items · 3"));
  fireEvent.change(screen.getByLabelText("Linked item scope"), {
    target: { value: "covered" },
  });
  expect(
    screen.getByText(/Partial reply item membership is unknown/),
  ).toBeVisible();
});

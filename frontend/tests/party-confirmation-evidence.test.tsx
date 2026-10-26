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

"use client";

import Link from "next/link";
import { useState } from "react";
import { useAction, useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";

type CashStatus = {
  state: string;
  claim_count: number | null;
  approval_error: string | null;
  related_reviews: {
    id: string;
    root_id: string;
    engagement_id?: string;
    title: string;
  }[];
};

export function BankCashReview({
  eid,
  eventId,
  version,
  onSelected,
}: {
  eid: string;
  eventId: string;
  version: number;
  onSelected: (id: string) => void;
}) {
  const prefix = `intelligence/engagements/${eid}/events/${eventId}`;
  const status = useAPI<CashStatus>(`${prefix}/bank-cash-status`, true, true);
  const action = useAction<{ id: string }>();
  const [reason, setReason] = useState("");
  return (
    <section aria-label="Shared bank cash approval controls">
      <h3>Shared bank cash approval controls</h3>
      <p>
        Approval checks bank capacity against active obligation allocation
        reviews across this legal entity’s engagements in the current firm.
        Calculations do not reserve cash. Stale approvals hold their claims
        until explicitly withdrawn. BRS evidence can support the same payment
        separately; this control does not post payments.
      </p>
      {status.error && <ErrorState error={status.error} />}
      {!status.data && !status.error && (
        <p>Checking approved bank cash claims…</p>
      )}
      {status.data && (
        <>
          <p>
            Cash claim: {status.data.state}. Allocated movements:{" "}
            {status.data.claim_count ?? "Unverifiable"}.
          </p>
          {status.data.approval_error && (
            <p role="alert">Approval blocked: {status.data.approval_error}</p>
          )}
          {status.data.related_reviews.map((review) =>
            review.engagement_id && review.engagement_id !== eid ? (
              <Link
                className="button"
                key={review.id}
                href={`/intelligence/${review.engagement_id}/country-workflow?event=${review.id}`}
              >
                Open related engagement allocation: {review.title}
              </Link>
            ) : (
              <Button key={review.id} onClick={() => onSelected(review.id)}>
                Open related allocation review: {review.title}
              </Button>
            ),
          )}
          {status.data.state === "ACTIVE_APPROVED_ALLOCATION" && (
            <>
              <label>
                Bank cash withdrawal reason
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
              <p>
                An independent reviewer must document the withdrawal. Historical
                approval and source values remain retained.
              </p>
              <Button
                disabled={action.isPending || reason.trim().length < 10}
                onClick={async () => {
                  const result = await action
                    .mutateAsync({
                      path: `${prefix}/withdraw-bank-cash`,
                      body: {
                        action: "reject",
                        expected_version: version,
                        comments: reason.trim(),
                      },
                    })
                    .catch(() => null);
                  if (result) onSelected(result.id);
                }}
              >
                Withdraw bank cash claim
              </Button>
            </>
          )}
        </>
      )}
      {action.error && <ErrorState error={action.error} />}
      <p>
        Edited bank fields and unlinked account aliases require separate
        assessment. This control covers one legal entity in the current firm;
        separate entities and firms do not share capacity.
      </p>
    </section>
  );
}

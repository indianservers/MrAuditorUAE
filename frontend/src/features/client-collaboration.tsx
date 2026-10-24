"use client";
import { useState } from "react";
import { useAPI, useAction, useCan } from "@/hooks/use-api";
import type { Page, RecordRow } from "@/types/models";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { PageHeader } from "./shared";
type LinkRow = {
  id: string;
  request_id: string;
  expires_at: string;
  revoked: boolean;
  responses: number;
  uploads: number;
};
export function ClientCollaboration() {
  const [eid, setEid] = useState("");
  const [rid, setRid] = useState("");
  const [retention, setRetention] = useState("");
  const [expiry, setExpiry] = useState("1440");
  const [secret, setSecret] = useState("");
  const [lid, setLid] = useState("");
  const [comments, setComments] = useState("");
  const canManage = useCan("engagement.assign");
  const canUpload = useCan("audit.evidence.upload");
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const workspace = useAPI<{
    policy: {
      quality_review_required: boolean;
      review_chain: string[];
      methodology: Record<string, unknown>;
    };
  }>(`engagements/${eid}/audit/workspace`, !!eid);
  const requests = useAPI<{ items: RecordRow[] }>(
    `engagements/${eid}/audit/requests?limit=100`,
    !!eid,
  );
  const links = useAPI<{ items: LinkRow[] }>(
    `collaboration/engagements/${eid}/links`,
    !!eid,
  );
  const responses = useAPI<{
    items: {
      id: string;
      kind: string;
      body: {
        response?: string;
        claimed_name?: string;
        identity_verified: boolean;
        request_id: string;
        scan_status?: string;
        evidence_id?: string;
      };
    }[];
  }>(
    `collaboration/engagements/${eid}/links/${lid}/submissions`,
    !!eid && !!lid,
  );
  const action = useAction<RecordRow>();
  const allowed =
    workspace.data?.policy.methodology.allow_account_free_portal === true;
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Client collaboration"
        title="Request-scoped Client Responses"
        description="Issue a bounded, expiring link for one request. Guests receive no engagement browsing or internal audit notes."
      />
      <div className="toolbar" style={{ padding: 16 }}>
        <label>
          Engagement
          <select
            value={eid}
            onChange={(e) => {
              setEid(e.target.value);
              setRid("");
              setLid("");
              setSecret("");
            }}
          >
            <option value="">Select engagement</option>
            {engagements.data?.items.map((e) => (
              <option key={e.id} value={e.id}>
                {String(e.name)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorState
        error={
          engagements.error ||
          workspace.error ||
          requests.error ||
          links.error ||
          responses.error ||
          action.error
        }
      />
      {eid && (
        <>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Firm engagement policy</h2>
            <Status value={allowed ? "enabled" : "disabled"} />
            <p>
              Account-free access is disabled by default. Configure the
              engagement policy before acceptance. Existing review requirements
              are preserved.
            </p>
            {canManage && workspace.data && (
              <Button
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({
                    path: `engagements/${eid}/audit/policy`,
                    body: {
                      quality_review_required:
                        workspace.data!.policy.quality_review_required,
                      review_chain: workspace.data!.policy.review_chain,
                      methodology: {
                        ...workspace.data!.policy.methodology,
                        allow_account_free_portal: !allowed,
                      },
                    },
                  })
                }
              >
                {allowed
                  ? "Disable account-free collaboration policy"
                  : "Enable account-free collaboration policy"}
              </Button>
            )}
            <label>
              Client document request
              <select value={rid} onChange={(e) => setRid(e.target.value)}>
                <option value="">Select exact request</option>
                {requests.data?.items.map((r) => (
                  <option key={r.id} value={r.id}>
                    {String(r.reference)} • {String(r.title)} •{" "}
                    {String(r.status)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Link lifetime
              <select
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
              >
                <option value="60">1 hour</option>
                <option value="1440">24 hours</option>
                <option value="10080">7 days</option>
              </select>
            </label>
            <label>
              Retain uploaded evidence until (firm-selected date)
              <input
                type="date"
                value={retention}
                onChange={(e) => setRetention(e.target.value)}
              />
            </label>
            <Button
              disabled={
                action.isPending || !canUpload || !allowed || !rid || !retention
              }
              onClick={async () => {
                const created = await action
                  .mutateAsync({
                    path: `collaboration/engagements/${eid}/links`,
                    body: {
                      request_id: rid,
                      expires_minutes: Number(expiry),
                      retain_until: retention,
                    },
                  })
                  .catch(() => null);
                if (created && typeof created.share_path === "string")
                  setSecret(window.location.origin + created.share_path);
              }}
            >
              Issue secure request link
            </Button>
            {secret && (
              <div>
                <label>
                  Secure link (shown once)
                  <input
                    type="password"
                    readOnly
                    value={secret}
                    autoComplete="off"
                  />
                </label>
                <Button onClick={() => navigator.clipboard.writeText(secret)}>
                  Copy secure link
                </Button>
                <Button onClick={() => setSecret("")}>Dismiss secret</Button>
                <p>
                  The token is stored as a hash. Links are shared manually;
                  issuing one sends no message.
                </p>
              </div>
            )}
          </section>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Issued links and live revocation</h2>
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Expires</th>
                  <th>Responses / files</th>
                  <th>State</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {links.data?.items.map((l) => (
                  <tr key={l.id}>
                    <td>{l.request_id}</td>
                    <td>{l.expires_at}</td>
                    <td>
                      {l.responses} / {l.uploads}
                    </td>
                    <td>
                      <Status value={l.revoked ? "revoked" : "issued"} />
                    </td>
                    <td>
                      <Button onClick={() => setLid(l.id)}>
                        Review responses
                      </Button>
                      <Button
                        disabled={l.revoked || action.isPending || !canUpload}
                        onClick={() =>
                          action.mutate({
                            path: `collaboration/engagements/${eid}/links/${l.id}/revoke`,
                          })
                        }
                      >
                        Revoke
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <label>
              Acceptance review comments
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </label>
            {responses.data?.items.map((s) => (
              <article
                key={s.id}
                style={{
                  border: "1px solid var(--border)",
                  padding: 16,
                  marginTop: 12,
                }}
              >
                <p>
                  {s.kind} • {s.id}
                </p>
                <p>
                  Claimed identity: {s.body.claimed_name || "Not supplied"} •{" "}
                  {s.body.identity_verified ? "Verified" : "Unverified"}
                </p>
                <p style={{ whiteSpace: "pre-wrap" }}>{s.body.response}</p>
                <Status value={s.body.scan_status || "text response"} />
                {s.kind === "response" && (
                  <Button
                    disabled={action.isPending || !canUpload}
                    onClick={() =>
                      action.mutate({
                        path: `collaboration/engagements/${eid}/links/${lid}/submissions/${s.id}/accept`,
                        body: {
                          expected_request_version: requests.data?.items.find(
                            (r) => r.id === s.body.request_id,
                          )?.version,
                          comments,
                        },
                      })
                    }
                  >
                    Accept response into request draft
                  </Button>
                )}
              </article>
            ))}
            <p>
              Acceptance records the client response and evidence reference. It
              does not approve document sufficiency, clear malware quarantine or
              perform an audit procedure. Changing the request invalidates its
              previously issued client links.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

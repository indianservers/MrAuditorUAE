"use client";
import { CountrySettings } from "./country-settings";
import { useState } from "react";
import { TPClientDocuments } from "./tp-client-documents";
import Link from "next/link";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Button,
  ErrorState,
  Facts,
  Pagination,
  Status,
} from "@/components/ui/primitives";
import { useAPI, useAction, useDebounced } from "@/hooks/use-api";
import type { Page, RecordRow } from "@/types/models";
import { PageHeader } from "./shared";

export function AuditAdministration({ area }: { area: string }) {
  return area === "firm-settings" ? (
    <>
      <CountrySettings />
      <MethodologyStudio />
    </>
  ) : (
    <FirmAdministration area={area} />
  );
}
function FirmAdministration({ area }: { area: string }) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const value = useDebounced(search);
  const endpoint =
    area === "activity"
      ? "activity"
      : area === "roles" || area === "permissions"
        ? "roles"
        : "users";
  const q = useAPI<Page<RecordRow>>(
    `admin/${endpoint}?search=${encodeURIComponent(value)}&offset=${offset}&limit=50`,
    true,
    true,
  );
  const permissions = useAPI<{ items: string[] }>(
    "admin/permissions",
    endpoint === "roles",
  );
  const roles = useAPI<{ items: RecordRow[] }>("admin/roles");
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const current = q.data?.items.find((r) => r.id === selected?.id) || selected;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [token, setToken] = useState("");
  const action = useAction<RecordRow>();
  const titles: Record<string, string> = {
    users: "User & Role Management",
    roles: "Firm Roles & Permissions",
    permissions: "Permission Catalogue",
    teams: "Firm Teams & Permissions",
    activity: "Platform Activity & Audit Logs",
    "firm-settings": "Firm Methodology & Settings",
  };
  return (
    <>
      <PageHeader
        eyebrow="Firm administration"
        title={titles[area] || titles.users}
        description="Live firm access, explicit role grants and preserved permission events."
      />
      <nav className="audit-tabs" aria-label="Firm administration">
        {Object.keys(titles).map((k) => (
          <Link
            key={k}
            href={`/admin/${k}`}
            aria-current={k === area ? "page" : undefined}
          >
            {titles[k]}
          </Link>
        ))}
      </nav>
      <div className="audit-split">
        <section className="audit-register">
          <div className="toolbar">
            <input
              aria-label="Search administration"
              placeholder="Search users…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </div>
          <FinancialDataGrid
            name={`admin-${endpoint}`}
            rows={q.data?.items || []}
            loading={q.isLoading}
            error={q.error}
            columns={[
              column(
                endpoint === "users"
                  ? "email"
                  : endpoint === "roles"
                    ? "name"
                    : "action",
                "Record",
                300,
                {
                  cellRenderer: (p: { data: RecordRow; value: string }) => (
                    <button
                      className="text-button"
                      onClick={() => setSelected(p.data)}
                    >
                      {p.value}
                    </button>
                  ),
                },
              ),
              column(
                endpoint === "users"
                  ? "status"
                  : endpoint === "roles"
                    ? "id"
                    : "created_at",
                "Status / Reference",
                240,
              ),
              ...(endpoint === "users"
                ? [column("active_sessions", "Active sessions", 130)]
                : []),
            ]}
          />
          <Pagination
            offset={offset}
            total={q.data?.total || q.data?.items.length || 0}
            limit={50}
            onChange={setOffset}
          />
        </section>
        <aside className="audit-inspector">
          <div className="audit-editor">
            {endpoint === "users" && (
              <>
                <h3>Invite a colleague or client</h3>
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const result = await action.mutateAsync({
                      path: "admin/invitations",
                      body: { email, role_ids: [role] },
                    });
                    setToken(String(result.token));
                  }}
                >
                  <label>
                    Email address
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </label>
                  <label>
                    Initial role
                    <select
                      required
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      <option value="">Select role</option>
                      {roles.data?.items
                        .filter((r) => !String(r.name).startsWith("Platform"))
                        .map((r) => (
                          <option key={String(r.id)} value={String(r.id)}>
                            {String(r.name)}
                          </option>
                        ))}
                    </select>
                  </label>
                  <Button primary>Create secure invitation</Button>
                </form>
                {token && (
                  <div className="audit-notice">
                    <strong>Deliver securely to the invitee</strong>
                    <p>
                      Expires after 48 hours. This token is shown for
                      administrator delivery.
                    </p>
                    <textarea
                      readOnly
                      aria-label="Invitation token"
                      value={token}
                    />
                  </div>
                )}
              </>
            )}
            {current && endpoint === "users" && (
              <>
                <h3>Selected membership</h3>
                <Facts data={current} />
                <Button
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({
                      path: `admin/users/${current.id}`,
                      method: "PATCH",
                      body: {
                        status:
                          current.status === "active" ? "disabled" : "active",
                        role_ids: current.role_ids,
                      },
                    })
                  }
                >
                  {current.status === "active"
                    ? "Deactivate membership"
                    : "Activate membership"}
                </Button>
                <label>
                  Add firm role
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      if (e.target.value)
                        action.mutate({
                          path: `admin/users/${current.id}`,
                          method: "PATCH",
                          body: {
                            status: current.status,
                            role_ids: [
                              ...new Set([
                                ...(current.role_ids as string[]),
                                e.target.value,
                              ]),
                            ],
                          },
                        });
                    }}
                  >
                    <option value="">Select role to add</option>
                    {roles.data?.items.map((r) => (
                      <option key={String(r.id)} value={String(r.id)}>
                        {String(r.name)}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  Assign engagement roles in the engagement team workspace.
                  Client organization access is explicitly granted below.
                </p>
                <ClientGrant membership={String(current.id)} />
              </>
            )}
            {current && endpoint === "roles" && (
              <RolePermissions
                key={String(current.id) + JSON.stringify(current.permissions)}
                role={current}
                catalogue={permissions.data?.items || []}
              />
            )}{" "}
            {current && endpoint === "activity" && <Facts data={current} />}
            <ErrorState error={action.error} />
            {area === "teams" && (
              <p className="audit-notice">
                Teams are scoped to each engagement. Open an engagement’s Team
                workspace to assign different roles and expiration dates.
              </p>
            )}
            {area === "firm-settings" && (
              <p className="audit-notice">
                Methodology and review-chain policies are configured per
                engagement. Professional standards applicability must be
                validated for the reporting period.
              </p>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}
function RolePermissions({
  role,
  catalogue,
}: {
  role: RecordRow;
  catalogue: string[];
}) {
  const [selected, setSelected] = useState(
    new Set(role.permissions as string[]),
  );
  const action = useAction();
  return (
    <>
      <h3>{String(role.name)}</h3>
      <p>Changes take effect on the next authorized request.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate({
            path: `admin/roles/${role.id}/permissions`,
            body: { permissions: [...selected] },
          });
        }}
      >
        <div className="audit-permissions">
          {catalogue.map((code) => (
            <label key={code}>
              <input
                type="checkbox"
                checked={selected.has(code)}
                onChange={(e) => {
                  const n = new Set(selected);
                  if (e.target.checked) n.add(code);
                  else n.delete(code);
                  setSelected(n);
                }}
              />
              {code}
            </label>
          ))}
        </div>
        <Button primary>Save permission policy</Button>
        <ErrorState error={action.error} />
      </form>
    </>
  );
}
function ClientGrant({ membership }: { membership: string }) {
  const [client, setClient] = useState("");
  const action = useAction();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({
          path: "admin/client-access",
          body: { membership_id: membership, client_id: client },
        });
      }}
    >
      <label>
        Client organization UUID
        <input
          required
          value={client}
          onChange={(e) => setClient(e.target.value)}
        />
      </label>
      <Button>Grant client access</Button>
      <ErrorState error={action.error} />
    </form>
  );
}

export function ClientPortal() {
  const q = useAPI<Page<RecordRow>>("client-portal/requests", true, true);
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const current = q.data?.items.find((r) => r.id === selected?.id) || selected;
  const [response, setResponse] = useState("");
  const action = useAction();
  return (
    <>
      <PageHeader
        eyebrow="Client collaboration"
        title="Document Request Portal"
        description="Requests assigned to your organization. Internal audit work remains private."
      />
      <TPClientDocuments />
      <div className="audit-split">
        <section className="audit-register">
          <FinancialDataGrid
            name="client-requests"
            rows={q.data?.items || []}
            loading={q.isLoading}
            error={q.error}
            columns={[
              column("reference", "Request", 150, {
                cellRenderer: (p: { data: RecordRow; value: string }) => (
                  <button
                    className="text-button"
                    onClick={() => {
                      setSelected(p.data);
                      setResponse(String(p.data.response || ""));
                      action.mutate({
                        path: `client-portal/requests/${p.data.id}/view`,
                      });
                    }}
                  >
                    {p.value}
                  </button>
                ),
              }),
              column("title", "Requested document", 320),
              column("status", "Status", 180),
              column("due_date", "Due date", 140),
            ]}
          />
        </section>
        <aside className="audit-inspector">
          <div className="audit-editor">
            {current ? (
              <>
                <h3>{String(current.title)}</h3>
                <Status value={current.status} />
                <p>{String(current.question)}</p>
                <label>
                  Upload requested evidence
                  <input
                    type="file"
                    accept=".pdf,.csv,.xlsx,.docx,.png,.jpg,.jpeg"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) {
                        const body = new FormData();
                        body.append("file", f);
                        action.mutate({
                          path: `client-portal/requests/${current.id}/upload`,
                          body,
                        });
                      }
                    }}
                  />
                </label>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    action.mutate({
                      path: `client-portal/requests/${current.id}/responses`,
                      body: { version: current.version, response },
                    });
                  }}
                >
                  <label>
                    Response to the auditor
                    <textarea
                      rows={6}
                      required
                      value={response}
                      onChange={(e) => setResponse(e.target.value)}
                    />
                  </label>
                  <Button primary>Send response</Button>
                </form>
                <small>
                  Uploaded evidence is subject to security scanning and auditor
                  review.
                </small>
              </>
            ) : (
              <p>Select a document request to view its question and respond.</p>
            )}
            <ErrorState error={action.error} />
          </div>
        </aside>
      </div>
    </>
  );
}

function MethodologyStudio() {
  const q = useAPI<{ items: RecordRow[] }>("admin/methodology");
  const starter = useAPI<RecordRow>("admin/methodology/starter");
  const action = useAction();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [rationale, setRationale] = useState("");
  return (
    <>
      <PageHeader
        eyebrow="Firm administration / Methodology"
        title="Versioned Audit Methodology"
        description="Original editable procedures, reporting-period applicability and independent technical approval."
      />
      <div className="audit-split">
        <section className="audit-register">
          <div className="toolbar">
            <Button
              onClick={() => setDraft(JSON.stringify(starter.data, null, 2))}
            >
              Load 20-area starter
            </Button>
          </div>
          <FinancialDataGrid
            name="methodology-versions"
            rows={q.data?.items || []}
            loading={q.isLoading}
            error={q.error}
            columns={[
              column("name", "Profile", 300, {
                cellRenderer: (p: { data: RecordRow; value: string }) => (
                  <button
                    className="text-button"
                    onClick={() =>
                      setDraft(
                        JSON.stringify(
                          {
                            name: p.data.name,
                            previous_version: p.data.version,
                            effective_from: p.data.effective_from,
                            profile: p.data.profile,
                          },
                          null,
                          2,
                        ),
                      )
                    }
                  >
                    {p.value}
                  </button>
                ),
              }),
              column("version", "Version", 100),
              column("effective_from", "Effective from", 180),
              column("id", "Source reference", 300),
            ]}
          />
        </section>
        <aside className="audit-inspector">
          <div className="audit-editor">
            <h3>Prepare a methodology version</h3>
            <p>
              The starter is original draft guidance. Tailor it and record
              independent professional validation before approval.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                try {
                  action.mutate({
                    path: "admin/methodology",
                    body: JSON.parse(draft),
                  });
                  setError("");
                } catch {
                  setError("Enter valid methodology JSON");
                }
              }}
            >
              <label>
                Methodology profile JSON
                <textarea
                  rows={22}
                  required
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
              </label>
              <Button primary>Create preserved version</Button>
            </form>
            <h3>Independent approval</h3>
            <label>
              Technical approval rationale
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
              />
            </label>
            {q.data?.items.map((v) => (
              <div className="toolbar" key={String(v.id)}>
                <span>
                  {String(v.name)} v{String(v.version)}
                </span>
                <Button
                  disabled={!rationale}
                  onClick={() =>
                    action.mutate({
                      path: `admin/methodology/${v.id}/approve`,
                      body: { rationale },
                    })
                  }
                >
                  Approve version
                </Button>
              </div>
            ))}
            {error && <p role="alert">{error}</p>}
            <ErrorState error={action.error} />
          </div>
        </aside>
      </div>
    </>
  );
}

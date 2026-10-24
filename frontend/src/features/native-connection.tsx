"use client";

import { useState } from "react";
import { Button, ErrorState, Facts, Status } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import type { RecordRow } from "@/types/models";
import { JobProgress } from "./shared";

type Setup = {
  editions: string[];
  credential_fields: string[];
  config_fields: string[];
  partner_fields: string[];
  documentation: string;
  oauth: boolean;
};
const names: Record<string, string> = {
  company_id: "Source company / organization identifier",
  functional_currency: "Company base currency",
  base_url: "Approved HTTPS API service root",
  directory_tenant: "Microsoft directory tenant",
  bc_environment: "Business Central environment",
  account_id: "NetSuite account identifier",
  subsidiary_id: "NetSuite subsidiary",
  accounting_book: "NetSuite accounting book",
  ledger: "Accounting ledger",
  company_path: "Company verification endpoint",
  accounts_path: "Chart-of-accounts endpoint",
  ledger_path: "Posted ledger endpoint",
  tb_path: "Trial-balance endpoint (optional)",
  rows_key: "Rows response field",
  next_key: "Next-page response field",
  company_id_field: "Company identity response field",
  currency_field: "Base currency response field",
  client_id: "OAuth client ID",
  client_secret: "OAuth client secret",
  access_token: "Access token",
  refresh_token: "Refresh token",
  api_key: "Partner API key",
  username: "API username",
  password: "API password",
  control_reference: "Independent source report/reference (optional)",
  expected_gl_rows: "Independent GL row count (optional)",
  expected_gl_debit: "Independent base-currency debit total (optional)",
  expected_gl_credit: "Independent base-currency credit total (optional)",
};

export function NativeConnection({ connection }: { connection: RecordRow }) {
  const setup = useAPI<{ direct_api: Setup }>(
    `connectors/${connection.provider}/requirements`,
  );
  const [config, setConfig] = useState<Record<string, unknown>>(
    (connection.config || {}) as Record<string, unknown>,
  );
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [job, setJob] = useState("");
  const [syncRun, setSyncRun] = useState("");
  const [mappingText, setMappingText] = useState(
    JSON.stringify(config.mappings || {}, null, 2),
  );
  const [error, setError] = useState("");
  const [redirect, setRedirect] = useState(
    typeof window !== "undefined"
      ? window.location.origin + "/integrations/zoho/callback?native=1"
      : "",
  );
  const [code, setCode] = useState("");
  const [state, setState] = useState("");
  const [realm, setRealm] = useState("");
  const save = useAction<RecordRow>();
  const action = useAction<RecordRow>();
  const spec = setup.data?.direct_api;
  const edition = String(config.edition || spec?.editions[0] || "");
  const partner = edition.includes("partner-api");
  const fields = [
    ...new Set([
      ...(spec?.config_fields || []),
      ...(partner ? spec?.partner_fields || [] : []),
    ]),
  ];
  const credentialFields = (spec?.credential_fields || []).filter(
    (key) =>
      !partner ||
      ["access_token", "api_key", "username", "password"].includes(key),
  );
  const run = useAPI<RecordRow>(
    `connectors/native/sync-runs/${syncRun}`,
    !!syncRun,
    true,
  );
  const jobState = useAPI<RecordRow>(`jobs/${job}`, !!job, true);

  return (
    <div className="resource-form">
      <ErrorState error={setup.error || save.error || action.error} />
      <p>
        Direct extraction preserves source responses and stages validated
        accounting data. Live account qualification remains pending.
      </p>
      {partner && (
        <p role="status">
          This edition needs a vendor-approved partner API. Configure the
          documented endpoints and response fields supplied by the vendor or
          partner. A local installation alone does not provide this API.
        </p>
      )}
      {spec && (
        <>
          <a href={spec.documentation} target="_blank" rel="noreferrer">
            Vendor API documentation
          </a>
          <label>
            Product edition
            <select
              value={edition}
              onChange={(e) =>
                setConfig((v) => ({ ...v, edition: e.target.value }))
              }
            >
              {spec.editions.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <div className="form-grid">
            {fields.map((key) => (
              <label key={key}>
                {names[key] || key.replaceAll("_", " ")}
                <input
                  value={String(config[key] ?? "")}
                  onChange={(e) =>
                    setConfig((v) => ({ ...v, [key]: e.target.value }))
                  }
                  placeholder={
                    key === "functional_currency"
                      ? "INR / AED / USD"
                      : undefined
                  }
                />
              </label>
            ))}
          </div>
          {partner && (
            <label>
              Partner response column mappings (JSON, by coa/gl/tb)
              <textarea
                rows={7}
                value={mappingText}
                onChange={(e) => setMappingText(e.target.value)}
              />
            </label>
          )}
          <details>
            <summary>Secure credentials</summary>
            <p>
              Stored credentials are never displayed. Leave a field blank to
              keep its current value.
            </p>
            <div className="form-grid">
              {credentialFields.map((key) => (
                <label key={key}>
                  {names[key] || key.replaceAll("_", " ")}
                  <input
                    type={
                      key === "client_id" || key === "username"
                        ? "text"
                        : "password"
                    }
                    autoComplete="off"
                    value={credentials[key] || ""}
                    onChange={(e) =>
                      setCredentials((v) => ({ ...v, [key]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
          </details>
          <Button
            disabled={save.isPending}
            onClick={() => {
              setError("");
              let mappings = config.mappings || {};
              try {
                if (partner) mappings = JSON.parse(mappingText);
              } catch {
                setError("Partner mappings must be a JSON object.");
                return;
              }
              const cleanConfig = Object.fromEntries(
                Object.entries({ ...config, edition, mappings }).filter(
                  ([key, value]) =>
                    !key.startsWith("expected_gl_") || value !== "",
                ),
              );
              save.mutate(
                {
                  path: `connectors/native/${connection.id}/configuration`,
                  method: "PATCH",
                  body: {
                    config: cleanConfig,
                    credentials: Object.fromEntries(
                      Object.entries(credentials).filter(([, v]) => v),
                    ),
                  },
                },
                { onSuccess: () => setCredentials({}) },
              );
            }}
          >
            Save direct API configuration
          </Button>
          {spec.oauth && !partner && (
            <>
              <label>
                Registered OAuth callback URL
                <input
                  value={redirect}
                  onChange={(e) => setRedirect(e.target.value)}
                />
              </label>
              <Button
                disabled={action.isPending}
                onClick={() =>
                  action.mutate(
                    {
                      path: `connectors/native/${connection.id}/authorize`,
                      body: { redirect_uri: redirect },
                    },
                    {
                      onSuccess: (r) => {
                        const url = new URL(String(r.authorization_url));
                        if (
                          ["appcenter.intuit.com", "login.xero.com"].includes(
                            url.hostname,
                          ) &&
                          url.protocol === "https:"
                        ) {
                          sessionStorage.setItem(
                            "auditos-native-connection",
                            connection.id,
                          );
                          window.location.assign(url.href);
                        }
                      },
                    },
                  )
                }
              >
                Authorize {String(connection.provider)}
              </Button>
              <details>
                <summary>Complete OAuth callback manually</summary>
                <label>
                  Authorization code
                  <input
                    type="password"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </label>
                <label>
                  OAuth state
                  <input
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                  />
                </label>
                {connection.provider === "quickbooks" && (
                  <label>
                    QuickBooks realm ID
                    <input
                      value={realm}
                      onChange={(e) => setRealm(e.target.value)}
                    />
                  </label>
                )}
                <Button
                  disabled={!code || !state || action.isPending}
                  onClick={() =>
                    action.mutate(
                      {
                        path: `connectors/native/${connection.id}/callback`,
                        body: { code, state, realm_id: realm || null },
                      },
                      {
                        onSuccess: () => {
                          setCode("");
                          setState("");
                        },
                      },
                    )
                  }
                >
                  Complete consent
                </Button>
              </details>
            </>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {save.data && <Status value={save.data.status} />}
      <Button
        primary
        disabled={action.isPending || save.isPending}
        onClick={() =>
          action.mutate(
            {
              path: `connectors/native/${connection.id}/sync`,
            },
            {
              onSuccess: (r) => {
                setSyncRun("");
                setJob(r.id);
              },
            },
          )
        }
      >
        Start direct API sync
      </Button>
      {job && (
        <JobProgress
          id={job}
          onDone={() => {
            const data = jobState.data?.result as
              { resource_id?: string } | undefined;
            if (data?.resource_id) setSyncRun(data.resource_id);
          }}
        />
      )}
      <ErrorState error={run.error || jobState.error} />
      {run.data && (
        <>
          <Facts
            data={{
              status: run.data.status,
              completeness: run.data.completeness,
              ...Object.fromEntries(
                Object.entries(
                  (run.data.manifest || {}) as Record<string, unknown>,
                ).filter(([key]) =>
                  [
                    "counts",
                    "scope_verification",
                    "validation_error",
                    "derived_import_batch_ids",
                    "functional_totals",
                    "source_control_reference",
                  ].includes(key),
                ),
              ),
            }}
          />
        </>
      )}
      <p className="subtle">
        Server administrators must allow the exact API origin for SAP and
        partner-hosted endpoints. A successful extraction still requires
        independent source controls and reviewer activation.
      </p>
    </div>
  );
}

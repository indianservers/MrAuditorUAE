"use client";
import { useEffect, useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { CountryFlag } from "@/components/ui/country-flag";

export type CountryPackage = {
  country: string;
  name: string;
  version: string;
  status: string;
  currency_default: string | null;
  capabilities: string[];
  limitations: string;
  regulatory_qualified: boolean;
};
type Settings = {
  country: string;
  version: number;
  package: CountryPackage;
  scope: string;
  profile: {
    version: string;
    status: string;
    currencies: string[];
    financial_year: string;
    accounting_standards: string[];
    auditing_standards: string[];
    tax_categories: string[];
    reporting_requirements: string[];
    sources: { title: string; url: string }[];
    legal_effectivity: string;
  };
};

export function CountryContext() {
  const settings = useAPI<Settings>("jurisdictions/settings");
  const country = useScope((s) => s.country),
    setCountry = useScope((s) => s.setCountry);
  useEffect(() => {
    if (settings.data && settings.data.country !== country)
      setCountry(settings.data.country);
  }, [settings.data, country, setCountry]);
  return null;
}

export function CountrySettings() {
  const [search, setSearch] = useState("");
  const organization = useAPI<{
    country: string;
    version: number;
    can_manage: boolean;
  }>("jurisdictions/organization");
  const settings = useAPI<Settings>("jurisdictions/settings");
  const packages = useAPI<{ items: CountryPackage[] }>(
    "jurisdictions/packages",
  );
  const action = useAction<Settings>();
  return (
    <section className="global-page" aria-label="Country settings">
      <div className="global-heading">
        <div>
          <span className="eyebrow">Administration / global configuration</span>
          <h1>Countries &amp; Jurisdictions</h1>
          <p>
            One platform. Distinct incorporation facts, reporting contexts and
            user preferences.
          </p>
        </div>
      </div>
      <p>
        Select your working country in this firm. Entity and engagement
        directories follow this selection. Existing engagements keep their
        original country and package version.
      </p>
      <div className="country-panel">
        <div className="card">
          <h2>Working country</h2>
          <input
            aria-label="Search countries"
            placeholder="Search by country name or ISO code…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label>
            Working country
            <select
              aria-label="Working country"
              value={settings.data?.country || "AE"}
              disabled={!settings.data || action.isPending}
              onChange={(e) =>
                action.mutate({
                  path: "jurisdictions/settings",
                  method: "PATCH",
                  body: {
                    country: e.target.value,
                    version: settings.data!.version,
                  },
                })
              }
            >
              {packages.data?.items
                .filter(
                  (p) =>
                    p.country === settings.data?.country ||
                    `${p.name} ${p.country}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                )
                .map((p) => (
                  <option key={p.country} value={p.country}>
                    {p.name} ({p.country})
                    {p.status === "CORE_ONLY"
                      ? " — core audit only"
                      : " — scoped UAE package"}
                  </option>
                ))}
            </select>
          </label>
          <p className="subtle">
            This preference belongs to you within the selected firm. It does not
            amend an existing engagement.
          </p>
        </div>
        <div className="card">
          <h2>Organization default</h2>
          <p>
            Authorized administrators choose the default for users without an
            override and for new entity setup. Engagements inherit their
            selected legal entity’s jurisdiction; no existing context is
            rewritten.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              action.mutate({
                path: "jurisdictions/organization",
                method: "PATCH",
                body: {
                  country: f.get("country"),
                  version: organization.data!.version,
                },
              });
            }}
            key={[
              organization.data?.version,
              organization.data?.country,
              packages.data?.items.length,
            ].join(":")}
          >
            <label>
              Organization country
              <select
                aria-label="Organization default country"
                name="country"
                defaultValue={organization.data?.country}
                disabled={!organization.data?.can_manage}
              >
                {packages.data?.items.map((p) => (
                  <option key={p.country} value={p.country}>
                    {p.name} ({p.country})
                  </option>
                ))}
              </select>
            </label>
            {organization.data?.can_manage ? (
              <Button disabled={action.isPending}>
                Save organization default
              </Button>
            ) : (
              <p>Administrator permission required to change this default.</p>
            )}
          </form>
        </div>
      </div>
      {settings.data && (
        <>
          <p>
            <strong>Package:</strong> {settings.data.package.version}{" "}
            <Status value={settings.data.package.status} />
          </p>
          <div className="country-profile card">
            <div className="global-heading">
              <div>
                <CountryFlag country={settings.data.country} />
                <h2>
                  {settings.data.package.name}{" "}
                  <small>{settings.data.country}</small>
                </h2>
                <Status value={settings.data.profile.status} />
              </div>
              <span>{settings.data.profile.version}</span>
            </div>
            <div className="profile-columns">
              {[
                ["Currency defaults", settings.data.profile.currencies],
                [
                  "Accounting frameworks",
                  settings.data.profile.accounting_standards,
                ],
                ["Audit standards", settings.data.profile.auditing_standards],
                ["Tax categories", settings.data.profile.tax_categories],
                [
                  "Reporting configuration",
                  settings.data.profile.reporting_requirements,
                ],
              ].map(([label, values]) => (
                <section key={String(label)}>
                  <h3>{String(label)}</h3>
                  {(values as string[]).length ? (
                    (values as string[]).map((v) => <p key={v}>{v}</p>)
                  ) : (
                    <p>Requires configuration</p>
                  )}
                </section>
              ))}
            </div>
            <p>{settings.data.profile.financial_year}</p>
            <p>{settings.data.profile.legal_effectivity}</p>
            <h3>Primary source library</h3>
            {settings.data.profile.sources.map((s) => (
              <p key={s.url}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              </p>
            ))}
            {settings.data.country === "IN" && (
              <p role="status">
                India’s platform profile is configured. GST, TDS/TCS, tax audit,
                CARO and Schedule III statutory engines remain planned.
                Registration does not assert statutory compliance.
              </p>
            )}
          </div>
          <p role="status">{settings.data.package.limitations}</p>
          <p>
            Available package capabilities:{" "}
            {settings.data.package.capabilities.join(", ")}. Reporting standards
            and functional currency must still be selected and reviewed for each
            entity.
          </p>
          <p>
            This is a software capability manifest, not regulatory approval or
            production certification. Firm-wide portfolio summaries remain
            firm-wide.
          </p>
        </>
      )}
      <ErrorState
        error={
          settings.error || packages.error || organization.error || action.error
        }
      />
      <Button onClick={() => settings.refetch()} disabled={settings.isFetching}>
        Reload country settings
      </Button>
    </section>
  );
}

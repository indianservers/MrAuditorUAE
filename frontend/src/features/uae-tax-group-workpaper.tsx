"use client";

import { useState } from "react";
import { useAction, useAPI } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import {
  RetainedEvidenceSelect,
  type EvidenceChoice,
} from "./retained-evidence-select";
import { RetainedRowsTable } from "./retained-rows-table";
import { RetainedEvidenceDocuments } from "./retained-evidence-documents";

type EvidenceAccess = {
  eid: string;
  tenant: string;
  dependencies: { type: string; id: string; record_id?: string }[];
};

const SOURCES = [
  [
    "rule",
    "Tax Group original FTA7 PDF",
    "f3eebe866669ad14f6f2e0789631f3feaf492295ab51243126711d9296be2119",
  ],
  [
    "clarification",
    "Tax Group original CTP007 PDF",
    "5b8d235dfd5af78789cc8cb96d5f55dbb57fb1df5e2ba5224fc82d6696147dbf",
  ],
  ["adoption", "Tax Group legal adoption evidence", undefined],
  ["mapping", "Tax Group retained statement mapping", undefined],
] as const;

export function UAETaxGroupWorkpaper({
  eid,
  onCreated,
}: {
  eid: string;
  onCreated: (id: string) => void;
}) {
  const [sources, setSources] = useState<Record<string, EvidenceChoice | null>>(
    {},
  );
  const [values, setValues] = useState<Record<string, string>>({
    operative_changes: "unresolved",
  });
  const [showSchema, setShowSchema] = useState(false);
  const schema = useAPI(
    `intelligence/engagements/${eid}/tax-group-mapping-schema`,
    showSchema,
  );
  const action = useAction<{ id: string }>();
  const update = (key: string, value: string) =>
    setValues({ ...values, [key]: value });
  const ids = SOURCES.map(([key]) => sources[key]?.id);
  return (
    <details className="main-panel" style={{ padding: 20, marginBottom: 16 }}>
      <summary>Prepare UAE Tax Group statement workpaper</summary>
      <p>
        Upload the original authority PDFs, separate legal adoption, member
        statements and an independently prepared JSON mapping through Evidence
        first. All documents must be retained in this group engagement. The
        mapping identifies each member statement version and hash. Preparation
        reads those original mapping bytes directly.
      </p>
      <p>
        This prepares a draft four-statement aggregation workpaper. Workpaper
        review does not issue audited financial statements or establish
        membership eligibility, prescribed notes, leaving-member treatment or
        filing readiness.
      </p>
      <ErrorState error={action.error} />
      {[
        ["label", "Tax Group workpaper title"],
        ["assessed_on", "Tax Group assessed on"],
        ["adopted_from", "Tax Group adopted from"],
        ["adopted_through", "Tax Group adopted through"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            type={key === "label" ? "text" : "date"}
            value={values[key] || ""}
            onChange={(e) => update(key, e.target.value)}
          />
        </label>
      ))}
      <label>
        Tax Group operative changes
        <select
          value={values.operative_changes}
          onChange={(e) => update("operative_changes", e.target.value)}
        >
          <option value="unresolved">Unresolved</option>
          <option value="assessed_none">Assessed no operative change</option>
        </select>
      </label>
      <label>
        Tax Group source adoption assessment
        <textarea
          value={values.legal_adoption_assessment || ""}
          onChange={(e) => update("legal_adoption_assessment", e.target.value)}
        />
      </label>
      {SOURCES.map(([key, label, sha256]) => (
        <RetainedEvidenceSelect
          key={key}
          eid={eid}
          label={label}
          sha256={sha256}
          value={sources[key] || null}
          onChange={(value) => setSources({ ...sources, [key]: value })}
        />
      ))}
      <details onToggle={(event) => setShowSchema(event.currentTarget.open)}>
        <summary>View statement mapping schema</summary>
        <ErrorState error={schema.error} />
        {schema.data !== undefined && schema.data !== null && (
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(schema.data, null, 2)}
          </pre>
        )}
      </details>
      <Button
        disabled={
          action.isPending ||
          ids.some((id) => !id) ||
          new Set(ids).size !== 4 ||
          !values.label?.trim() ||
          !values.assessed_on ||
          !values.adopted_from ||
          !values.adopted_through ||
          (values.legal_adoption_assessment || "").trim().length < 10
        }
        onClick={async () => {
          try {
            const result = await action.mutateAsync({
              path: `intelligence/engagements/${eid}/uae-tax-group-statements`,
              body: {
                ...values,
                profile: "uae-tax-group-retained-workpaper/1",
                rule_evidence_version_id: sources.rule!.id,
                clarification_evidence_version_id: sources.clarification!.id,
                adoption_evidence_version_id: sources.adoption!.id,
                adoption_sha256: sources.adoption!.sha256,
                mapping_evidence_version_id: sources.mapping!.id,
                mapping_sha256: sources.mapping!.sha256,
              },
            });
            onCreated(result.id);
          } catch {
            /* Action error is displayed above. */
          }
        }}
      >
        Prepare Tax Group workpaper
      </Button>
    </details>
  );
}

function Collection({
  prefix,
  selected,
  name,
  title,
  period = "all",
  statement = "all",
  access,
}: {
  prefix: string;
  selected: string;
  name: string;
  title: string;
  period?: string;
  statement?: string;
  access?: EvidenceAccess;
}) {
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({
    collection_name: name,
    period,
    statement,
    offset: String(offset),
    limit: "25",
  });
  const result = useAPI<{ items: Record<string, unknown>[]; total: number }>(
    `${prefix}/events/${selected}/tax-group-collections?${query}`,
  );
  if (result.error) return <ErrorState error={result.error} />;
  if (result.isLoading)
    return <p role="status">Loading {title.toLowerCase()}…</p>;
  return (
    <div>
      <ErrorState error={result.error} />
      <RetainedRowsTable
        title={title}
        rows={result.data?.items || []}
        currency="AED"
        serverPage={{
          offset,
          total: result.data?.total || 0,
          onPage: setOffset,
          isLoading: result.isFetching,
        }}
      />
      {name === "documents" && access && (
        <RetainedEvidenceDocuments
          eid={access.eid}
          tenant={access.tenant}
          label="Tax Group"
          summary="Original files on this page"
          documents={(result.data?.items || []).map((item) => ({
            id: String(item.version_id),
            sha256: String(item.sha256),
            record_id: access.dependencies.find(
              (dependency) =>
                dependency.type === "evidence" &&
                dependency.id === item.version_id,
            )?.record_id,
          }))}
        />
      )}
    </div>
  );
}

export function UAETaxGroupResult({
  prefix,
  selected,
  body,
  access,
}: {
  prefix: string;
  selected: string;
  body: Record<string, unknown>;
  access?: EvidenceAccess;
}) {
  const totals = Array.isArray(body.tax_group_totals)
    ? (body.tax_group_totals as Record<string, unknown>[])
    : [];
  return (
    <section aria-label="UAE Tax Group statement workpaper">
      <h3>Draft Tax Group aggregation workpaper</h3>
      {body.blocked === true && (
        <p role="alert">
          Resolve the retained source and reconciliation issues before
          independent workpaper approval.
        </p>
      )}
      <p>
        Amounts retain their original AED precision. Independent workpaper
        review does not establish statutory readiness, an audit opinion or
        submission. The underlying original statement mapping and every source
        contribution remain retained.
      </p>
      {totals.map((total) => (
        <div key={String(total.period)}>
          <section aria-label={`${String(total.period)} Tax Group totals`}>
            <h4>{String(total.period)} totals</h4>
            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(180px, 1fr) minmax(0, 3fr)",
                gap: "8px 16px",
              }}
            >
              {Object.entries(total).map(([key, value]) => (
                <div key={key} style={{ display: "contents" }}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd style={{ margin: 0, overflowWrap: "anywhere" }}>
                    {value === null ? "Not established" : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          {(["position", "profit_loss", "oci", "changes_equity"] as const).map(
            (statement) => (
              <Collection
                key={`${selected}:${total.period}:${statement}`}
                prefix={prefix}
                selected={selected}
                name="statements"
                period={String(total.period)}
                statement={statement}
                title={`${String(total.period)} ${statement.replaceAll("_", " ")} statement`}
              />
            ),
          )}
        </div>
      ))}
      {(
        [
          ["issues", "Tax Group unresolved issues"],
          ["checks", "Tax Group reconciliation checks"],
          ["members", "Tax Group member packages"],
          ["sources", "Tax Group original source contributions"],
          ["adjustments", "Tax Group explicit adjustments"],
          ["notes", "Tax Group retained notes"],
          ["losses", "Tax Group pre-join loss review"],
          ["documents", "Tax Group retained documents"],
        ] as const
      ).map(([name, title]) => (
        <details key={`${selected}:${name}`}>
          <summary>{title}</summary>
          <Collection
            prefix={prefix}
            selected={selected}
            name={name}
            title={title}
            access={access}
          />
        </details>
      ))}
    </section>
  );
}

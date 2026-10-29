"use client";
import { useState } from "react";
import Link from "next/link";
import { Button, ErrorState, Status } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { useScope } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import {
  ReportRequirementsEditor,
  ReportRequirementSelector,
  type ReportRequirement,
} from "./report-requirements";
import { PageHeader } from "./shared";
import {
  TaxAuditScopeForm,
  emptyTaxScope,
  selectedTaxScope,
  type TaxAuditScope,
  type TaxScopeDraft,
} from "./tax-audit-scope";

type Block = {
  key: string;
  title: string;
  kind: string;
  source_kind?: string;
  source_id?: string;
  text: string;
  requirement_keys?: string[];
};
type Result = {
  id: string;
  version: number;
  freshness: string;
  body: {
    title: string;
    category: string;
    blocks: Block[];
    review_status: string;
    tax_audit_scope?: TaxAuditScope | null;
    requirements?: ReportRequirement[];
    requirements_assessed?: boolean;
    requirements_basis?: string;
    requirements_pack?: string | null;
    requirements_coverage?: {
      complete: boolean;
      source_validation: string;
      items: {
        key: string;
        title: string;
        disposition: string;
        status: string;
        block_keys: string[];
      }[];
    };
  };
};
const kinds = [
  "financial_table",
  "comparative_table",
  "regulatory_checklist",
  "disclosure",
  "reconciliation",
  "analysis",
  "graph",
  "findings_summary",
  "narrative",
  "working_paper_reference",
  "audit_conclusion",
];
export function StatutoryReportBuilder() {
  const scopeKey = useScope((scope) => `${scope.tenant}:${scope.country}`);
  return <ReportBuilderForm key={scopeKey} />;
}
function ReportBuilderForm() {
  const [eid, setEid] = useState("");
  const [requirements, setRequirements] = useState<ReportRequirement[]>([]);
  const [requirementsPack, setRequirementsPack] = useState<string | null>(null);
  const [requirementsAssessed, setRequirementsAssessed] = useState(false);
  const [requirementsBasis, setRequirementsBasis] = useState("");
  const [requirementKeys, setRequirementKeys] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("management-letter");
  const [comments, setComments] = useState("");
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [selected, setSelected] = useState("");
  const [reportId, setReportId] = useState("");
  const [kind, setKind] = useState("narrative");
  const [blockTitle, setBlockTitle] = useState("");
  const [sourceKind, setSourceKind] = useState("intelligence");
  const [sourceId, setSourceId] = useState("");
  const [text, setText] = useState("");
  const [taxScope, setTaxScope] = useState<TaxScopeDraft>(emptyTaxScope);
  const [error, setError] = useState<Error | null>(null);
  const engagements = useAPI<Page<RecordRow>>("engagements?limit=100");
  const presets = useAPI<{
    country: string;
    items: {
      id: string;
      title: string;
      category: string;
      kind: string;
      allow_not_applicable: boolean;
      not_applicable_keys?: string[];
      requirements: ReportRequirement[];
      limitations: string[];
    }[];
  }>(`regulatory/engagements/${eid}/report-presets`, !!eid);
  const availablePresets = (presets.data?.items || []).filter(
    (p) => p.category === category,
  );
  const selectedPreset = availablePresets.find(
    (p) => p.id === requirementsPack,
  );
  const sources = useEventHistory<{
    id: string;
    kind: string;
    label: string;
    review_status: string;
  }>(`intelligence/engagements/${eid}`, !!eid);
  const papers = useAPI<{ items: RecordRow[] }>(
    `engagements/${eid}/audit/working-papers?limit=100`,
    !!eid,
  );
  const templates = (sources.data?.items || []).filter(
    (item) => item.kind === "report-template",
  );
  const detail = useAPI<Result>(
    `intelligence/engagements/${eid}/events/${selected}`,
    !!selected && !!eid,
  );
  const action = useAction<Result>();
  function move(from: number, to: number) {
    if (to < 0 || to >= blocks.length) return;
    const copy = [...blocks];
    const [block] = copy.splice(from, 1);
    copy.splice(to, 0, block);
    setBlocks(copy);
  }
  return (
    <div className="intelligence-workspace">
      <PageHeader
        eyebrow="Reporting"
        title="Statutory Report Designer"
        description="Compose reviewed source tables, disclosures and working-paper references. Reordering blocks changes presentation, never the underlying calculations."
      />
      <div className="toolbar" style={{ padding: 16 }}>
        <label>
          Engagement
          <select
            value={eid}
            onChange={(e) => {
              setEid(e.target.value);
              setSelected("");
              setRequirements([]);
              setRequirementsPack(null);
              setRequirementsAssessed(false);
              setRequirementsBasis("");
              setRequirementKeys([]);
              setBlocks([]);
              setTitle("");
              setComments("");
              setBlockTitle("");
              setText("");
              setSourceId("");
              setCategory("management-letter");
              setTaxScope(emptyTaxScope);
              setReportId("");
              setError(null);
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
        {eid && (
          <Link className="button" href={`/engagements/${eid}/lifecycle`}>
            Review dependency graph
          </Link>
        )}
      </div>
      <ErrorState
        error={
          engagements.error ||
          sources.error ||
          papers.error ||
          presets.error ||
          detail.error ||
          action.error ||
          error
        }
      />
      {eid && (
        <>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Versioned template</h2>
            <label>
              Report title
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              Report category
              <select
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setRequirements([]);
                  setRequirementsPack(null);
                  setRequirementsAssessed(false);
                  setRequirementsBasis("");
                  setRequirementKeys([]);
                  setBlocks((old) =>
                    old.map((block) => ({ ...block, requirement_keys: [] })),
                  );
                  setTaxScope(emptyTaxScope);
                }}
              >
                {[
                  "india-statutory",
                  "caro",
                  "schedule-iii",
                  "india-tax-audit",
                  "uae-ifrs",
                  "uae-ct",
                  "vat",
                  "tp-local",
                  "tp-master",
                  "dmtt",
                  "group-audit",
                  "consolidation",
                  "internal-audit",
                  "management-letter",
                  "audit-committee",
                ].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {category === "india-tax-audit" && (
              <TaxAuditScopeForm
                eid={eid}
                value={taxScope}
                onChange={setTaxScope}
              />
            )}
            <label>
              Template / review rationale
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </label>
            {sources.hasOlder && (
              <Button
                disabled={sources.loadingOlder}
                onClick={sources.loadOlder}
              >
                Load older sources and templates
              </Button>
            )}
            {!!availablePresets.length && (
              <>
                <label>
                  Operational report preset
                  <select
                    value={requirementsPack || ""}
                    onChange={(e) => {
                      const preset = availablePresets.find(
                        (p) => p.id === e.target.value,
                      );
                      setRequirementsPack(preset?.id || null);
                      setRequirements(
                        preset?.requirements.map((r) => ({ ...r })) || [],
                      );
                      setRequirementsAssessed(false);
                      setRequirementsBasis("");
                      setRequirementKeys([]);
                      setBlocks((old) =>
                        old.map((b) => ({ ...b, requirement_keys: [] })),
                      );
                      if (preset) {
                        setKind(
                          preset.kind === "form26-index"
                            ? "working_paper_reference"
                            : "reconciliation",
                        );
                        setSourceKind(
                          preset.kind === "form26-index"
                            ? "record"
                            : "intelligence",
                        );
                      }
                    }}
                  >
                    <option value="">Manually declared requirements</option>
                    {availablePresets.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  Changing preset resets requirement assessments and block
                  mappings. All items still need explicit assessment and current
                  independently reviewed sources.
                </p>
                {selectedPreset && (
                  <ul>
                    {selectedPreset.limitations.map((limit) => (
                      <li key={limit}>{limit}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
            <ReportRequirementsEditor
              locked={!!requirementsPack}
              allowNotApplicable={selectedPreset?.allow_not_applicable === true}
              notApplicableKeys={selectedPreset?.not_applicable_keys}
              items={requirements}
              assessed={requirementsAssessed}
              basis={requirementsBasis}
              onItems={setRequirements}
              onAssessed={setRequirementsAssessed}
              onBasis={setRequirementsBasis}
            />
            <h3>Add source-linked block</h3>
            <label>
              Block title
              <input
                value={blockTitle}
                onChange={(e) => setBlockTitle(e.target.value)}
              />
            </label>
            <label>
              Content type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {kinds.map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label>
              Source type
              <select
                value={sourceKind}
                onChange={(e) => {
                  setSourceKind(e.target.value);
                  setSourceId("");
                }}
              >
                <option value="intelligence">
                  Immutable intelligence / regulatory result
                </option>
                <option value="record">Reviewed working paper</option>
              </select>
            </label>
            <label>
              Source reference
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
              >
                <option value="">No source (authored narrative only)</option>
                {sourceKind === "intelligence"
                  ? sources.data?.items.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label} • {s.review_status}
                      </option>
                    ))
                  : papers.data?.items.map((p) => (
                      <option key={p.id} value={p.id}>
                        {String(p.reference)} • {String(p.status)}
                      </option>
                    ))}
              </select>
            </label>
            <label>
              User-authored narrative / commentary
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <ReportRequirementSelector
              items={requirements}
              selected={requirementKeys}
              onChange={setRequirementKeys}
              label="Requirements covered by this block"
              searchLabel="Search requirements for this block"
            />
            <Button
              disabled={!blockTitle || (kind !== "narrative" && !sourceId)}
              onClick={() => {
                setBlocks([
                  ...blocks,
                  {
                    key: crypto.randomUUID(),
                    requirement_keys: requirementKeys,
                    title: blockTitle,
                    kind,
                    text,
                    ...(sourceId
                      ? { source_kind: sourceKind, source_id: sourceId }
                      : {}),
                  },
                ]);
                setBlockTitle("");
                setRequirementKeys([]);
                setText("");
              }}
            >
              Add content block
            </Button>
            <ol aria-label="Ordered report blocks">
              {blocks.map((b, i) => (
                <li
                  key={b.key}
                  draggable
                  onDragStart={(e) =>
                    e.dataTransfer.setData("text/plain", String(i))
                  }
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const from = Number(e.dataTransfer.getData("text/plain"));
                    if (Number.isInteger(from)) move(from, i);
                  }}
                  style={{
                    padding: 12,
                    border: "1px solid var(--border)",
                    marginBottom: 8,
                  }}
                >
                  <strong>{b.title}</strong> • {b.kind} •{" "}
                  {b.source_id || "Authored narrative"}
                  <p>
                    Requirement links:{" "}
                    {b.requirement_keys?.join(", ") ||
                      "None; review declared coverage"}
                  </p>
                  <ReportRequirementSelector
                    items={requirements}
                    selected={b.requirement_keys || []}
                    label={`Coverage for ${b.title}`}
                    onChange={(keys) =>
                      setBlocks((old) =>
                        old.map((block) =>
                          block.key === b.key
                            ? { ...block, requirement_keys: keys }
                            : block,
                        ),
                      )
                    }
                  />
                  <div className="toolbar">
                    <Button
                      aria-label={`Move ${b.title} up`}
                      disabled={i === 0}
                      onClick={() => move(i, i - 1)}
                    >
                      Up
                    </Button>
                    <Button
                      aria-label={`Move ${b.title} down`}
                      disabled={i === blocks.length - 1}
                      onClick={() => move(i, i + 1)}
                    >
                      Down
                    </Button>
                    <Button
                      onClick={() =>
                        setBlocks(blocks.filter((x) => x.key !== b.key))
                      }
                    >
                      Remove from new draft
                    </Button>
                  </div>
                </li>
              ))}
            </ol>
            <Button
              primary
              disabled={action.isPending || !blocks.length}
              onClick={async () => {
                setError(null);
                let assessedScope: TaxAuditScope | undefined;
                try {
                  if (category === "india-tax-audit")
                    assessedScope = selectedTaxScope(taxScope);
                } catch (failure) {
                  setError(failure as Error);
                  return;
                }
                const result = await action
                  .mutateAsync({
                    path: `regulatory/engagements/${eid}/report-templates`,
                    body: {
                      title,
                      category,
                      blocks,
                      rationale: comments,
                      requirements,
                      requirements_assessed: requirementsAssessed,
                      requirements_basis: requirementsBasis,
                      requirements_pack: requirementsPack,
                      ...(assessedScope
                        ? { tax_audit_scope: assessedScope }
                        : {}),
                      ...(detail.data
                        ? {
                            prior_id: detail.data.id,
                            expected_version: detail.data.version,
                          }
                        : {}),
                    },
                  })
                  .catch(() => null);
                if (result) setSelected(result.id);
              }}
            >
              Save template version
            </Button>
          </section>
          <section className="main-panel" style={{ padding: 20 }}>
            <h2>Review and controlled generation</h2>
            <label>
              Saved template version
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Select template</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label} • {t.review_status}
                  </option>
                ))}
              </select>
            </label>
            {detail.data && (
              <>
                <Status value={detail.data.body.review_status} />
                <Status value={detail.data.freshness} />
                <p>
                  {detail.data.body.title} • v{detail.data.version}
                </p>
                <section aria-label="Retained requirement coverage">
                  <h3>Declared requirement coverage</h3>
                  <p>
                    {detail.data.body.requirements_basis ||
                      "No scope basis recorded; amend this template before review."}
                  </p>
                  <p>
                    Source validation:{" "}
                    {detail.data.body.requirements_coverage
                      ?.source_validation || "Not assessed"}
                    . Statutory completeness is not qualified by this
                    declaration.
                  </p>
                  <table>
                    <caption>
                      Required items and their report-block links
                    </caption>
                    <thead>
                      <tr>
                        <th>Reference</th>
                        <th>Requirement</th>
                        <th>Disposition</th>
                        <th>Coverage</th>
                        <th>Blocks</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.body.requirements_coverage?.items.map(
                        (item) => (
                          <tr key={item.key}>
                            <td>{item.key}</td>
                            <td>{item.title}</td>
                            <td>{item.disposition}</td>
                            <td>{item.status}</td>
                            <td>{item.block_keys.join(", ") || "Missing"}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                  {detail.data.body.blocks.map((block) => (
                    <details key={block.key}>
                      <summary>
                        {block.title} · {block.key}
                      </summary>
                      <p>{block.text}</p>
                      <p>
                        {block.source_kind || "Authored narrative"}:{" "}
                        {block.source_id || "No evidence source"}
                      </p>
                      {block.source_id && (
                        <Link
                          href={
                            block.source_kind === "intelligence"
                              ? `/intelligence/${eid}/lead?event=${block.source_id}`
                              : `/engagements/${eid}/lifecycle`
                          }
                        >
                          {block.source_kind === "intelligence"
                            ? "Open source result"
                            : "Open source evidence graph"}
                        </Link>
                      )}
                    </details>
                  ))}
                </section>
                <Button
                  onClick={() => {
                    setBlocks(detail.data!.body.blocks);
                    setTitle(detail.data!.body.title);
                    setCategory(detail.data!.body.category);
                    setRequirements(detail.data!.body.requirements || []);
                    setRequirementsPack(
                      detail.data!.body.requirements_pack || null,
                    );
                    setRequirementsAssessed(
                      detail.data!.body.requirements_assessed || false,
                    );
                    setRequirementsBasis(
                      detail.data!.body.requirements_basis || "",
                    );
                    setRequirementKeys([]);
                    setTaxScope(
                      detail.data!.body.tax_audit_scope || emptyTaxScope,
                    );
                  }}
                >
                  Load retained blocks into new revision
                </Button>
                <Button
                  disabled={
                    action.isPending ||
                    !detail.data.body.requirements_coverage?.complete ||
                    detail.data.freshness !== "CURRENT"
                  }
                  onClick={async () => {
                    const result = await action
                      .mutateAsync({
                        path: `intelligence/engagements/${eid}/events/${selected}/review`,
                        body: {
                          action: "approve",
                          expected_version: detail.data!.version,
                          comments,
                        },
                      })
                      .catch(() => null);
                    if (result) setSelected(result.id);
                  }}
                >
                  Record independent template approval
                </Button>
                <Button
                  disabled={
                    action.isPending ||
                    detail.data.body.review_status !== "REVIEWED" ||
                    detail.data.freshness !== "CURRENT"
                  }
                  onClick={async () => {
                    const result = await action
                      .mutateAsync({
                        path: `regulatory/engagements/${eid}/reports`,
                        body: { template_id: selected, rationale: comments },
                      })
                      .catch(() => null);
                    if (result) setReportId(result.id);
                  }}
                >
                  Generate from current reviewed sources
                </Button>
              </>
            )}
            {reportId && (
              <Link
                className="button"
                href={`/intelligence/${eid}/lead?event=${reportId}`}
              >
                Review generated report and export DOCX / XLSX / PDF
              </Link>
            )}
            <p>
              Outputs retain template, source and reviewer versions. They remain
              drafts; the application does not sign opinions or submit statutory
              filings.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

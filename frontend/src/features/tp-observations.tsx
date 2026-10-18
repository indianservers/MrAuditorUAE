"use client";
import { useState } from "react";
import { useAPI, useAction } from "@/hooks/use-api";
import { Button, ErrorState } from "@/components/ui/primitives";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import type { Page, RecordRow } from "@/types/models";

export function TPObservations({
  base,
  profile,
  canScreen,
}: {
  base: string;
  profile: string;
  canScreen: boolean;
}) {
  const datasets = useAPI<Page<RecordRow>>(base + "/records/dataset");
  const studies = useAPI<Page<RecordRow>>(base + "/records/study");
  const [dataset, setDataset] = useState("");
  const [study, setStudy] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [country, setCountry] = useState("");
  const [industry, setIndustry] = useState("");
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const [review, setReview] = useState({
    reason: "",
    independence_review: "",
    loss_review: "",
    functional_review: "",
  });
  const observations = useAPI<Page<RecordRow>>(
    `${base}/observations?dataset_id=${dataset}&offset=${offset}&limit=50&search=${encodeURIComponent(search)}${country ? `&country=${encodeURIComponent(country)}` : ""}${industry ? `&industry=${encodeURIComponent(industry)}` : ""}`,
    !!dataset,
  );
  const action = useAction();
  async function decide(decision: string) {
    if (!selected) return;
    try {
      await action.mutateAsync({
        path: base + "/records/screening",
        body: {
          reference: "SCREEN-" + crypto.randomUUID(),
          title: `Comparable ${decision.toLowerCase()} — ${String(selected.company_key)}`,
          body: {
            profile_id: profile,
            study_id: study,
            evidence_record_ids: [dataset],
            rationale: review.reason,
            decisions: [{ observation_id: selected.id, decision, ...review }],
          },
        },
      });
      setSelected(null);
    } catch {}
  }
  return (
    <section>
      <h2>Authorized comparable observations</h2>
      <div className="toolbar">
        <label>
          Observation dataset
          <select
            aria-label="Observation dataset"
            value={dataset}
            onChange={(e) => {
              setDataset(e.target.value);
              setOffset(0);
              setSelected(null);
            }}
          >
            <option value="">Choose approved dataset</option>
            {datasets.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {String(x.reference)} · {String(x.status)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Comparable name
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Country code
          <input
            value={country}
            maxLength={2}
            onChange={(e) => {
              setCountry(e.target.value.toUpperCase());
              setOffset(0);
            }}
          />
        </label>
        <label>
          Industry
          <input
            value={industry}
            onChange={(e) => {
              setIndustry(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      {observations.error && <ErrorState error={observations.error} />}
      {action.error && <ErrorState error={action.error} />}
      <FinancialDataGrid
        exportable={false}
        name="tp-authorized-observations"
        rows={observations.data?.items || []}
        columns={[
          column("company_key", "Company key", 170),
          column("name", "Source name", 280),
          column("country", "Country", 90),
          column("industry", "Industry", 150),
          column("fiscal_year", "Year", 90),
          column("revenue", "Revenue", 150),
          column("cost_sales", "Cost of sales", 150),
          column("value", "Observed value", 150),
        ]}
        onSelect={setSelected}
      />
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous observations
        </Button>
        <span>
          {observations.data?.total || 0} observations · offset {offset}
        </span>
        <Button
          disabled={offset + 50 >= (observations.data?.total || 0)}
          onClick={() => setOffset(offset + 50)}
        >
          Next observations
        </Button>
      </div>
      {selected && (
        <>
          <h3>Screen {String(selected.company_key)}</h3>
          <label>
            Screening study
            <select
              aria-label="Screening study"
              value={study}
              onChange={(e) => setStudy(e.target.value)}
            >
              <option value="">Choose reviewed study</option>
              {studies.data?.items.map((x) => (
                <option key={x.id} value={x.id}>
                  {String(x.reference)}
                </option>
              ))}
            </select>
          </label>
          {Object.entries(review).map(([key, value]) => (
            <label key={key}>
              {key.replaceAll("_", " ")}
              <textarea
                value={value}
                onChange={(e) =>
                  setReview({ ...review, [key]: e.target.value })
                }
              />
            </label>
          ))}
          <div className="toolbar">
            {["ACCEPT", "REJECT"].map((d) => (
              <Button
                key={d}
                disabled={
                  !canScreen ||
                  !profile ||
                  !study ||
                  Object.values(review).some((x) => !x.trim()) ||
                  action.isPending
                }
                onClick={() => decide(d)}
              >
                Prepare {d.toLowerCase()} decision
              </Button>
            ))}
          </div>
          <p>
            Decisions remain draft workpapers until independently approved.
            Conflicting prior decisions must be resolved explicitly.
          </p>
        </>
      )}
    </section>
  );
}

export function TPCandidates({
  base,
  profile,
  onSelect,
}: {
  base: string;
  profile: string;
  onSelect: (row: RecordRow) => void;
}) {
  const [offset, setOffset] = useState(0);
  const q = useAPI<Page<RecordRow>>(
    `${base}/candidates/${profile}?offset=${offset}&limit=50`,
    !!profile,
  );
  return (
    <section>
      <h2>Ledger candidates requiring review</h2>
      <p>
        Exact party names and descriptive keywords are evidence pointers. Select
        a source to start a draft classification; establish its relationship and
        contract separately.
      </p>
      {q.error && <ErrorState error={q.error} />}
      <FinancialDataGrid
        exportable={false}
        name="tp-ledger-candidates"
        rows={q.data?.items || []}
        columns={[
          column("posting_date", "Posting date", 130),
          column("counterparty", "Counterparty", 230),
          column("description", "Source description", 360),
          column("base_amount", "Functional amount", 150),
          column("reason", "Candidate reason", 260),
        ]}
        onSelect={onSelect}
      />
      <div className="toolbar">
        <Button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous candidates
        </Button>
        <span>{q.data?.total || 0} candidates</span>
        <Button
          disabled={offset + 50 >= (q.data?.total || 0)}
          onClick={() => setOffset(offset + 50)}
        >
          Next candidates
        </Button>
      </div>
    </section>
  );
}

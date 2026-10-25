"use client";
import { useState } from "react";
import Link from "next/link";
import { useAPI, useAction } from "@/hooks/use-api";
import { useEventHistory } from "@/hooks/use-event-history";
import { Button, ErrorState } from "@/components/ui/primitives";
export function RegulatoryAssessmentPanel({ eid }: { eid: string }) {
  const engagementCountry = useAPI<{ country: string }>(
    `intelligence/engagements/${eid}/country-workflows`,
  );
  const country = engagementCountry.data?.country;
  const [ids, setIds] = useState<string[]>([]);
  const [facts, setFacts] = useState("{}");
  const [factSources, setFactSources] = useState("{}");
  const [date, setDate] = useState("");
  const [source, setSource] = useState("");
  const [conversion, setConversion] = useState("");
  const [rateSource, setRateSource] = useState("");
  const [rateRow, setRateRow] = useState("");
  const [rateOffset, setRateOffset] = useState(0);
  const [rateLabel, setRateLabel] = useState("");
  const [places, setPlaces] = useState("");
  const [rounding, setRounding] = useState("");
  const [convertedAmount, setConvertedAmount] = useState("");
  const [conversionReason, setConversionReason] = useState("");
  const [conversionTitle, setConversionTitle] = useState("");
  const [preparedConversion, setPreparedConversion] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const rules = useAPI<{
    items: {
      id: string;
      rule_key: string;
      version: number;
      state: string;
      body: {
        title: string;
        effective_from: string;
        effective_to: string | null;
        framework: string;
        method: string;
        calculation_currency?: string | null;
      };
    }[];
  }>(`regulatory/rules?country=${country}&limit=100`, !!country);
  const schedules = useEventHistory<{
    id: string;
    kind: string;
    table_type?: string;
    label: string;
    review_status: string;
    freshness: string;
  }>(`intelligence/engagements/${eid}`);
  const action = useAction<{ id: string }>();
  const conversions = schedules;
  const rateSources = schedules;
  const rateRows = useAPI<{
    collection_totals?: { rows: number };
    body: {
      rows: {
        id: string;
        source_currency: string;
        target_currency: string;
        rate: string;
        method: string;
        rate_date: string;
      }[];
    };
  }>(
    `intelligence/engagements/${eid}/events/${rateSource}?limit=100&offset=${rateOffset}`,
    !!rateSource,
  );
  return (
    <section className="main-panel" style={{ padding: 20 }}>
      <h2>Apply validated effective-dated rules</h2>
      <p>
        Country, entity type, framework, functional currency and reporting dates
        come from the approved engagement context. Additional facts and tax-base
        selection are professional inputs. Rate-based rules require an explicit
        currency matching the reviewed source; currency conversion needs a
        separate workflow. No tax thresholds or legal regime are assumed.
      </p>
      <ErrorState
        error={
          engagementCountry.error ||
          rules.error ||
          schedules.error ||
          conversions.error ||
          rateSources.error ||
          rateRows.error ||
          action.error ||
          error
        }
      />
      <label>
        Published rule versions
        <select
          multiple
          size={5}
          value={ids}
          onChange={(e) =>
            setIds(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {rules.data?.items
            .filter((r) => r.state === "PUBLISHED")
            .map((r) => (
              <option
                key={r.id}
                value={r.id}
                disabled={
                  ["benefit_profile", "payroll_profile"].includes(
                    r.body.method,
                  ) ||
                  (r.body.method === "flat_rate" &&
                    !r.body.calculation_currency)
                }
              >
                {r.rule_key} • v{r.version} • {r.body.framework} •{" "}
                {r.body.effective_from}–{r.body.effective_to || "open"} •{" "}
                {r.body.method}
                {r.body.method === "flat_rate"
                  ? ` • ${r.body.calculation_currency || "currency review required"}`
                  : r.body.method === "benefit_profile"
                    ? " • use employee benefit review"
                    : r.body.method === "payroll_profile"
                      ? " • use payroll contribution review"
                      : ""}
              </option>
            ))}
        </select>
      </label>
      {country === "AE" && (
        <p>
          <Link href={`/intelligence/${eid}/workflow-source`}>
            Prepare published benefit profiles for employee review
          </Link>
        </p>
      )}
      {country === "IN" && (
        <p>
          <Link href={`/intelligence/${eid}/workflow-source`}>
            Prepare published profiles for payroll contribution review
          </Link>
        </p>
      )}
      <label>
        Reviewed currency conversion (optional)
        <select
          value={conversion}
          onChange={(e) => setConversion(e.target.value)}
        >
          <option value="">Use original schedule currency</option>
          {conversions.data?.items
            .filter(
              (item) =>
                item.review_status === "REVIEWED" &&
                item.kind === "regulatory-conversion" &&
                item.freshness === "CURRENT",
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
        </select>
      </label>
      <details>
        <summary>Prepare explicit source currency conversion</summary>
        <p>
          Uses the selected reviewed source schedule. Retain an exchange-rate
          quote and import an fx-rates schedule with its document ID/hash,
          direction, date coverage and assessed method. Review the rate source
          independently first. No rate or rounding policy is selected
          automatically.
        </p>
        <label>
          Currency conversion title
          <input
            value={conversionTitle}
            onChange={(e) => setConversionTitle(e.target.value)}
          />
        </label>
        <label>
          Reviewed exchange rate source
          <select
            value={rateSource}
            onChange={(e) => {
              setRateSource(e.target.value);
              setRateRow("");
              setRateOffset(0);
              setRateLabel("");
            }}
          >
            <option value="">Select a reviewed rate source</option>
            {rateSources.data?.items
              .filter(
                (item) =>
                  item.table_type === "fx-rates" &&
                  item.kind === "workflow-source" &&
                  item.review_status === "REVIEWED" &&
                  item.freshness === "CURRENT",
              )
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
          </select>
        </label>
        <label>
          Exchange rate row
          <select
            value={rateRow}
            onChange={(e) => {
              setRateRow(e.target.value);
              setRateLabel(e.target.selectedOptions[0]?.text || "");
            }}
          >
            <option value="">Select an explicit direct rate</option>
            {rateRow &&
              !rateRows.data?.body?.rows.some(
                (item) => item.id === rateRow,
              ) && <option value={rateRow}>{rateLabel}</option>}
            {rateRows.data?.body?.rows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.source_currency} → {item.target_currency} · {item.rate} ·{" "}
                {item.method} · {item.rate_date}
              </option>
            ))}
          </select>
        </label>
        {rateSource && (
          <div className="toolbar">
            <Button
              disabled={!rateOffset || rateRows.isFetching}
              onClick={() => setRateOffset(Math.max(0, rateOffset - 100))}
            >
              Previous rate rows
            </Button>
            <Button
              disabled={
                rateRows.isFetching ||
                rateOffset + 100 >=
                  (rateRows.data?.collection_totals?.rows || 0)
              }
              onClick={() => setRateOffset(rateOffset + 100)}
            >
              Next rate rows
            </Button>
          </div>
        )}
        <label>
          Conversion decimal places
          <input
            type="number"
            min="0"
            max="8"
            value={places}
            onChange={(e) => setPlaces(e.target.value)}
          />
        </label>
        <label>
          Conversion rounding
          <select
            value={rounding}
            onChange={(e) => setRounding(e.target.value)}
          >
            <option value="">Select assessed rounding</option>
            <option value="half-up">Half up</option>
            <option value="half-even">Half even</option>
            <option value="towards-zero">Towards zero</option>
            <option value="floor">Floor</option>
          </select>
        </label>
        <label>
          Independent converted amount
          <input
            value={convertedAmount}
            onChange={(e) => setConvertedAmount(e.target.value)}
          />
        </label>
        <label>
          Conversion basis and rounding assessment
          <textarea
            value={conversionReason}
            onChange={(e) => setConversionReason(e.target.value)}
          />
        </label>
        <Button
          disabled={
            action.isPending ||
            !source ||
            !conversionTitle.trim() ||
            !rateSource ||
            !rateRow ||
            places === "" ||
            !rounding
          }
          onClick={async () => {
            setError(null);
            try {
              const output = await action.mutateAsync({
                path: `regulatory/engagements/${eid}/conversions`,
                body: {
                  source_event_id: source,
                  rate_source_id: rateSource,
                  rate_row_id: rateRow,
                  decimal_places: Number(places),
                  rounding,
                  target_amount: convertedAmount,
                  title: conversionTitle,
                  assessment: conversionReason,
                },
              });
              setPreparedConversion(output.id);
            } catch (e) {
              setError(e as Error);
            }
          }}
        >
          Prepare currency conversion for review
        </Button>
        {preparedConversion && (
          <Link
            className="button"
            href={`/intelligence/${eid}/lead?event=${preparedConversion}`}
          >
            Review prepared currency conversion
          </Link>
        )}
      </details>
      <label>
        Additional applicability facts (JSON)
        <textarea
          rows={5}
          value={facts}
          onChange={(e) => setFacts(e.target.value)}
        />
      </label>
      <label>
        Numeric fact source bindings (JSON)
        <textarea
          value={factSources}
          onChange={(e) => setFactSources(e.target.value)}
          placeholder='{"turnover":{"kind":"record","id":"approved-record-uuid","path":["amount"]}}'
        />
      </label>
      <label>
        Transaction date (for transaction-based rules)
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      <label>
        Reviewed source schedule (required for arithmetic)
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">No financial calculation</option>
          {schedules.data?.items
            .filter(
              (s) =>
                s.review_status === "REVIEWED" && s.freshness === "CURRENT",
              // Only original reviewed lead schedules can establish the base.
            )
            .filter((s) => s.kind === "lead")
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.label} • {s.id}
              </option>
            ))}
        </select>
      </label>
      {schedules.hasOlder && (
        <Button disabled={schedules.loadingOlder} onClick={schedules.loadOlder}>
          {schedules.error
            ? "Retry older source schedules"
            : schedules.loadingOlder
              ? "Loading older source schedules…"
              : "Load older source schedules"}
        </Button>
      )}
      <label>
        Professional applicability / tax-base selection rationale
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <Button
        disabled={action.isPending || !ids.length}
        onClick={async () => {
          setError(null);
          try {
            const output = await action.mutateAsync({
              path: `regulatory/engagements/${eid}/assessments`,
              body: {
                rule_ids: ids,
                facts: JSON.parse(facts),
                fact_sources: JSON.parse(factSources),
                rationale: reason,
                ...(date ? { transaction_date: date } : {}),
                ...(source ? { source_event_id: source } : {}),
                ...(conversion ? { conversion_event_id: conversion } : {}),
              },
            });
            setResult(output.id);
          } catch (e) {
            setError(e as Error);
          }
        }}
      >
        Evaluate current rules and retain receipt
      </Button>
      {result && (
        <Link
          className="button"
          href={`/intelligence/${eid}/lead?event=${result}`}
        >
          Review source-backed assessment
        </Link>
      )}
    </section>
  );
}

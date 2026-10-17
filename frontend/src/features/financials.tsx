"use client";
import {
  FinancialDataGrid,
  amount,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Badge,
  Button,
  Drawer,
  Empty,
  ErrorState,
  Facts,
  Pagination,
  QueryState,
  Status,
} from "@/components/ui/primitives";
import {
  useAPI,
  useAction,
  useCan,
  useCurrency,
  useDebounced,
  usePopulation,
} from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { money, textValue } from "@/lib/formatting/money";
import { useScope } from "@/stores/workspace";
import type { Balance, Page, RecordRow } from "@/types/models";
import { ArrowUpRight, CheckCircle2, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AIRequest,
  ContextGate,
  LineageDetail,
  PageHeader,
  PopulationPicker,
} from "./shared";
export function TrialBalance() {
  return (
    <>
      <PageHeader
        eyebrow="Financial Data"
        title="Trial Balance Workbench"
        description="Review, analyze and validate your trial balance with source-linked insights."
        actions={<Badge tone="blue">Backend-calculated balances</Badge>}
      />
      <ContextGate>
        <TrialBalanceBody />
      </ContextGate>
    </>
  );
}
function TrialBalanceBody() {
  const { snapshot, detail } = usePopulation();
  const scope = useScope();
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<RecordRow | null>(null);
  const balance = useAPI<Balance>(
    "accounting/trial-balance?" +
      qs({ snapshot_id: snapshot, offset, limit: 100 }),
    !!snapshot,
  );
  const accountId = selected?.id;
  const ledger = useAPI<Page<RecordRow>>(
    "workspace/ledger?" +
      qs({
        entity_id: scope.entity,
        period_id: scope.period,
        snapshot_id: snapshot,
        account_id: accountId,
        limit: 10,
      }),
    !!snapshot && !!accountId,
  );
  useEffect(() => {
    setSelected(null);
    setOffset(0);
  }, [snapshot]);
  return (
    <div className="workbench-body">
      <div className="toolbar">
        <PopulationPicker />
        <span className="subtle">
          Select an account to inspect its financial source.
        </span>
        <span className="spacer" />
        <Badge tone="neutral">Prior-period variance unavailable</Badge>
      </div>
      <ErrorState error={detail.error} />
      {!snapshot ? (
        <Empty title="No committed financial population">
          Upload and validate a GL, journal or trial balance file in
          Integrations.
        </Empty>
      ) : (
        <div className={"split-workbench" + (selected ? " has-inspector" : "")}>
          <section className="main-panel">
            <FinancialDataGrid
              name="trial-balance"
              rows={balance.data?.items || []}
              columns={[
                column("code", "Account Code", 100, { pinned: "left" }),
                column("name", "Account Name", 210, { pinned: "left" }),
                column("classification", "Account Category", 120),
                amount(
                  "opening",
                  "Opening Balance",
                  balance.data?.functional_currency,
                ),
                amount(
                  "debit",
                  "Period Debit",
                  balance.data?.functional_currency,
                ),
                amount(
                  "credit",
                  "Period Credit",
                  balance.data?.functional_currency,
                ),
                amount(
                  "display_closing",
                  "Closing Balance",
                  balance.data?.functional_currency,
                ),
                column("classification", "Mapping Status", 110, {
                  colId: "mapping",
                  valueFormatter: (p) =>
                    !p.value || p.value === "Unclassified"
                      ? "Unmapped"
                      : "Mapped",
                }),
              ]}
              onSelect={setSelected}
              loading={balance.isLoading}
              error={balance.error}
              currency={balance.data?.functional_currency}
            />
            <Pagination
              offset={offset}
              total={balance.data?.total || 0}
              limit={100}
              onChange={setOffset}
            />
            <div className="summary-strip">
              <div>
                <small>Total accounts</small>
                <strong>{balance.data?.total ?? "—"}</strong>
              </div>
              <div>
                <small>Mapped accounts</small>
                <strong className="success-text">
                  {balance.data?.mapped_accounts ?? "—"}
                </strong>
              </div>
              <div>
                <small>Unmapped accounts</small>
                <strong className="danger-text">
                  {balance.data?.unmapped_accounts ?? "—"}
                </strong>
              </div>
              <div>
                <small>Completeness</small>
                <span>Independent controls required</span>
              </div>
            </div>
          </section>
          {selected && (
            <aside className="inspector">
              <header>
                <SparkleLabel />
                <button
                  className="icon-button"
                  aria-label="Close account insight"
                  onClick={() => setSelected(null)}
                >
                  ×
                </button>
              </header>
              <h3>
                {textValue(selected.code)} — {textValue(selected.name)}
              </h3>
              <p className="subtle">{textValue(selected.classification)}</p>
              <div className="big-amount">
                {balance.data?.functional_currency}{" "}
                {money(selected.display_closing)}
              </div>
              <div className="card">
                <h4>Account overview</h4>
                <Facts
                  data={{
                    opening: money(selected.opening),
                    period_debit: money(selected.debit),
                    period_credit: money(selected.credit),
                    closing: money(selected.closing),
                    prior_period: "Unavailable",
                    transaction_count: ledger.data?.total ?? "Unavailable",
                  }}
                />
              </div>
              <Link
                className="button"
                href={"/financials/general-ledger?account=" + selected.id}
              >
                <ArrowUpRight size={14} /> Linked transactions
              </Link>
              <div className="card">
                <h4>Recent linked journal lines</h4>
                <QueryState query={ledger}>
                  {ledger.data?.items.map((l) => (
                    <Link
                      className="list-link"
                      href={
                        "/financials/general-ledger?line=" +
                        l.id +
                        "&account=" +
                        selected.id
                      }
                      key={l.id}
                    >
                      {textValue(l.voucher_number)}
                      <span>{textValue(l.posting_date)}</span>
                    </Link>
                  ))}
                  {ledger.data?.total === 0 && (
                    <p>No journal rows for this source type.</p>
                  )}
                </QueryState>
              </div>
              {snapshot && (
                <AIRequest
                  key={selected.id}
                  task="account-classification"
                  snapshot={snapshot}
                  accountId={selected.id}
                />
              )}
            </aside>
          )}
        </div>
      )}
      {balance.data && (
        <footer className="balance-bar">
          <span
            className={
              "balance-icon " + (balance.data.balanced ? "good" : "bad")
            }
          >
            <CheckCircle2 size={25} />
          </span>
          <div>
            <strong>
              {balance.data.balanced
                ? "Trial Balance Balanced"
                : "Trial Balance Difference"}
            </strong>
            <small>Balance alone does not prove completeness</small>
          </div>
          <div>
            <small>Total Debits ({balance.data.functional_currency})</small>
            <strong>{money(balance.data.total_debit)}</strong>
          </div>
          <div>
            <small>Total Credits ({balance.data.functional_currency})</small>
            <strong>{money(balance.data.total_credit)}</strong>
          </div>
          <div>
            <small>Difference</small>
            <strong>{money(balance.data.debit_credit_difference)}</strong>
          </div>
        </footer>
      )}
    </div>
  );
}
function SparkleLabel() {
  return <strong className="ai-label">✦ AI Insight</strong>;
}
export function Ledger({ journals = false }: { journals?: boolean }) {
  return (
    <>
      <PageHeader
        eyebrow="Financial Data"
        title={journals ? "Journal Entries" : "General Ledger Explorer"}
        description="Explore the financial population. Trace every journal line to its immutable source."
      />
      <ContextGate>
        <LedgerBody />
      </ContextGate>
    </>
  );
}
function LedgerBody() {
  const currency = useCurrency();
  const scope = useScope();
  const params = useSearchParams();
  const [search, setSearch] = useState(""),
    [account, setAccount] = useState(params.get("account") || ""),
    [dateFrom, setDateFrom] = useState(""),
    [dateTo, setDateTo] = useState(""),
    [minimum, setMinimum] = useState(""),
    [maximum, setMaximum] = useState(""),
    [journalType, setJournalType] = useState(""),
    [sort, setSort] = useState("-posting_date"),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<RecordRow | null>(null);
  const debounced = useDebounced(search);
  const accounts = useAPI<Page<RecordRow>>(
    "accounting/accounts?" + qs({ entity_id: scope.entity, limit: 100 }),
  );
  const path =
    "workspace/ledger?" +
    qs({
      entity_id: scope.entity,
      period_id: scope.period,
      account_id: account,
      search: debounced,
      date_from: dateFrom,
      date_to: dateTo,
      minimum,
      maximum,
      journal_type: journalType,
      offset,
      limit: 50,
      sort,
    });
  const q = useAPI<Page<RecordRow>>(path);
  useEffect(() => {
    setOffset(0);
    setSelected(null);
  }, [
    debounced,
    account,
    dateFrom,
    dateTo,
    minimum,
    maximum,
    journalType,
    sort,
    scope.entity,
    scope.period,
  ]);
  const line = useAPI<RecordRow>(
    "accounting/lineage/" + params.get("line"),
    !!params.get("line"),
  );
  useEffect(() => {
    if (line.data?.journal_line)
      setSelected(line.data.journal_line as RecordRow);
  }, [line.data]);
  return (
    <div className="workbench-body">
      <div className="tabs">
        <span className="active">All transactions</span>
        <Link href="/financials/journals">Journals</Link>
        <Link href="/financials/trial-balance">Trial balance</Link>
      </div>
      <div className="toolbar wrap">
        <label className="search-field">
          <Search size={14} />
          <input
            aria-label="Search transaction descriptions"
            placeholder="Search transaction descriptions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <select
          aria-label="Filter account"
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        >
          <option value="">All accounts</option>
          {accounts.data?.items.map((a) => (
            <option key={a.id} value={a.id}>
              {textValue(a.code)} · {textValue(a.name)}
            </option>
          ))}
        </select>
        <label>
          From
          <input
            type="date"
            aria-label="Posting date from"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            aria-label="Posting date to"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
        <input
          className="small-input"
          type="number"
          min="0"
          aria-label="Minimum amount"
          placeholder="Min amount"
          value={minimum}
          onChange={(e) => setMinimum(e.target.value)}
        />
        <input
          className="small-input"
          type="number"
          min="0"
          aria-label="Maximum amount"
          placeholder="Max amount"
          value={maximum}
          onChange={(e) => setMaximum(e.target.value)}
        />
        <input
          className="small-input"
          aria-label="Journal type"
          placeholder="Journal type"
          value={journalType}
          onChange={(e) => setJournalType(e.target.value)}
        />
        <select
          aria-label="Server sort"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="-posting_date">Newest first</option>
          <option value="posting_date">Oldest first</option>
          <option value="-amount">Largest amounts</option>
          <option value="code">Account code</option>
        </select>
      </div>
      <FinancialDataGrid
        name="general-ledger"
        server
        rows={q.data?.items || []}
        loading={q.isLoading}
        error={q.error}
        onSelect={setSelected}
        columns={[
          column("posting_date", "Posting Date", 125, { pinned: "left" }),
          column("voucher_number", "Voucher No.", 160),
          column("account_code", "Account", 110),
          column("account_name", "Account Name", 210),
          column("description", "Narration", 300),
          amount("base_debit", "Debit", currency),
          amount("base_credit", "Credit", currency),
          column("source_system", "Source", 115),
          column("counterparty", "Counterparty", 180),
        ]}
      />
      <Pagination
        offset={offset}
        total={q.data?.total || 0}
        limit={50}
        onChange={setOffset}
      />
      <Drawer
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title="Transaction Details"
      >
        {selected && (
          <>
            <Status value="Source linked" />
            <h3>{textValue(selected.voucher_number || selected.id)}</h3>
            <Facts
              data={{
                posting_date: selected.posting_date,
                document_date: selected.document_date,
                description: selected.description,
                debit: money(selected.base_debit),
                credit: money(selected.base_credit),
                source: selected.source_system,
                batch: selected.batch_id,
                attachments: "Not available through current API",
              }}
            />
            <LineageDetail id={selected.id} />
          </>
        )}
      </Drawer>
    </div>
  );
}
export function Mapping() {
  const scope = useScope();
  const q = useAPI<Page<RecordRow>>(
    "accounting/accounts?" + qs({ entity_id: scope.entity, limit: 100 }),
    !!scope.entity,
  );
  const [selected, setSelected] = useState<RecordRow | null>(null),
    [classification, setClassification] = useState("Assets"),
    [group, setGroup] = useState("");
  const action = useAction();
  const can = useCan("accounting.map");
  return (
    <>
      <PageHeader
        eyebrow="Financial Data"
        title="Account Mapping"
        description="Apply an explicit, versioned classification profile. AI suggestions never modify the ledger."
      />
      <ContextGate>
        <div className="workbench-body">
          <FinancialDataGrid
            name="mapping"
            rows={q.data?.items || []}
            loading={q.isLoading}
            error={q.error}
            columns={[
              column("code", "Code", 120),
              column("name", "Account", 300),
              column("classification", "Classification", 170),
              column("statement_group", "Statement group", 220),
              column("mapping_version", "Mapping version", 140),
            ]}
            onSelect={setSelected}
          />
        </div>
      </ContextGate>
      <Drawer
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title="Account classification"
      >
        {selected && (
          <>
            <Facts
              data={{
                code: selected.code,
                name: selected.name,
                current_classification: selected.classification,
              }}
            />
            <form
              className="resource-form"
              onSubmit={(e) => {
                e.preventDefault();
                action.mutate(
                  {
                    path: "accounting/mappings",
                    body: {
                      client_id: scope.client,
                      entity_id: scope.entity,
                      period_id: scope.period,
                      name: "Manual account mapping",
                      approved: true,
                      mapping: {
                        accounts: {
                          [String(selected.code)]: {
                            classification,
                            statement_group: group,
                          },
                        },
                      },
                    },
                  },
                  { onSuccess: () => setSelected(null) },
                );
              }}
            >
              <label>
                Classification
                <select
                  value={classification}
                  onChange={(e) => setClassification(e.target.value)}
                >
                  {[
                    "Assets",
                    "Liabilities",
                    "Equity",
                    "Income",
                    "Expenses",
                  ].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Statement group
                <input
                  required
                  value={group}
                  maxLength={100}
                  onChange={(e) => setGroup(e.target.value)}
                />
              </label>
              <Button primary disabled={!can || action.isPending}>
                <ShieldCheck size={14} /> Approve and apply mapping
              </Button>
              <ErrorState error={action.error} />
            </form>
          </>
        )}
      </Drawer>
    </>
  );
}

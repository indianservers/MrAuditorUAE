"use client";
import { textValue } from "@/lib/formatting/money";
import { useUI } from "@/stores/workspace";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tooltip from "@radix-ui/react-tooltip";
import {
  AlertCircle,
  Database,
  LoaderCircle,
  RefreshCw,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
export function Button({
  children,
  primary = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return (
    <button className={"button" + (primary ? " primary" : "")} {...props}>
      {children}
    </button>
  );
}
export function Tip({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tooltip" side="right">
          {label}
          <Tooltip.Arrow />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Status({ value }: { value: unknown }) {
  const s = textValue(value);
  const state = s.toLowerCase();
  return (
    <Badge
      tone={
        [
          "active",
          "passed",
          "completed",
          "approved",
          "balanced",
          "authorized",
          "connected",
        ].includes(state)
          ? "success"
          : ["failed", "critical", "error", "rejected", "unbalanced"].includes(
                state,
              )
            ? "danger"
            : /review|pending|insufficient|not_testable|uploaded/.test(state) ||
                ["high", "moderate"].includes(state)
              ? "warning"
              : "neutral"
      }
    >
      {s.replaceAll("_", " ")}
    </Badge>
  );
}
export function Empty({
  title = "No data yet",
  children,
}: {
  title?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Database size={23} />
      </span>
      <h3>{title}</h3>
      <p>
        {children ||
          "Select a client, entity and financial period, then import a financial population."}
      </p>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={20} /> Loading authorized records…
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return error ? (
    <div className="error" role="alert">
      <AlertCircle size={18} />
      <div>
        <strong>
          {"status" in error && error.status === 403
            ? "Access restricted"
            : error.message}
        </strong>
        <p>
          {"requestId" in error && error.requestId
            ? `Reference: ${error.requestId}`
            : "Your firm permissions and service availability apply."}
        </p>
      </div>
      {retry && (
        <Button onClick={retry}>
          <RefreshCw size={14} /> Retry
        </Button>
      )}
    </div>
  ) : null;
}
export function QueryState({
  query,
  children,
}: {
  query: { isLoading: boolean; error: Error | null; refetch: () => unknown };
  children: React.ReactNode;
}) {
  if (query.isLoading) return <Loading />;
  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return children;
}
export function Modal({
  open,
  onOpenChange,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className={"modal " + (wide ? "wide" : "")}
          aria-describedby={undefined}
        >
          <header>
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close asChild>
              <button className="icon-button" aria-label="Close dialog">
                <X size={18} />
              </button>
            </Dialog.Close>
          </header>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function Drawer({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: React.ReactNode;
}) {
  const { panelWidth, setPanelWidth } = useUI();
  const start = useRef(0);
  const [dragging, setDragging] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="drawer-overlay" />
        <Dialog.Content
          className="drawer"
          style={{ width: Math.max(panelWidth, 380) }}
          aria-describedby={undefined}
        >
          {/* A focusable ARIA separator implements the WAI-ARIA window splitter keyboard pattern. */}
          {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
          <div
            className="resize-handle"
            role="separator"
            aria-label="Resize detail drawer"
            aria-orientation="vertical"
            aria-valuenow={panelWidth}
            aria-valuemin={380}
            aria-valuemax={700}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft")
                setPanelWidth(Math.min(700, panelWidth + 20));
              if (e.key === "ArrowRight")
                setPanelWidth(Math.max(380, panelWidth - 20));
            }}
            onPointerDown={(e) => {
              start.current = e.clientX;
              setDragging(true);
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              if (dragging) {
                setPanelWidth(
                  Math.max(
                    380,
                    Math.min(700, panelWidth + start.current - e.clientX),
                  ),
                );
                start.current = e.clientX;
              }
            }}
            onPointerUp={() => setDragging(false)}
          />
          {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
          <header>
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close asChild>
              <button className="icon-button" aria-label="Close details">
                <X size={18} />
              </button>
            </Dialog.Close>
          </header>
          <div className="drawer-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function Facts({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="facts">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>{textValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: string[];
  value: string;
  onChange: (s: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((v) => (
        <button
          key={v}
          role="tab"
          aria-selected={v === value}
          className={v === value ? "active" : ""}
          onClick={() => onChange(v)}
        >
          {v}
        </button>
      ))}
    </div>
  );
}
export function Pagination({
  offset,
  total,
  limit,
  onChange,
}: {
  offset: number;
  total: number;
  limit: number;
  onChange: (n: number) => void;
}) {
  return (
    <footer className="pagination">
      <span>
        {total
          ? `${offset + 1}–${Math.min(total, offset + limit)} of ${total.toLocaleString()} records`
          : "0 records"}
      </span>
      <div>
        <Button
          aria-label="Previous page"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <span>Page {Math.floor(offset / limit) + 1}</span>
        <Button
          aria-label="Next page"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </Button>
      </div>
      <small>Server page · {limit} rows</small>
    </footer>
  );
}

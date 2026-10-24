"use client";
import { CountryContext } from "@/features/country-settings";
import { navigation } from "@/components/navigation/routes";
import {
  Empty,
  ErrorState,
  Loading,
  Modal,
  Tip,
} from "@/components/ui/primitives";
import { useAccess, useAPI, useDebounced, useDirectory } from "@/hooks/use-api";
import { api, qs } from "@/lib/api/client";
import { useScope, useUI } from "@/stores/workspace";
import type { Page, RecordRow } from "@/types/models";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  ChevronDown,
  ChevronsLeft,
  Command,
  LogOut,
  Menu,
  PanelLeftClose,
  Search,
  Sparkles,
  Layers as LayersIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname(),
    router = useRouter(),
    cache = useQueryClient();
  const scope = useScope();
  const ui = useUI();
  const access = useAccess();
  const directory = useDirectory();
  const [command, setCommand] = useState(false),
    [notifications, setNotifications] = useState(false),
    [authError, setAuthError] = useState("");
  const session = useQuery({
    queryKey: ["session"],
    retry: false,
    queryFn: async () => {
      try {
        return await api<{ email: string }>("/api/session");
      } catch (e) {
        if (
          "status" in (e as object) &&
          (e as { status: number }).status === 401
        ) {
          await api("/api/session/refresh", { method: "POST" });
          return api<{ email: string }>("/api/session");
        }
        throw e;
      }
    },
  });
  const tenants = useQuery({
    queryKey: ["tenants"],
    enabled: !!session.data,
    queryFn: ({ signal }) =>
      api<{ id: string; name: string }[]>("tenants", { signal }),
  });
  useEffect(() => {
    if (tenants.data?.length && !scope.tenant)
      scope.setTenant(tenants.data[0].id);
  }, [tenants.data, scope]);
  useEffect(() => {
    if (
      session.error &&
      "status" in session.error &&
      session.error.status === 401
    )
      router.replace("/login");
  }, [session.error, router]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setCommand((v) => !v);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const [sections, setSections] = useState<Record<string, boolean>>({});
  const [specialists, setSpecialists] = useState(false);
  const mainRoutes = [
    "/dashboard",
    "/clients",
    "/engagements",
    "/intelligence",
    "/compliance/country",
    "/modules",
    "/working-papers",
    "/findings",
    "/groups",
    "/reports",
    "/ai-copilot",
    "/admin/users",
    "/settings",
  ];
  const permitted = navigation.filter((n) =>
    access.data?.permissions.includes(n.permission),
  );
  const changeTenant = (id: string) => {
    cache.removeQueries({ queryKey: ["api"] });
    cache.removeQueries({ queryKey: ["access"] });
    scope.setTenant(id);
  };
  if (session.isLoading) return <Loading />;
  if (session.error)
    return (
      <main className="auth-error">
        <ErrorState error={session.error} retry={() => session.refetch()} />
        <Link href="/login">Return to sign in</Link>
      </main>
    );
  return (
    <div
      className={
        "app-shell" +
        (ui.collapsed ? " sidebar-collapsed" : "") +
        (ui.dark ? " dark-sidebar" : "")
      }
    >
      <CountryContext />
      <header className="topbar">
        <Link href="/dashboard" className="brand">
          <span className="brand-mark">A</span>
          <span>
            Mr Auditor <small>{scope.country}</small>
          </span>
        </Link>
        <button className="command-search" onClick={() => setCommand(true)}>
          <Search size={16} />
          <span>Search accounts, transactions, clients, or ask AI…</span>
          <kbd>⌘ K</kbd>
        </button>
        <div className="context-selects">
          <EngagementSwitcher />
          <label>
            <Building2 size={15} />
            <select
              aria-label="Select client"
              value={scope.client}
              onChange={(e) => scope.setClient(e.target.value)}
            >
              <option value="">Firm-wide</option>
              {directory.clients.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <Building2 size={15} />
            <select
              aria-label="Select entity"
              value={scope.entity}
              disabled={!scope.client}
              onChange={(e) => scope.setEntity(e.target.value)}
            >
              <option value="">Select entity</option>
              {directory.entities.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <select
              aria-label="Select period"
              value={scope.period}
              disabled={!scope.entity}
              onChange={(e) => scope.setPeriod(e.target.value)}
            >
              <option value="">Select period</option>
              {directory.periods.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.start_date} – {p.end_date}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          className="icon-button"
          aria-label="Notifications"
          onClick={() => setNotifications(true)}
        >
          <Bell size={19} />
        </button>
        <Dropdown.Root>
          <Dropdown.Trigger className="user-button" aria-label="User menu">
            <span className="avatar">
              {session.data?.email.slice(0, 2).toUpperCase()}
            </span>
            <span className="user-label">
              {session.data?.email}
              <small>Firm workspace</small>
            </span>
            <ChevronDown size={14} />
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content className="dropdown" align="end">
              <Dropdown.Label>Workspace</Dropdown.Label>
              {tenants.data?.map((t) => (
                <Dropdown.Item key={t.id} onSelect={() => changeTenant(t.id)}>
                  {t.name}
                  {t.id === scope.tenant ? " ✓" : ""}
                </Dropdown.Item>
              ))}
              <Dropdown.Separator />
              <Dropdown.Item onSelect={() => router.push("/settings")}>
                Country & regional settings ({scope.country})
              </Dropdown.Item>
              <Dropdown.Item onSelect={() => ui.toggleTheme()}>
                Toggle sidebar appearance
              </Dropdown.Item>
              <Dropdown.Item
                onSelect={async () => {
                  try {
                    await api("/api/session", { method: "DELETE" });
                    cache.clear();
                    scope.setTenant("");
                    window.location.assign("/login");
                  } catch (e) {
                    setAuthError((e as Error).message);
                  }
                }}
              >
                <LogOut size={14} /> Sign out
              </Dropdown.Item>
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      </header>
      <aside className="sidebar">
        <button
          className="collapse-button"
          onClick={ui.toggleSidebar}
          aria-label={
            ui.collapsed ? "Expand navigation" : "Collapse navigation"
          }
        >
          {ui.collapsed ? (
            <Menu size={18} />
          ) : (
            <>
              <PanelLeftClose size={16} />
              <span>Workspace</span>
              <ChevronsLeft size={14} />
            </>
          )}
        </button>
        <nav aria-label="Main navigation">
          {permitted
            .filter(
              (n) =>
                mainRoutes.includes(n.href) ||
                specialists ||
                path.startsWith(n.href),
            )
            .map((n) => {
              const active =
                path === n.href ||
                (!!n.children && path.startsWith(n.href + "/"));
              const opened = sections[n.href] ?? active;
              return (
                <div key={n.href} className="nav-group">
                  <Tip label={n.label}>
                    {n.children ? (
                      <button
                        className={"nav-link" + (active ? " selected" : "")}
                        aria-expanded={opened}
                        onClick={() => {
                          if (ui.collapsed) router.push(n.children![0][1]);
                          else
                            setSections((s) => ({ ...s, [n.href]: !opened }));
                        }}
                      >
                        <n.icon size={19} />
                        <span>{n.label}</span>
                        <ChevronDown
                          size={13}
                          className={opened ? "rotate" : ""}
                        />
                      </button>
                    ) : (
                      <Link
                        className={"nav-link" + (active ? " selected" : "")}
                        href={n.href}
                        aria-current={active ? "page" : undefined}
                      >
                        <n.icon size={19} />
                        <span>{n.label}</span>
                      </Link>
                    )}
                  </Tip>
                  {n.children && opened && !ui.collapsed && (
                    <div className="nav-children">
                      {n.children.map(([label, href]) => (
                        <Link
                          key={href}
                          href={href}
                          className={path === href ? "active" : ""}
                          aria-current={path === href ? "page" : undefined}
                        >
                          {label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          <button
            className="nav-link"
            onClick={() => setSpecialists(!specialists)}
            aria-expanded={specialists}
          >
            <LayersIcon size={19} />
            <span>Specialist workspaces</span>
            <ChevronDown size={13} />
          </button>
        </nav>
        <div className="sidebar-footer">
          <Link href="/ai-copilot" className="assistant-callout">
            <Sparkles size={19} />
            <strong>AI Assistant</strong>
            <span>Investigate your financial data.</span>
            <kbd>Context aware</kbd>
          </Link>
          <small>Mr Auditor · Global audit platform</small>
        </div>
      </aside>
      <main id="main-content" className="workspace">
        {authError && (
          <div className="error" role="alert">
            {authError}
          </div>
        )}
        <ErrorState
          error={
            access.error ||
            directory.clients.error ||
            directory.entities.error ||
            directory.periods.error
          }
        />
        {access.isLoading ? (
          <Loading />
        ) : access.error ? null : !tenants.data?.length ? (
          <Empty title="No active firm membership">
            Contact your firm administrator.
          </Empty>
        ) : (
          children
        )}
      </main>
      <CommandPalette open={command} onOpenChange={setCommand} />
      <Modal
        open={notifications}
        onOpenChange={setNotifications}
        title="Notification center"
      >
        <Empty title="No notification service configured">
          Job state is available in the relevant import or analytics workflow.
          Compliance alerts arrive with Phase 5.
        </Empty>
      </Modal>
    </div>
  );
}
function EngagementSwitcher() {
  const access = useAccess(),
    router = useRouter(),
    path = usePathname();
  const q = useAPI<Page<RecordRow>>(
    "engagements?limit=100",
    !!access.data?.permissions.includes("engagements.read"),
  );
  return (
    <label>
      <select
        aria-label="Select engagement"
        value={path.startsWith("/engagements/") ? path.split("/")[2] : ""}
        onChange={(e) => {
          if (e.target.value)
            router.push(`/engagements/${e.target.value}/workspace`);
        }}
      >
        <option value="">Select engagement</option>
        {q.data?.items.map((e) => (
          <option key={String(e.id)} value={String(e.id)}>
            {String(e.name)}
          </option>
        ))}
      </select>
    </label>
  );
}

function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [search, setSearch] = useState("");
  const value = useDebounced(search);
  const scope = useScope();
  const access = useAccess();
  const router = useRouter();
  const dir = useDirectory();
  const accounts = useAPI<Page<RecordRow>>(
    "accounting/accounts?" + qs({ entity_id: scope.entity, limit: 100 }),
    open &&
      !!scope.entity &&
      !!access.data?.permissions.includes("accounting.read"),
  );
  const engagements = useAPI<Page<RecordRow>>(
    "engagements?" + qs({ search: value, limit: 20 }),
    open && !!access.data?.permissions.includes("engagements.read"),
  );
  const navigate = (href: string) => {
    router.push(href);
    onOpenChange(false);
  };
  const universal = useAPI<{
    items: { id: string; category: string; label: string; url: string }[];
    truncated: boolean;
  }>(
    `jurisdictions/search?${qs({ q: value, country: scope.country })}`,
    open && !!value,
  );
  return (
    <Modal
      title="Search your workspace"
      open={open}
      onOpenChange={onOpenChange}
    >
      <div className="command-input">
        <Command size={18} />
        <input
          aria-label="Command search"
          placeholder="Search pages, clients, accounts, engagements…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              document
                .querySelector<HTMLButtonElement>(".command-results button")
                ?.focus();
            }
          }}
        />
      </div>
      <div
        className="command-results"
        role="toolbar"
        aria-label="Search results"
        tabIndex={-1}
        onKeyDown={(e) => {
          if (["ArrowDown", "ArrowUp"].includes(e.key)) {
            e.preventDefault();
            const buttons = Array.from(
              e.currentTarget.querySelectorAll("button"),
            );
            const index = buttons.indexOf(
              document.activeElement as HTMLButtonElement,
            );
            buttons[
              (index + (e.key === "ArrowDown" ? 1 : -1) + buttons.length) %
                buttons.length
            ]?.focus();
          }
        }}
      >
        {universal.data?.items.map((r) => (
          <button key={r.category + r.id} onClick={() => navigate(r.url)}>
            {r.label}
            <kbd>{r.category}</kbd>
          </button>
        ))}
        {navigation
          .filter((n) => access.data?.permissions.includes(n.permission))
          .flatMap((n) =>
            n.children
              ? n.children.map(([label, href]) => ({ label, href }))
              : [n],
          )
          .filter((n) => n.label.toLowerCase().includes(value.toLowerCase()))
          .map((n) => (
            <button key={n.href} onClick={() => navigate(n.href)}>
              <Search size={14} />
              {n.label}
              <kbd>Navigate</kbd>
            </button>
          ))}
        {dir.clients.data
          ?.filter(
            (c) => value && c.name.toLowerCase().includes(value.toLowerCase()),
          )
          .slice(0, 10)
          .map((c) => (
            <button
              key={c.id}
              onClick={() => {
                scope.setClient(c.id);
                navigate("/clients");
              }}
            >
              {c.name}
              <kbd>Select client</kbd>
            </button>
          ))}
        {accounts.data?.items
          .filter(
            (a) =>
              value &&
              `${a.code} ${a.name}`.toLowerCase().includes(value.toLowerCase()),
          )
          .slice(0, 10)
          .map((a) => (
            <button
              key={a.id}
              onClick={() =>
                navigate("/financials/general-ledger?account=" + a.id)
              }
            >
              {String(a.code)} · {String(a.name)}
              <kbd>Account ledger</kbd>
            </button>
          ))}
        {engagements.data?.items
          .filter(() => !!value)
          .map((e) => (
            <button key={e.id} onClick={() => navigate("/engagements/" + e.id)}>
              {String(e.name)}
              <kbd>Engagement</kbd>
            </button>
          ))}
      </div>
      <small className="subtle">
        Account search covers the first 100 accounts in the selected entity. Use
        the financial grid for the complete directory.
      </small>
    </Modal>
  );
}

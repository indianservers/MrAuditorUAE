"use client";
import {
  FinancialDataGrid,
  column,
} from "@/components/grids/financial-data-grid";
import {
  Button,
  Drawer,
  Empty,
  ErrorState,
  Facts,
  Modal,
  Pagination,
  QueryState,
  Status,
} from "@/components/ui/primitives";
import { useAPI, useAction, useCan, useDebounced } from "@/hooks/use-api";
import { qs } from "@/lib/api/client";
import { useScope } from "@/stores/workspace";
import type {
  Client,
  Engagement,
  Entity,
  Page,
  Period,
  RecordRow,
} from "@/types/models";
import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, ExternalLink, Pencil, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { PageHeader } from "./shared";
const schema = z.object({
  code: z
    .string()
    .min(1)
    .max(40)
    .regex(/^[A-Za-z0-9_-]+$/),
  name: z.string().min(1).max(200),
  kind: z.enum(["company", "group", "individual"]),
  status: z.enum(["active", "inactive", "archived"]),
});
type Form = z.infer<typeof schema>;
export function Clients() {
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Client | null>(null),
    [editing, setEditing] = useState<Client | null>(null),
    [form, setForm] = useState(false);
  const debounced = useDebounced(search);
  const q = useAPI<Page<Client>>(
    "clients?" + qs({ search: debounced, status, offset, limit: 50 }),
  );
  const can = useCan("clients.write");
  const scope = useScope();
  return (
    <>
      <PageHeader
        eyebrow="Firm workspace"
        title="Client & Company Management"
        description="Manage your client portfolio, legal entities and engagements."
        actions={
          can && (
            <Button
              primary
              onClick={() => {
                setEditing(null);
                setForm(true);
              }}
            >
              <Plus size={15} /> Add client
            </Button>
          )
        }
      />
      <div className="page-body directory-page">
        <div className="tabs">
          <span className="active">All clients {q.data?.total ?? ""}</span>
          <span>Authorized firm directory</span>
        </div>
        <div className="toolbar">
          <label className="search-field">
            <Search size={15} />
            <input
              aria-label="Search clients"
              placeholder="Search clients by name or code…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <select
            aria-label="Client status filter"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {["active", "inactive", "archived"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <span className="subtle">
            Tax IDs, industry and deadlines: not configured
          </span>
        </div>
        <FinancialDataGrid
          name="clients"
          rows={(q.data?.items || []) as unknown as RecordRow[]}
          loading={q.isLoading}
          error={q.error}
          onSelect={(r) => setSelected(r as unknown as Client)}
          columns={[
            column("code", "Client code", 130, { pinned: "left" }),
            column("name", "Client / company", 300, {
              cellRenderer: (p: { value: string }) => (
                <span className="client-cell">
                  <Building2 size={16} />
                  <strong>{p.value}</strong>
                </span>
              ),
            }),
            column("kind", "Client type", 130),
            column("status", "Status", 140, {
              cellRenderer: (p: { value: string }) => (
                <Status value={p.value} />
              ),
            }),
            column("updated_at", "Last activity", 195, {
              valueFormatter: (p) => new Date(String(p.value)).toLocaleString(),
            }),
            column("version", "Version", 100),
          ]}
        />
        <Pagination
          offset={offset}
          total={q.data?.total || 0}
          limit={50}
          onChange={setOffset}
        />
      </div>
      <Drawer
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title={selected?.name || "Client details"}
      >
        {selected && (
          <>
            <Facts
              data={{
                code: selected.code,
                kind: selected.kind,
                status: selected.status,
                version: selected.version,
              }}
            />
            <div className="actions">
              <Button
                primary
                onClick={() => {
                  scope.setClient(selected.id);
                  setSelected(null);
                }}
              >
                Use this client context
              </Button>
              {can && (
                <Button
                  onClick={() => {
                    setEditing(selected);
                    setForm(true);
                  }}
                >
                  <Pencil size={14} /> Edit client
                </Button>
              )}
            </div>
            <ClientRelations client={selected} />
          </>
        )}
      </Drawer>
      <Modal
        title={editing ? "Edit client" : "Create client"}
        open={form}
        onOpenChange={setForm}
      >
        <ClientForm
          key={editing?.id || "new"}
          client={editing}
          onDone={() => {
            setForm(false);
            setSelected(null);
          }}
        />
      </Modal>
    </>
  );
}
function ClientForm({
  client,
  onDone,
}: {
  client: Client | null;
  onDone: () => void;
}) {
  const action = useAction();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: client?.code || "",
      name: client?.name || "",
      kind: client?.kind || "company",
      status: client?.status || "active",
    },
  });
  return (
    <form
      className="resource-form"
      onSubmit={handleSubmit((values) =>
        action.mutate(
          {
            path: "clients" + (client ? "/" + client.id : ""),
            method: client ? "PATCH" : "POST",
            body: client
              ? {
                  name: values.name,
                  status: values.status,
                  version: client.version,
                }
              : values,
          },
          { onSuccess: onDone },
        ),
      )}
    >
      {(["code", "name", "kind", "status"] as const).map((field) => (
        <label key={field}>
          {field}
          {["kind", "status"].includes(field) ? (
            <select
              {...register(field)}
              disabled={field === "kind" && !!client}
            >
              {(field === "kind"
                ? ["company", "group", "individual"]
                : ["active", "inactive", "archived"]
              ).map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          ) : (
            <input
              {...register(field)}
              disabled={field === "code" && !!client}
            />
          )}
          <small role={errors[field] ? "alert" : undefined}>
            {errors[field]?.message}
          </small>
        </label>
      ))}
      <ErrorState error={action.error} />
      <Button primary disabled={action.isPending}>
        {action.isPending ? "Saving…" : "Save client"}
      </Button>
    </form>
  );
}
export function ResourceForm({
  path,
  fields,
  base = {},
  onDone,
}: {
  path: string;
  fields: {
    name: string;
    label: string;
    options?: string[];
    type?: string;
    value?: string;
    optional?: boolean;
  }[];
  base?: Record<string, unknown>;
  onDone: () => void;
}) {
  const action = useAction();
  const { register, handleSubmit } = useForm<Record<string, string>>({
    defaultValues: Object.fromEntries(
      fields.map((f) => [f.name, f.value || f.options?.[0] || ""]),
    ),
  });
  return (
    <form
      className="resource-form"
      onSubmit={handleSubmit((values) =>
        action.mutate(
          {
            path,
            body: {
              ...base,
              ...Object.fromEntries(
                Object.entries(values).filter(([, v]) => v !== ""),
              ),
            },
          },
          { onSuccess: onDone },
        ),
      )}
    >
      {fields.map((f) => (
        <label key={f.name}>
          {f.label}
          {f.options ? (
            <select {...register(f.name)}>
              {f.options.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              type={f.type || "text"}
              required={!f.optional}
              maxLength={200}
              {...register(f.name)}
            />
          )}
        </label>
      ))}
      <ErrorState error={action.error} />
      <Button primary disabled={action.isPending}>
        Save
      </Button>
    </form>
  );
}
function ClientRelations({ client }: { client: Client }) {
  const entities = useAPI<Page<Entity>>(
    "workspace/directory?" + qs({ client_id: client.id }),
  );
  const can = useCan("entities.write");
  const [form, setForm] = useState(false);
  return (
    <>
      <div className="section-heading">
        <h3>Legal entities</h3>
        {can && (
          <Button onClick={() => setForm(true)}>
            <Plus size={13} /> Entity
          </Button>
        )}
      </div>
      <QueryState query={entities}>
        {entities.data?.items.length ? (
          entities.data.items.map((e) => (
            <section className="card" key={e.id}>
              <h3>{e.name}</h3>
              <Facts
                data={{
                  country: e.country,
                  jurisdiction: e.jurisdiction,
                  currency: e.functional_currency,
                  status: e.status,
                }}
              />
              <EntityRelations entity={e} />
            </section>
          ))
        ) : (
          <Empty title="No legal entities" />
        )}
      </QueryState>
      <p className="subtle">
        Related-entity ownership and tax registration metadata are unavailable
        in the current API.
      </p>
      <Modal open={form} onOpenChange={setForm} title="Add legal entity">
        <ResourceForm
          path="entities"
          base={{ client_id: client.id }}
          fields={[
            { name: "name", label: "Legal name" },
            { name: "country", label: "ISO country", value: "AE" },
            {
              name: "jurisdiction",
              label: "Jurisdiction",
              value: "United Arab Emirates",
            },
            {
              name: "functional_currency",
              label: "Functional currency",
              value: "AED",
            },
            {
              name: "presentation_currency",
              label: "Presentation currency",
              value: "AED",
            },
          ]}
          onDone={() => setForm(false)}
        />
      </Modal>
    </>
  );
}
function EntityRelations({ entity }: { entity: Entity }) {
  const periods = useAPI<Page<Period>>(
    "workspace/directory?" +
      qs({ client_id: entity.client_id, entity_id: entity.id }),
  );
  const engagements = useAPI<Page<Engagement>>(
    "engagements?limit=100",
    useCan("engagements.read"),
  );
  const [form, setForm] = useState<"period" | "engagement" | null>(null);
  const periodWrite = useCan("entities.write"),
    engagementWrite = useCan("engagements.write");
  return (
    <>
      <div className="actions">
        {periodWrite && (
          <Button onClick={() => setForm("period")}>
            Add financial period
          </Button>
        )}
        {engagementWrite && (
          <Button onClick={() => setForm("engagement")}>Add engagement</Button>
        )}
      </div>
      <h4>Financial periods</h4>
      {periods.data?.items.map((p) => (
        <p key={p.id}>
          {p.start_date} – {p.end_date}
        </p>
      ))}
      <h4>Engagements</h4>
      {engagements.data?.items
        .filter((e) => e.entity_id === entity.id)
        .map((e) => (
          <Link className="list-link" key={e.id} href={"/engagements/" + e.id}>
            {e.name}
            <ExternalLink size={13} />
          </Link>
        ))}
      <Modal
        open={!!form}
        onOpenChange={(v) => {
          if (!v) setForm(null);
        }}
        title={
          form === "period" ? "Create financial period" : "Create engagement"
        }
      >
        <ResourceForm
          path={form === "period" ? "financial-periods" : "engagements"}
          base={{ entity_id: entity.id }}
          fields={
            form === "period"
              ? [
                  { name: "start_date", label: "Start date", type: "date" },
                  { name: "end_date", label: "End date", type: "date" },
                ]
              : [
                  { name: "name", label: "Engagement name" },
                  {
                    name: "engagement_type",
                    label: "Engagement type",
                    options: [
                      "External Audit",
                      "Internal Audit",
                      "IFRS Review",
                      "Corporate Tax",
                      "VAT",
                      "Transfer Pricing",
                      "Pillar Two",
                      "General Compliance",
                    ],
                  },
                ]
          }
          onDone={() => setForm(null)}
        />
      </Modal>
    </>
  );
}

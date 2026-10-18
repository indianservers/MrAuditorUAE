"use client";
import { api, qs } from "@/lib/api/client";
import { useScope } from "@/stores/workspace";
import type {
  Access,
  Client,
  Entity,
  Page,
  Period,
  RecordRow,
} from "@/types/models";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
export function useAccess() {
  const tenant = useScope((s) => s.tenant);
  return useQuery({
    queryKey: ["access", tenant],
    enabled: !!tenant,
    queryFn: ({ signal }) =>
      api<Access>("workspace/access", { signal }, tenant),
  });
}
export function useCan(permission: string) {
  return useAccess().data?.permissions.includes(permission) || false;
}
export function useAPI<T>(path: string, enabled = true, poll = false) {
  const tenant = useScope((s) => s.tenant);
  return useQuery({
    queryKey: ["api", tenant, path],
    enabled: !!tenant && enabled,
    queryFn: ({ signal }) => api<T>(path, { signal }, tenant),
    refetchInterval: poll
      ? (query) => {
          const status = String(
            (query.state.data as { status?: unknown } | undefined)?.status,
          );
          return [
            "completed",
            "failed",
            "cancelled",
            "active",
            "validated",
          ].includes(status)
            ? false
            : 2000;
        }
      : false,
  });
}
export function useAction<T = RecordRow>() {
  const tenant = useScope((s) => s.tenant);
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      body,
      method = "POST",
    }: {
      path: string;
      body?: unknown;
      method?: string;
    }) =>
      api<T>(
        path,
        {
          method,
          body:
            body instanceof FormData
              ? body
              : body === undefined
                ? undefined
                : JSON.stringify(body),
        },
        tenant,
      ),
    onSuccess: (data) => {
      const status = String(
        (data as { status?: unknown } | undefined)?.status || "",
      );
      window.dispatchEvent(
        new CustomEvent("auditos:notice", {
          detail:
            status === "failed"
              ? "The backend returned a failed result. Review the execution details."
              : "Request accepted by the backend. Review its current state in this workflow.",
        }),
      );
      if (typeof BroadcastChannel !== "undefined") {
        const channel = new BroadcastChannel("auditos:changes");
        channel.postMessage({ tenant });
        channel.close();
      }
      return Promise.all([
        client.invalidateQueries({ queryKey: ["api", tenant] }),
        client.invalidateQueries({ queryKey: ["access", tenant] }),
      ]);
    },
  });
}
async function metadata<T>(path: string, tenant: string, signal: AbortSignal) {
  const items: T[] = [];
  let offset = 0;
  for (;;) {
    const page = await api<Page<T>>(
      path + (path.includes("?") ? "&" : "?") + qs({ offset, limit: 100 }),
      { signal },
      tenant,
    );
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || !page.items.length) return items;
  }
}
export function useDirectory() {
  const { tenant, client, entity } = useScope();
  const access = useAccess();
  const allowed = access.data?.permissions || [];
  const clients = useQuery({
    queryKey: ["api", tenant, "directory-clients"],
    enabled: !!tenant && allowed.includes("clients.read"),
    queryFn: ({ signal }) => metadata<Client>("clients", tenant, signal),
  });
  const entities = useQuery({
    queryKey: ["api", tenant, "directory-entities", client],
    enabled: !!tenant && !!client && allowed.includes("entities.read"),
    queryFn: ({ signal }) =>
      metadata<Entity>(
        "workspace/directory?" + qs({ client_id: client }),
        tenant,
        signal,
      ),
  });
  const periods = useQuery({
    queryKey: ["api", tenant, "directory-periods", client, entity],
    enabled: !!entity && allowed.includes("entities.read"),
    queryFn: ({ signal }) =>
      metadata<Period>(
        "workspace/directory?" + qs({ client_id: client, entity_id: entity }),
        tenant,
        signal,
      ),
  });
  return { clients, entities, periods };
}
export function usePopulation() {
  const scope = useScope();
  const canRead = useCan("accounting.read");
  const batches = useAPI<Page<RecordRow>>(
    "accounting/imports?" +
      qs({
        client_id: scope.client,
        entity_id: scope.entity,
        period_id: scope.period,
        sort: "-created_at",
        limit: 100,
      }),
    !!scope.period && canRead,
  );
  const committed =
    batches.data?.items.filter(
      (r) =>
        ["active", "superseded"].includes(String(r.status)) &&
        ["gl", "journals", "tb"].includes(String(r.kind)),
    ) || [];
  const chosen =
    committed.find((b) => b.id === scope.snapshot) ||
    committed.find((b) => b.status === "active");
  const detail = useAPI<RecordRow>(
    "accounting/imports/" + chosen?.id,
    !!chosen,
  );
  return {
    batches,
    committed,
    chosen,
    snapshot: detail.data?.snapshot_id as string | undefined,
    detail,
  };
}
export function useDebounced<T>(value: T, delay = 300) {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setResult(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return result;
}

export function useCurrency() {
  const entity = useScope((s) => s.entity);
  return (
    useDirectory().entities.data?.find((e) => e.id === entity)
      ?.functional_currency || "—"
  );
}

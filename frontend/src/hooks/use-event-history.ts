"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useAPI } from "@/hooks/use-api";
import { api } from "@/lib/api/client";
import { useScope } from "@/stores/workspace";

type EventPage<T> = { items: T[]; next_before?: string | null };

/** Keep a live head and a contiguous history; older pages refresh on invalidation. */
export function useEventHistory<T extends { id: string }>(
  prefix: string,
  enabled = true,
) {
  const tenant = useScope((state) => state.tenant);
  const path = `${prefix}/events?limit=100&newest=true`;
  const latest = useAPI<EventPage<T>>(path, enabled, true);
  const history = useInfiniteQuery({
    queryKey: ["api", tenant, `${prefix}/event-history`],
    enabled: !!tenant && enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api<EventPage<T>>(
        path + (pageParam ? `&before=${encodeURIComponent(pageParam)}` : ""),
        { signal },
        tenant,
      ),
    getNextPageParam: (page) => page.next_before || undefined,
  });
  // Retain the history head too: new events can push boundary rows out of the
  // live page. On invalidation, infinite-query rebuilds the whole cursor chain.
  const pages = [latest.data, ...(history.data?.pages || [])];
  const byId = new Map<string, T>();
  for (const page of pages)
    for (const item of page?.items || [])
      if (!byId.has(item.id)) byId.set(item.id, item);
  const first = latest.data || history.data?.pages[0];
  return {
    ...latest,
    data: first ? { ...first, items: [...byId.values()] } : undefined,
    error: latest.error || history.error || null,
    loadingOlder: history.isFetching,
    hasOlder: enabled && (history.isError || history.hasNextPage),
    loadOlder: () => {
      if (!enabled || history.isFetching) return;
      if (history.isError && !history.isFetchNextPageError)
        void history.refetch();
      else void history.fetchNextPage();
    },
  };
}

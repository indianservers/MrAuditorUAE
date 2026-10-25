import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { useEventHistory } from "@/hooks/use-event-history";

const state = vi.hoisted(() => ({
  tenant: "tenant-a",
  latest: {
    items: [{ id: "new", freshness: "CURRENT" }],
    next_before: "boundary" as string | null,
  },
  fetch: vi.fn(),
}));
vi.mock("@/hooks/use-api", () => ({
  useAPI: () => ({ data: state.latest, error: null }),
}));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (value: { tenant: string }) => unknown) =>
    select({ tenant: state.tenant }),
}));
vi.mock("@/lib/api/client", () => ({
  api: (path: string, ...args: unknown[]) =>
    path.includes("before=")
      ? state.fetch(path, ...args)
      : Promise.resolve(state.latest),
}));

function harness() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

beforeEach(() => {
  state.tenant = "tenant-a";
  state.latest = {
    items: [{ id: "new", freshness: "CURRENT" }],
    next_before: "boundary",
  };
  state.fetch.mockReset();
});

describe("event source history", () => {
  it("keeps the loaded boundary rows when live results push them off the newest page", async () => {
    state.fetch.mockResolvedValue({
      items: [{ id: "old" }],
      next_before: null,
    });
    const { client, wrapper } = harness();
    const { result, rerender } = renderHook(
      () => useEventHistory("intelligence/engagements/ae"),
      { wrapper },
    );
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.data?.items).toHaveLength(2));
    state.latest = {
      items: [{ id: "newer", freshness: "CURRENT" }],
      next_before: "new-boundary",
    };
    rerender();
    expect(result.current.data?.items.map((item) => item.id)).toEqual([
      "newer",
      "new",
      "old",
    ]);
    client.clear();
  });
  it("loads older sources on demand, prefers refreshed current versions and invalidates older choices", async () => {
    state.fetch.mockResolvedValue({
      items: [
        { id: "new", freshness: "STALE" },
        { id: "old", freshness: "CURRENT" },
      ],
      next_before: null,
    });
    const { client, wrapper } = harness();
    const { result, rerender } = renderHook(
      () =>
        useEventHistory<{ id: string; freshness: string }>(
          "intelligence/engagements/ae",
        ),
      { wrapper },
    );
    expect(state.fetch).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.data?.items).toHaveLength(2));
    expect(result.current.data?.items[0].freshness).toBe("CURRENT");
    expect(state.fetch.mock.calls[0][0]).toContain("before=boundary");
    expect(result.current.hasOlder).toBe(false);
    state.fetch.mockResolvedValue({
      items: [{ id: "old", freshness: "STALE" }],
      next_before: null,
    });
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["api", "tenant-a"] });
    });
    await waitFor(() =>
      expect(result.current.data?.items[1].freshness).toBe("STALE"),
    );
    state.latest = {
      items: [{ id: "different", freshness: "CURRENT" }],
      next_before: null,
    };
    state.tenant = "tenant-b";
    rerender();
    expect(result.current.data?.items.map((item) => item.id)).toEqual([
      "different",
    ]);
    client.clear();
  });

  it("keeps retry available after an older-page failure", async () => {
    state.fetch
      .mockRejectedValueOnce(new Error("Temporary source history failure"))
      .mockResolvedValueOnce({ items: [{ id: "old" }], next_before: null });
    const { client, wrapper } = harness();
    const { result } = renderHook(
      () => useEventHistory("intelligence/engagements/in"),
      { wrapper },
    );
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.data?.items.map((item) => item.id)).toEqual(["new"]);
    expect(result.current.hasOlder).toBe(true);
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.data?.items).toHaveLength(2));
    expect(result.current.error).toBeNull();
    client.clear();
  });

  it("continues past a page with no visible events and resets history on engagement change", async () => {
    state.fetch
      .mockResolvedValueOnce({ items: [], next_before: "next-authorized-scan" })
      .mockResolvedValueOnce({
        items: [{ id: "old-authorized" }],
        next_before: null,
      });
    const { client, wrapper } = harness();
    const { result, rerender } = renderHook(
      ({ prefix }) => useEventHistory(prefix),
      { initialProps: { prefix: "intelligence/engagements/ae" }, wrapper },
    );
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    expect(result.current.hasOlder).toBe(true);
    await waitFor(() => expect(result.current.loadingOlder).toBe(false));
    act(() => result.current.loadOlder());
    await waitFor(() => expect(result.current.data?.items).toHaveLength(2));
    rerender({ prefix: "intelligence/engagements/in" });
    expect(result.current.data?.items.map((item) => item.id)).toEqual(["new"]);
    client.clear();
  });
});

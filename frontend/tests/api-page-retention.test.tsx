import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { useAPI } from "@/hooks/use-api";

const state = vi.hoisted(() => ({ tenant: "tenant-a", fetch: vi.fn() }));
vi.mock("@/stores/workspace", () => ({
  useScope: (select: (value: { tenant: string; country: string }) => unknown) =>
    select({ tenant: state.tenant, country: "AE" }),
}));
vi.mock("@/lib/api/client", () => ({
  api: (...args: unknown[]) => state.fetch(...args),
}));

beforeEach(() => {
  state.tenant = "tenant-a";
  state.fetch
    .mockReset()
    .mockResolvedValueOnce({ id: "event-a", rows: ["first-page"] })
    .mockImplementation(() => new Promise(() => {}));
});

function harness() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

it.each(["result", "tenant", "disabled-option"])(
  "never retains another scope or without opt-in: %s",
  async (change) => {
    const { client, wrapper } = harness();
    const { result, rerender, unmount } = renderHook(
      ({ id, offset, keep }) =>
        useAPI<{ id: string; rows: string[] }>(
          `intelligence/engagements/e/events/${id}?offset=${offset}&limit=100`,
          true,
          false,
          keep,
        ),
      {
        wrapper,
        initialProps: {
          id: "event-a",
          offset: 0,
          keep: change !== "disabled-option",
        },
      },
    );
    await waitFor(() => expect(result.current.data?.id).toBe("event-a"));
    if (change === "tenant") state.tenant = "tenant-b";
    rerender({
      id: change === "result" ? "event-b" : "event-a",
      offset: 100,
      keep: change !== "disabled-option",
    });
    expect(result.current.data).toBeUndefined();
    expect(result.current.isPlaceholderData).toBe(false);
    unmount();
    client.clear();
  },
);

it("retains only the same result while the next page is pending, then replaces it with the actual page", async () => {
  let finish!: (value: { id: string; rows: string[] }) => void;
  state.fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { client, wrapper } = harness();
  const { result, rerender, unmount } = renderHook(
    ({ offset }) =>
      useAPI<{ id: string; rows: string[] }>(
        `intelligence/engagements/e/events/event-a?offset=${offset}&limit=100`,
        true,
        false,
        true,
      ),
    { wrapper, initialProps: { offset: 0 } },
  );
  await waitFor(() =>
    expect(result.current.data?.rows).toEqual(["first-page"]),
  );
  rerender({ offset: 100 });
  expect(result.current.data?.rows).toEqual(["first-page"]);
  expect(result.current.isPlaceholderData).toBe(true);
  await act(async () => finish({ id: "event-a", rows: ["actual-next-page"] }));
  await waitFor(() =>
    expect(result.current.data?.rows).toEqual(["actual-next-page"]),
  );
  expect(result.current.isPlaceholderData).toBe(false);
  unmount();
  client.clear();
});

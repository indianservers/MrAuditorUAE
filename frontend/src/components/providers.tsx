"use client";
import { ApiError } from "@/lib/api/client";
import * as Tooltip from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 300_000,
            refetchOnWindowFocus: false,
            retry: (n, error) =>
              n < 2 && (!(error instanceof ApiError) || error.status >= 500),
          },
          mutations: { retry: false },
        },
      }),
  );
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel("auditos:changes");
    channel.onmessage = (event: MessageEvent<{ tenant?: unknown }>) => {
      if (typeof event.data?.tenant !== "string") return;
      void client.invalidateQueries({ queryKey: ["api", event.data.tenant] });
      void client.invalidateQueries({
        queryKey: ["access", event.data.tenant],
      });
    };
    return () => channel.close();
  }, [client]);
  return (
    <QueryClientProvider client={client}>
      <Tooltip.Provider delayDuration={350}>
        {children}
        <ToastRegion />
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
function ToastRegion() {
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const show = (event: Event) => {
      setNotice((event as CustomEvent<string>).detail);
      clearTimeout(timer);
      timer = setTimeout(() => setNotice(""), 6000);
    };
    window.addEventListener("auditos:notice", show);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("auditos:notice", show);
    };
  }, []);
  return notice ? (
    <div className="toast" role="status">
      <span>{notice}</span>
      <button
        className="icon-button"
        aria-label="Dismiss notification"
        onClick={() => setNotice("")}
      >
        ×
      </button>
    </div>
  ) : null;
}

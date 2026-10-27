import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntelligenceExports } from "@/features/intelligence-exports";
import { api } from "@/lib/api/client";

const props = {
  tenant: "firm-a",
  prefix: "intelligence/engagements/eng-a",
  eventId: "result-a",
  filename: "country-workflow-result-a",
};
let downloads: { filename: string; href: string; attached: boolean }[];

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
  class DownloadURL extends URL {
    static createObjectURL = vi.fn(() => "blob:synthetic-export");
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", DownloadURL);
  downloads = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloads.push({
      filename: this.download,
      href: this.href,
      attached: this.isConnected,
    });
  });
});
afterEach(() => {
  cleanup();
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
async function press(format: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: `Export ${format}` }));
  });
}

describe("reviewable intelligence downloads", () => {
  it.each(["XLSX", "PDF", "DOCX"])(
    "downloads the requested %s bytes with tenant scope",
    async (format) => {
      vi.mocked(fetch).mockResolvedValue(
        new Response("SYNTHETIC-export-bytes"),
      );
      render(<IntelligenceExports {...props} />);
      await press(format);
      expect(fetch).toHaveBeenCalledTimes(1);
      const [url, init] = vi.mocked(fetch).mock.calls[0];
      expect(url).toBe(
        `/api/backend/${props.prefix}/events/result-a/export?format=${format.toLowerCase()}`,
      );
      expect(init).toMatchObject({
        credentials: "same-origin",
        cache: "no-store",
      });
      expect(new Headers(init?.headers).get("X-Tenant-ID")).toBe("firm-a");
      const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
      expect(await blob.text()).toBe("SYNTHETIC-export-bytes");
      expect(downloads).toEqual([
        {
          filename: `${props.filename}.${format.toLowerCase()}`,
          href: "blob:synthetic-export",
          attached: true,
        },
      ]);
      expect(document.querySelector("a[download]")).toBeNull();
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1000);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:synthetic-export");
      expect(
        screen.getByRole("button", { name: `Export ${format}` }),
      ).toBeEnabled();
    },
  );

  it("shows actionable unsupported-font guidance and its request reference without an attachment", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            message:
              "PDF font coverage is unavailable for U+4E2D; use the complete XLSX export",
            request_id: "unicode-ref",
          },
        }),
        { status: 422 },
      ),
    );
    render(<IntelligenceExports {...props} />);
    await press("PDF");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "use the complete XLSX export",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("unicode-ref");
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(downloads).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Export XLSX" })).toBeEnabled();
  });

  it("retains permission errors and handles a non-JSON outage without a fake file", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { message: "Denied" } }), {
          status: 403,
        }),
      )
      .mockResolvedValueOnce(
        new Response("upstream unavailable", { status: 503 }),
      );
    render(<IntelligenceExports {...props} />);
    await press("PDF");
    expect(screen.getByRole("alert")).toHaveTextContent("Access restricted");
    await press("XLSX");
    expect(screen.getByRole("alert")).toHaveTextContent("Request failed (503)");
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("blocks overlapping exports while a real response is pending", async () => {
    let complete!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValue(
      new Promise((resolve) => {
        complete = resolve;
      }),
    );
    render(<IntelligenceExports {...props} />);
    await press("PDF");
    expect(
      screen.getByRole("button", { name: "Preparing PDF…" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Export XLSX" }));
    fireEvent.click(screen.getByRole("button", { name: "Export DOCX" }));
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => complete(new Response("SYNTHETIC")));
    expect(downloads).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeEnabled();
  });

  it("cancels the old result on scope change even if the response ignores abort", async () => {
    let complete!: (value: Response) => void;
    vi.mocked(fetch)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          complete = resolve;
        }),
      )
      .mockResolvedValueOnce(new Response("SYNTHETIC-new-firm"));
    const view = render(
      <IntelligenceExports key="firm-a:result-a" {...props} />,
    );
    await press("PDF");
    const signal = vi.mocked(fetch).mock.calls[0][1]?.signal;
    view.rerender(
      <IntelligenceExports
        key="firm-b:result-b"
        {...props}
        tenant="firm-b"
        eventId="result-b"
        filename="new-result"
      />,
    );
    expect(signal?.aborted).toBe(true);
    await act(async () => complete(new Response("SYNTHETIC-old-firm")));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    await press("XLSX");
    expect(downloads.map((x) => x.filename)).toEqual(["new-result.xlsx"]);
    expect(
      new Headers(vi.mocked(fetch).mock.calls[1][1]?.headers).get(
        "X-Tenant-ID",
      ),
    ).toBe("firm-b");
  });

  it("refreshes an expired session before reading the binary attachment", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response("", { status: 200 }))
      .mockResolvedValueOnce(new Response("SYNTHETIC-after-refresh"));
    render(<IntelligenceExports {...props} />);
    await press("PDF");
    expect(vi.mocked(fetch).mock.calls[1]).toEqual([
      "/api/session/refresh",
      { method: "POST" },
    ]);
    expect(vi.mocked(fetch).mock.calls[2][0]).toBe(
      vi.mocked(fetch).mock.calls[0][0],
    );
    expect(downloads).toHaveLength(1);
  });

  it("keeps existing JSON and no-content API behavior", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "retained" })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api("clients", {}, "firm-a")).resolves.toEqual({
      id: "retained",
    });
    await expect(
      api("clients/retained", { method: "PATCH" }, "firm-a"),
    ).resolves.toBeUndefined();
  });

  it("shares one pending session refresh between JSON requests and downloads", async () => {
    let finishRefresh!: (value: Response) => void;
    const attempts = new Map<string, number>();
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/session/refresh")
        return new Promise((resolve) => {
          finishRefresh = resolve;
        });
      const count = (attempts.get(url) || 0) + 1;
      attempts.set(url, count);
      if (count === 1) return new Response("", { status: 401 });
      return new Response(
        url.endsWith("/clients")
          ? JSON.stringify({ id: "client" })
          : "SYNTHETIC-after-shared-refresh",
      );
    });
    render(<IntelligenceExports {...props} />);
    let jsonRead!: Promise<unknown>;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
      jsonRead = api("clients", {}, "firm-a");
    });
    expect(
      vi
        .mocked(fetch)
        .mock.calls.filter(([url]) => url === "/api/session/refresh"),
    ).toHaveLength(1);
    await act(async () => finishRefresh(new Response("")));
    await expect(jsonRead).resolves.toEqual({ id: "client" });
    expect(downloads).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(5);
  });
});

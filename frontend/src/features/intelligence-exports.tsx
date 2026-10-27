"use client";

import { useEffect, useRef, useState } from "react";
import { Button, ErrorState } from "@/components/ui/primitives";
import { apiResponse } from "@/lib/api/client";

const formats = ["xlsx", "pdf", "docx"] as const;
type Format = (typeof formats)[number];

/** Mount with a scope-specific key so changing results cancels an old download. */
export function IntelligenceExports({
  prefix,
  eventId,
  tenant,
  filename,
}: {
  prefix: string;
  eventId: string;
  tenant: string;
  filename: string;
}) {
  const [busy, setBusy] = useState<Format | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function download(format: Format) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(format);
    setError(null);
    try {
      const response = await apiResponse(
        `${prefix}/events/${eventId}/export?format=${format}`,
        { signal: controller.signal },
        tenant,
      );
      const blob = await response.blob();
      controller.signal.throwIfAborted();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${filename}.${format}`;
      document.body.append(anchor);
      try {
        anchor.click();
      } finally {
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(cause instanceof Error ? cause : new Error("Export failed"));
    } finally {
      request.current = null;
      setBusy(null);
    }
  }

  return (
    <>
      {formats.map((format) => (
        <Button
          key={format}
          disabled={busy !== null}
          onClick={() => download(format)}
        >
          {busy === format
            ? `Preparing ${format.toUpperCase()}…`
            : `Export ${format.toUpperCase()}`}
        </Button>
      ))}
      <span className="subtle">
        Use XLSX for complete source values. PDF and DOCX may abbreviate data.
      </span>
      <ErrorState error={error} />
    </>
  );
}

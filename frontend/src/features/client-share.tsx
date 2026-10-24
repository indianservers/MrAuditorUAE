"use client";
import { useEffect, useState } from "react";
import { Button, ErrorState } from "@/components/ui/primitives";
type Question = {
  title: string;
  question: string;
  due_date: string | null;
  expires_at: string;
  max_file_bytes: number;
  uploads_remaining: number;
  identity_status: string;
};
export function ClientShare({
  tenant,
  link,
}: {
  tenant: string;
  link: string;
}) {
  const [token, setToken] = useState("");
  const [question, setQuestion] = useState<Question | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [response, setResponse] = useState("");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState("");
  useEffect(() => {
    const secret = window.location.hash.slice(1);
    setToken(secret);
    const controller = new AbortController();
    fetch(`/api/collaboration/${tenant}/${link}`, {
      headers: { "X-Collaboration-Token": secret },
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "This client link is invalid, expired, revoked or its request has changed.",
          );
        setQuestion(await r.json());
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e);
      });
    return () => controller.abort();
  }, [tenant, link]);
  async function submit() {
    if (!question) return;
    setBusy(true);
    setError(null);
    try {
      if (file && file.size > question.max_file_bytes)
        throw new Error("Selected file exceeds this request's upload limit.");
      const data = new FormData();
      data.set("response", response);
      data.set("claimed_name", name);
      if (file) data.set("file", file);
      const result = await fetch(`/api/collaboration/${tenant}/${link}`, {
        method: "POST",
        headers: { "X-Collaboration-Token": token },
        body: data,
        credentials: "omit",
        cache: "no-store",
      });
      const value = await result.json();
      if (!result.ok)
        throw new Error(
          value.detail ||
            value.error?.message ||
            "Response could not be submitted.",
        );
      setReceipt(value.id);
      setResponse("");
      setFile(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main
      style={{
        maxWidth: 760,
        margin: "40px auto",
        padding: 24,
        border: "1px solid #d7e0ee",
        borderRadius: 12,
        background: "white",
        color: "#10213e",
      }}
    >
      <p>MR AUDITOR • CLIENT COLLABORATION</p>
      <h1>{question?.title || "Client document request"}</h1>
      <ErrorState error={error} />
      {question && (
        <>
          <p style={{ whiteSpace: "pre-wrap" }}>{question.question}</p>
          <p>
            Due: {question.due_date || "Not specified"} • Link expires{" "}
            {question.expires_at}
          </p>
          <p>
            This link grants access to this request only. Uploaded support and
            responses require auditor review.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
            style={{ display: "grid", gap: 16 }}
          >
            <label>
              Your name (claimed identity, not verified)
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
              />
            </label>
            <label>
              Response
              <textarea
                rows={6}
                required
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                maxLength={10000}
              />
            </label>
            <label>
              Supporting document (optional, maximum {question.max_file_bytes}{" "}
              bytes)
              <input
                type="file"
                disabled={!question.uploads_remaining}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <Button primary disabled={busy || !response.trim()} type="submit">
              {busy ? "Submitting…" : "Submit for auditor review"}
            </Button>
          </form>
          {receipt && (
            <p role="status">
              Received for review. Receipt: {receipt}. This does not approve the
              evidence or complete an audit procedure.
            </p>
          )}
        </>
      )}
    </main>
  );
}

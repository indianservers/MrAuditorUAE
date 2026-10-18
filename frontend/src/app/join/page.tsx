"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/primitives";
export default function Join() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <section className="login-brand">
        <div className="brand">
          AuditOS <small>UAE</small>
        </div>
        <div>
          <h1>Join your firm’s workspace.</h1>
          <p>
            Your administrator controls your organization and engagement access.
          </p>
        </div>
      </section>
      <section className="login-panel">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await api("/api/invitations", {
                method: "POST",
                body: JSON.stringify({ token, password }),
              });
              setToken("");
              setPassword("");
              setStatus(
                "Account activated. Sign in with your invited email address.",
              );
            } catch (e) {
              setStatus(e instanceof Error ? e.message : "Activation failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>Accept invitation</h2>
          <label>
            Invitation token
            <textarea
              required
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
          <label>
            Create password
            <input
              type="password"
              autoComplete="new-password"
              minLength={14}
              maxLength={128}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button primary disabled={busy}>
            Activate account
          </Button>
          {status && <p role="status">{status}</p>}
          <Link href="/login">Return to sign in</Link>
        </form>
      </section>
    </main>
  );
}

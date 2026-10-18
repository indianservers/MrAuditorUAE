"use client";
import { api } from "@/lib/api/client";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1).max(128),
  otp: z.string().regex(/^(?:[0-9]{6})?$/).optional(),
});
export default function Login() {
  const [error, setError] = useState("");
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  return (
    <main className="login">
      <section className="login-brand">
        <div className="brand">
          <span className="brand-mark">A</span> AuditOS <small>UAE</small>
        </div>
        <div>
          <span className="eyebrow">PRECISION. EVIDENCE. CONFIDENCE.</span>
          <h1>
            Your financial data.
            <br />A clearer perspective.
          </h1>
          <p>
            An integrated workspace for accounting intelligence and professional
            audit investigation.
          </p>
          <div className="login-proof">
            <ShieldCheck size={20} /> Tenant-scoped access · Evidence-led
            workflows
          </div>
        </div>
        <small>AuditOS UAE • Enterprise accounting intelligence</small>
      </section>
      <section className="login-form">
        <form
          onSubmit={handleSubmit(async (data) => {
            setError("");
            try {
              await api("/api/session", {
                method: "POST",
                body: JSON.stringify(data),
              });
              window.location.assign("/dashboard");
            } catch (e) {
              setError((e as Error).message);
            }
          })}
        >
          <span className="eyebrow">WELCOME BACK</span>
          <h2>Sign in to your workspace</h2>
          <p>Use your firm account to continue.</p>
          <label>
            Email address
            <input
              autoComplete="username"
              type="email"
              {...register("email")}
            />
          </label>
          {errors.email && <small role="alert">{errors.email.message}</small>}
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              {...register("password")}
            />
          </label>
          {errors.password && (
            <small role="alert">{errors.password.message}</small>
          )}
          <label>
            Authenticator code (if enabled)
            <input autoComplete="one-time-code" inputMode="numeric" maxLength={6} {...register("otp")} />
          </label>
          {errors.otp && <small role="alert">Enter a six digit code.</small>}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="button primary" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
            <ArrowRight size={16} />
          </button>
          <p className="subtle">
            Account access is managed by your firm administrator.
          </p>
          <a href="/security">Set up authenticator MFA</a>
        </form>
      </section>
    </main>
  );
}

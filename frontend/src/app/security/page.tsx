"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import Link from "next/link";

export default function Security() {
  const status = useQuery({queryKey:["mfa"], retry:false, queryFn:()=>api<{enabled:boolean;session_verified:boolean}>("auth/mfa")});
  const [password,setPassword]=useState("");
  const [code,setCode]=useState("");
  const [secret,setSecret]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  return <main className="operations-shell"><Link href="/dashboard">AuditOS UAE · Return to workspace</Link>
    <h1>Account security</h1><p>Use an authenticator app. Store your enrollment secret securely. Recovery requires a separately verified support process.</p>
    {status.isPending && <p role="status">Checking MFA status…</p>}
    {status.error && <p role="alert">{status.error.message}</p>}
    {status.data?.enabled && <p role="status">Authenticator enabled. This session is {status.data.session_verified?"verified":"not verified; sign in with a code"}.</p>}
    {status.data && !status.data.enabled && <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");try{
      if(!secret){const result=await api<{secret:string}>("auth/mfa/enroll",{method:"POST",body:JSON.stringify({password})});setSecret(result.secret);setPassword("");}
      else {await api("auth/mfa/confirm",{method:"POST",body:JSON.stringify({code})});setSecret("");window.location.assign("/login");}
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
      {!secret?<label>Current password<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} /></label>:<><p>Enter this key in your authenticator app:</p><code className="mfa-secret">{secret}</code><label>Authenticator code<input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" required maxLength={6} value={code} onChange={e=>setCode(e.target.value)} /></label></>}
      {error&&<p role="alert">{error}</p>}<button className="button primary" disabled={busy}>{busy?"Saving…":secret?"Verify and enable":"Begin enrollment"}</button>
    </form>}
  </main>;
}

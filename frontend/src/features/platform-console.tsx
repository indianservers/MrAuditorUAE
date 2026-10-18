"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api/client";

const areas=["overview","tenants","subscriptions","usage","services","incidents","security","releases","qa-center"];
type Tenant={id:string;name:string;status:string;subscription:null|{plan:string;status:string;version:number;limits:Record<string,number>;features:string[]};usage:{metric:string;quantity:number;period:string}[]};
type Result={items?:Tenant[];total?:number;runs?:{id:string;executed_at:string;results:Record<string,unknown>}[];[key:string]:unknown};

export function PlatformConsole({area}:{area:string}) {
  const [offset,setOffset]=useState(0);
  const [selected,setSelected]=useState<Tenant|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const result=useQuery({queryKey:["platform",area,offset],enabled:areas.includes(area),retry:false,queryFn:()=>api<Result>(`platform/${area}?offset=${offset}&limit=25`)});
  return <main className="operations-shell"><Link href="/dashboard">AuditOS UAE · Firm workspace</Link><h1>Platform operations</h1>
    <p>Operational metadata only. A separate operator grant and verified MFA are required. Client accounting and evidence access requires an explicit professional assignment.</p>
    <nav aria-label="Platform workspaces">{areas.map(item=><Link key={item} href={`/platform/${item}`} aria-current={item===area?"page":undefined}>{item.replace(/^./,s=>s.toUpperCase())}</Link>)}</nav>
    {!areas.includes(area)&&<p role="alert">Unknown operations workspace.</p>}
    <h2>{area.replace(/^./,s=>s.toUpperCase())}</h2>
    {result.isPending&&areas.includes(area)&&<p role="status">Loading operational records…</p>}
    {result.error&&<p role="alert">{result.error.message}</p>}
    {result.data&&<>
      {area==="qa-center"&&<section aria-label="Persisted QA campaign results">
        <p>Executed results from the isolated development campaign. Unexecuted and blocked checks remain explicit.</p>
        {!result.data.runs?.length&&<p>No campaign results have been recorded.</p>}
        {result.data.runs?.map(run=><article key={run.id}><h3>Run {new Date(run.executed_at).toLocaleString()}</h3>
          <dl>{Object.entries(run.results).filter(([,v])=>typeof v!=="object").map(([key,value])=><div key={key}><dt>{key.replaceAll("_"," ")}</dt><dd>{String(value)}</dd></div>)}</dl>
          <details><summary>Detailed execution evidence</summary><pre className="operations-result">{JSON.stringify(run.results,null,2)}</pre></details>
        </article>)}
      </section>}
      {Array.isArray(result.data.items)&&["overview","tenants","subscriptions","usage"].includes(area)?<>
        <div className="operations-table"><table><caption>Tenant operational metadata</caption><thead><tr><th scope="col">Tenant</th><th scope="col">Lifecycle</th><th scope="col">Subscription</th><th scope="col">Usage this month</th><th scope="col">Action</th></tr></thead><tbody>
          {result.data.items.map(tenant=><tr key={tenant.id}><th scope="row">{tenant.name}<small>{tenant.id}</small></th><td>{tenant.status}</td><td>{tenant.subscription?`${tenant.subscription.plan} · ${tenant.subscription.status}`:"Provisioning required"}</td><td>{tenant.usage.map(row=><p key={row.metric}>{row.metric}: {row.quantity}</p>)}</td><td><button className="button" onClick={()=>{setSelected(tenant);setError("");}}>Configure {tenant.name}</button></td></tr>)}
        </tbody></table></div>
        {!result.data.items.length&&<p>No tenant records on this page.</p>}
        <p>{result.data.total} tenants · Billing provider not configured. No payment processing or provider invoices.</p>
        <button className="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button> <button className="button" disabled={offset+25>=Number(result.data.total)} onClick={()=>setOffset(offset+25)}>Next</button>
      </>:area!=="qa-center"&&<pre className="operations-result">{JSON.stringify(result.data,null,2)}</pre>}
    </>}
    {selected&&<section aria-labelledby="subscription-heading"><h2 id="subscription-heading">Configure {selected.name}</h2><p>Changes take effect immediately. A downgrade retains records and prevents admissions beyond the new limits.</p>
      <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");const form=new FormData(e.currentTarget);try{
        const limits=JSON.parse(String(form.get("limits")));
        await api(`platform/tenants/${selected.id}/subscription`,{method:"PUT",body:JSON.stringify({plan:form.get("plan"),status:form.get("status"),valid_until:new Date(String(form.get("valid"))).toISOString(),grace_until:new Date(String(form.get("grace"))).toISOString(),features:String(form.get("features")).split(",").map(x=>x.trim()).filter(Boolean),limits,reason:form.get("reason"),expected_version:selected.subscription?.version||0})});setSelected(null);await result.refetch();
      }catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
        <label>Plan<select name="plan" defaultValue={selected.subscription?.plan||"Starter"}>{["Starter","Professional","Enterprise"].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Status<select name="status" defaultValue={selected.subscription?.status||"trial"}>{["trial","active","past_due","suspended","cancelled"].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Valid until (local time)<input required name="valid" type="datetime-local" /></label><label>Grace until (local time)<input required name="grace" type="datetime-local" /></label>
        <label>Enabled features (comma separated)<input name="features" defaultValue={selected.subscription?.features.join(",")||"accounting,audit"}/></label>
        <label>Quota configuration (JSON)<textarea required name="limits" rows={4} defaultValue={JSON.stringify(selected.subscription?.limits||{users:5,clients:10,ai_requests:100,ml_requests:0,storage_bytes:1073741824})}/></label>
        <label>Reason<input required minLength={10} maxLength={500} name="reason"/></label>
        {error&&<p role="alert">{error}</p>}<button className="button primary" disabled={busy}>{busy?"Saving…":"Apply subscription"}</button> <button className="button" type="button" onClick={()=>setSelected(null)}>Cancel</button>
      </form>
    </section>}
    <p><Link href="/security">Account security and MFA</Link></p>
  </main>;
}

export const schema = {
  version: "audit-features/1", names: ["log_amount", "credit_direction", "month_sin", "month_cos", "weekday", "month_end", "year_end", "round_thousands", "description_length", "currency_mismatch", "reversal_word", "manual_known", "manual_missing", "account_frequency_past", "counterparty_frequency_past", "amount_vs_past_mean"],
  unavailable: ["reliable posting time", "public holiday calendar", "tax mismatch without tax evidence", "document completeness", "posting user", "approved RP relationship at posting"],
};
export type Row = { id:string; journal:string; client:string; date:string; debit:number; credit:number; currency:string; functional_currency:string; description:string; account:string; counterparty?:string; manual?:boolean; label?:number; label_kind?:string; category?:number; account_name?:string; };
export function features(rows:Row[]):number[][] {
  const ordered=rows.map((r,i)=>({r,i})).sort((a,b)=>a.r.date.localeCompare(b.r.date)||a.r.journal.localeCompare(b.r.journal));
  const accounts=new Map<string,{n:number,sum:number}>(), parties=new Map<string,number>(), out:number[][]=Array(rows.length);
  // Update history only after each posting date: same-day order cannot introduce future peers.
  for(let start=0;start<ordered.length;){let end=start+1;while(end<ordered.length&&ordered[end].r.date===ordered[start].r.date)end++;
    for(let k=start;k<end;k++){const {r,i}=ordered[k], d=new Date(r.date+"T00:00:00Z"),m=d.getUTCMonth(),v=r.debit+r.credit,key=r.client+"/"+r.account,pkey=r.client+"/"+(r.counterparty||""),h=accounts.get(key); if(!Number.isFinite(v)||v<0||!Number.isFinite(d.getTime()))throw Error("Invalid accounting features");
      out[i]=[Math.log1p(v),r.credit>0?1:0,Math.sin(2*Math.PI*m/12),Math.cos(2*Math.PI*m/12),d.getUTCDay()/6,d.getUTCDate()===new Date(Date.UTC(d.getUTCFullYear(),m+1,0)).getUTCDate()?1:0,m===11&&d.getUTCDate()>=25?1:0,v>0&&v%1000===0?1:0,Math.min(r.description.length,1000)/1000,r.currency!==r.functional_currency?1:0,/revers/i.test(r.description)?1:0,r.manual===true?1:0,r.manual===undefined?1:0,Math.log1p(h?.n||0),Math.log1p(parties.get(pkey)||0),h?Math.log1p(v/(h.sum/h.n+1)):0];
    }
    for(let k=start;k<end;k++){const r=ordered[k].r,key=r.client+"/"+r.account,h=accounts.get(key)||{n:0,sum:0};h.n++;h.sum+=r.debit+r.credit;accounts.set(key,h);const pk=r.client+"/"+(r.counterparty||"");parties.set(pk,(parties.get(pk)||0)+1);}start=end;
  }return out;
}
export type Scaling={mean:number[],sd:number[]};
export function fit(x:number[][]):Scaling{if(!x.length)throw Error("Empty training set");const mean=x[0].map((_,j)=>x.reduce((a,r)=>a+r[j],0)/x.length);return {mean,sd:mean.map((m,j)=>Math.max(1e-6,Math.sqrt(x.reduce((a,r)=>a+(r[j]-m)**2,0)/x.length)))};}
export function transform(x:number[][],s:Scaling){return x.map(r=>{if(r.length!==s.mean.length||r.some(v=>!Number.isFinite(v)))throw Error("Feature schema mismatch");return r.map((v,j)=>Math.max(-10,Math.min(10,(v-s.mean[j])/s.sd[j])));});}
export function accountVector(name:string):number[]{const tokens=name.toLowerCase().split(/\W+/),v=Array(32).fill(0);for(const t of tokens){let h=2166136261;for(const c of t)h=Math.imul(h^c.charCodeAt(0),16777619);v[(h>>>0)%32]++;}return v;}

export const schema = {
  version: "audit-features/1", names: ["log_amount", "credit_direction", "month_sin", "month_cos", "weekday", "month_end", "year_end", "round_thousands", "description_length", "currency_mismatch", "reversal_word", "manual_known", "manual_missing", "account_frequency_past", "counterparty_frequency_past", "amount_vs_past_mean"],
  unavailable: ["reliable posting time", "public holiday calendar", "tax mismatch without tax evidence", "document completeness", "posting user", "approved RP relationship at posting"],
};
export type Row = { id:string; journal:string; client:string; date:string; debit:number; credit:number; currency:string; functional_currency:string; description:string; account:string; counterparty?:string; manual?:boolean; label?:number; label_kind?:string; category?:number; account_name?:string; };
export const accountSchema = {version: 'account-hash/1', dimensions: 32};
export function validateRows(input: unknown, maxRows = 10000, requireAccountName = false): Row[] {
  if (!Array.isArray(input) || input.length < 1 || input.length > maxRows) throw Error('Invalid row population size');
  const ids = new Set<string>();
  return input.map((value: unknown) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Invalid accounting row');
    const r = value as Record<string, unknown>;
    for (const field of ['id', 'journal', 'client', 'date', 'account', 'currency', 'functional_currency']) {
      if (typeof r[field] !== 'string' || !(r[field] as string).trim() || (r[field] as string).length > 200) throw Error('Missing or invalid row identity/currency/date');
    }
    if (ids.has(r.id as string)) throw Error('Duplicate source row ID');
    ids.add(r.id as string);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date as string) || !Number.isFinite(Date.parse(r.date as string)) || new Date(r.date as string).toISOString().slice(0,10) !== r.date) throw Error('Invalid accounting date');
    if (!/^[A-Z]{3}$/.test(r.currency as string) || !/^[A-Z]{3}$/.test(r.functional_currency as string)) throw Error('Invalid currency');
    for (const field of ['debit', 'credit']) if (typeof r[field] !== 'number' || !Number.isFinite(r[field]) || (r[field] as number) < 0) throw Error('Invalid debit/credit');
    if (r.description != null && (typeof r.description !== 'string' || r.description.length > 12000)) throw Error('Invalid description');
    if (r.counterparty != null && (typeof r.counterparty !== 'string' || r.counterparty.length > 200)) throw Error('Invalid counterparty');
    if (r.manual != null && typeof r.manual !== 'boolean') throw Error('Invalid manual flag');
    if (r.account_name != null && (typeof r.account_name !== 'string' || r.account_name.length > 1000)) throw Error('Invalid account name');
    if (requireAccountName && (typeof r.account_name !== 'string' || !r.account_name.trim())) throw Error('Account classifier requires account_name');
    if (r.category != null && (!Number.isInteger(r.category) || (r.category as number) < 0 || (r.category as number) > 4)) throw Error('Invalid account category');
    return {...r, description: r.description ?? '', counterparty:r.counterparty??undefined,
      manual:r.manual??undefined, account_name:r.account_name??undefined,
      category:r.category??undefined,label:r.label??undefined} as Row;
  });
}
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
export function transform(x:number[][],s:Scaling){if(!s || !Array.isArray(s.mean) || !Array.isArray(s.sd) || !s.mean.length || s.mean.length!==s.sd.length || s.mean.some(v=>!Number.isFinite(v)) || s.sd.some(v=>!Number.isFinite(v)||v<=0))throw Error('Invalid preprocessing scaler');return x.map(r=>{if(r.length!==s.mean.length||r.some(v=>!Number.isFinite(v)))throw Error("Feature schema mismatch");return r.map((v,j)=>Math.max(-10,Math.min(10,(v-s.mean[j])/s.sd[j])));});}
export function accountVector(name:string):number[]{const tokens=name.toLowerCase().split(/\W+/),v=Array(32).fill(0);for(const t of tokens){let h=2166136261;for(const c of t)h=Math.imul(h^c.charCodeAt(0),16777619);v[(h>>>0)%32]++;}return v;}

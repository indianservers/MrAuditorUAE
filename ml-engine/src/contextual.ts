/** Version 2: fixed train-only context, Unicode text, entity calendar. */
import type {Row} from './features.js';
import {validateRows} from './features.js';
export const journalTypes = ['sales','purchases','payroll','bank','accrual','prepayment','depreciation','reclassification','closing','other'] as const;
export const accountTypes = ['Assets','Liabilities','Equity','Income','Expenses'] as const;
export type ContextRow = Row & {period_end?:string; reversal_date?:string; source?:string; related_group?:string; split_date?:string; target?:string; split?:'train'|'validation'|'test'; label_origin?:'auditor_reviewed'|'synthetic';};
export type Preprocessor = {version:'contextual/2'; calendar:{working_days:number[]}; accounts:Record<string,number>; pairs:Record<string,number>; count:number; median:number[]; scale:number[]};
const tokens = (s:string) => s.normalize('NFKC').toLocaleLowerCase('en').match(/[\p{L}\p{N}]+/gu) ?? [];
export function textVector(text:string) {
 const out=Array<number>(32).fill(0);
 for(const token of tokens(text)){let h=2166136261;for(const c of token) h=Math.imul(h^c.codePointAt(0)!,16777619);out[(h>>>0)%32]++;}
 const norm=Math.hypot(...out)||1;return out.map(v=>v/norm);
}
const quantile=(a:number[],p:number)=>{const s=[...a].sort((a,b)=>a-b);return s[Math.floor((s.length-1)*p)]??0;};
export function observations(input:ContextRow[],checkLabels=false) {
 validateRows(input,250000);
 const groups=new Map<string,ContextRow[]>();
 for(const r of input){const key=r.client+'\0'+r.journal;groups.set(key,[...(groups.get(key)??[]),r]);}
 return [...groups.values()].map(lines=>{
  const first=lines[0];
  if(lines.some(r=>r.date!==first.date || r.split!==first.split || checkLabels&&(r.target!==first.target || r.label_origin!==first.label_origin))) throw Error('Conflicting journal context/labels');
  return {key:first.client+'/'+first.journal,first,lines,pair:[...new Set(lines.map(r=>r.account))].sort().join('|')};
 });
}
type Observation=ReturnType<typeof observations>[number];
function raw(o:Observation,p:Preprocessor){
 const r=o.first,date=new Date(r.date+'T00:00:00Z');
 const debit=o.lines.reduce((s,r)=>s+r.debit,0),credit=o.lines.reduce((s,r)=>s+r.credit,0);
 const period=r.period_end ? Date.parse(r.period_end+'T00:00:00Z') : NaN;
 const knownReversal=r.reversal_date ? Date.parse(r.reversal_date+'T00:00:00Z') : NaN;
 const reversal=knownReversal<=date.getTime()?knownReversal:NaN;
 if(r.period_end && !Number.isFinite(period) || r.reversal_date && !Number.isFinite(knownReversal))throw Error('Invalid contextual date');
 return [Math.log1p(debit),Math.log1p(credit),Math.log1p(debit+credit),o.lines.length,
  new Set(o.lines.map(r=>r.account)).size,
  ...[o.lines.reduce((s,r)=>s+(Object.hasOwn(p.accounts,r.account)?p.accounts[r.account]:0),0)/o.lines.length,Object.hasOwn(p.pairs,o.pair)?p.pairs[o.pair]:0].map(n=>-Math.log((n+1)/(p.count+1))),
  Number.isFinite(period)?Math.max(-366,Math.min(366,(period-date.getTime())/86400000)):0,
  Number.isFinite(reversal)?Math.max(-366,Math.min(366,(reversal-date.getTime())/86400000)):0,
  +!p.calendar.working_days.includes(date.getUTCDay()),+!r.period_end,+!Number.isFinite(reversal),
  +o.lines.some(r=>r.manual===undefined),+o.lines.some(r=>!r.counterparty),+o.lines.some(r=>!r.description),
  ...textVector(o.lines.map(r=>(r.account_name??'')+' '+r.description).join(' '))];
}
export function fitContext(rows:ContextRow[],workingDays=[1,2,3,4,5]):Preprocessor {
 if(!workingDays.length||workingDays.some(d=>!Number.isInteger(d)||d<0||d>6))throw Error('Invalid entity working calendar');
 if(rows.some(r=>r.split && r.split!=='train'))throw Error('Preprocessing must fit training data only');
 const obs=observations(rows);if(!obs.length)throw Error('Empty training context');
 const p:Preprocessor={version:'contextual/2',calendar:{working_days:[...workingDays]},accounts:Object.create(null),pairs:Object.create(null),count:obs.length,median:[],scale:[]};
 for(const o of obs){for(const a of new Set(o.lines.map(r=>r.account)))p.accounts[a]=(p.accounts[a]??0)+1;p.pairs[o.pair]=(p.pairs[o.pair]??0)+1;}
 const matrix=obs.map(o=>raw(o,p));
 p.median=matrix[0].map((_,j)=>quantile(matrix.map(r=>r[j]),.5));
 p.scale=matrix[0].map((_,j)=>Math.max(.1,quantile(matrix.map(r=>r[j]),.75)-quantile(matrix.map(r=>r[j]),.25)));
 return p;
}
export function transformContext(rows:ContextRow[],p:Preprocessor){
 if(p.version!=='contextual/2'||p.median.length!==47||p.scale.length!==47||p.scale.some(s=>!Number.isFinite(s)||s<=0))throw Error('Invalid contextual preprocessing artifact');
 return observations(rows,true).map(o=>({id:o.key,line_ids:o.lines.map(r=>r.id),target:o.first.target,label_origin:o.first.label_origin,
  values:raw(o,p).map((v,j)=>Math.max(-10,Math.min(10,(v-p.median[j])/p.scale[j])))}));
}
export function classificationMetrics(truth:number[],probabilities:number[][],classes:number,threshold=.6){
 const confusion=Array.from({length:classes},()=>Array<number>(classes).fill(0));let accepted=0,brier=0;
 truth.forEach((y,i)=>{const p=probabilities[i],pred=p.indexOf(Math.max(...p));if(y<0||y>=classes)throw Error('Unseen evaluation label');
  p.forEach((v,j)=>brier+=(v-+(j===y))**2);if(p[pred]>=threshold){confusion[y][pred]++;accepted++;}});
 const per_class=confusion.map((row,c)=>{const support=truth.filter(y=>y===c).length,tp=row[c],pred=confusion.reduce((s,r)=>s+r[c],0);
  const precision=pred?tp/pred:null,recall=support?tp/support:null;return {support,precision,recall,f1:precision!==null&&recall!==null?(precision+recall?2*precision*recall/(precision+recall):0):support?0:null};});
 const present=per_class.filter(c=>c.support>0);
 return {confusion,per_class,macro_f1:present.length?present.reduce((s,c)=>s+(c.f1??0),0)/present.length:null,coverage:truth.length?accepted/truth.length:0,abstention_rate:truth.length?1-accepted/truth.length:1,multiclass_brier:truth.length?brier/truth.length:null,probability_calibrated:false};
}

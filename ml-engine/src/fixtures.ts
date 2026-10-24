import {journalTypes,accountTypes,type ContextRow} from './contextual.js';
import type {Task} from './foundation.js';
export const sectors=['trading','professional-services','construction','real-estate','free-zone','group'] as const;
/** Deliberately simple synthetic labels, never evidence of real-client accuracy. */
export function syntheticPopulation(task:Task):ContextRow[]{
 const rows:ContextRow[]=[];
 for(let partition=0;partition<3;partition++)for(let i=0;i<(partition===0?120:40);i++){
  const split=(['train','validation','test'] as const)[partition],sector=sectors[i%sectors.length];
  const label=task==='journal-type'?journalTypes[i%journalTypes.length]:task==='account-mapping'?accountTypes[i%accountTypes.length]:i%10===0?'relevant_exception':'normal';
  const amount=i%10===0?100000+i:100+i,currency=i%4===0?'USD':'AED';
  for(let side=0;side<2;side++)rows.push({id:`${partition}-${i}-${side}`,journal:`${partition}-${i}`,client:`SYNTHETIC-${sector}`,date:`2026-${String(1+partition*4).padStart(2,'0')}-${String(1+i%25).padStart(2,'0')}`,
   debit:side===0?amount:0,credit:side===1?amount:0,currency,functional_currency:'AED',
   account:task==='account-mapping'?`${partition}-${i}-${label}-${side}`:`account-${i%7}-${side}`,account_name:`${label} حساب`,description:i%11===0?'':`${label} SYNTHETIC ${sector} قيد محاسبي`,
   manual:i%7===0?undefined:i%3===0,counterparty:i%8===0?undefined:`party-${i%9}`,target:label,split,label_origin:'synthetic',period_end:'2026-12-31',reversal_date:i%13===0?'2026-12-31':undefined});
 }
 return rows;
}

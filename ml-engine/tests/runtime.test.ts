import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve, dirname, basename} from 'node:path';
import * as tf from '@tensorflow/tfjs';
import {train, infer, type Dataset} from '../src/engine.js';
import {clearInferenceCache} from '../src/inference.js';
import {validateRows, transform} from '../src/features.js';
import type {Row} from '../src/features.js';

const row = (i=0) => ({id:'r'+i,journal:'j'+i,client:'tenant-synthetic-client',date:'2026-01-15',debit:100+i,credit:0,currency:'AED',functional_currency:'AED',description:'SYNTHETIC journal',account:'A1',label:i%2,label_kind:'synthetic_injected'});

test('local CPU training/inference, cache, schema and artifact failures without language credentials', async()=>{
 const dir=await mkdtemp(join(tmpdir(),'auditos-test-model-'));
 const initialTensors=tf.memory().numTensors;
 const prior=process.env.AI_API_KEY; const openai=process.env.OPENAI_API_KEY;
 delete process.env.AI_API_KEY; delete process.env.OPENAI_API_KEY;
 try {
  const rows=Array.from({length:120},(_,i)=>row(i));
  const split:Dataset['split']=rows.map((_,i)=>i<60?'train':i<80?'validation':i<100?'test':'ood');
  await train({rows,split,synthetic:true},{family:'journal-classifier',epochs:1,batch_size:16,learning_rate:.003,seed:2026,patience:1},dir);
  const first=await infer(rows.slice(100),dir);
  assert.equal(first.execution_mode,'trained_model');
  assert.equal(first.backend,'cpu');
  assert.equal(first.task_semantics,'binary_exception_review_signal');
  assert.equal(first.calibrated_probability,false);
  assert.equal(first.production_validated,false);
  const tensorCount=tf.memory().numTensors;
  for(let i=0;i<20;i++)assert.deepEqual((await infer(rows.slice(100),dir)).predictions,first.predictions);
  assert.equal(tf.memory().numTensors,tensorCount,'Repeated inference must not leak tensors');
  const nullable=await infer(rows.slice(100).map(r=>({...r,counterparty:null,manual:null,description:null})) as unknown as Row[],dir);
  assert.deepEqual(nullable.predictions[0].missing_optional_fields,['description','counterparty','manual']);
  const parallel=await Promise.all([infer(rows.slice(100),dir),infer(rows.slice(100),dir)]);
  assert.deepEqual(parallel[0].predictions,parallel[1].predictions);
  const burst=await Promise.allSettled(Array.from({length:12},()=>infer(rows.slice(100),dir)));
  assert.ok(burst.some(r=>r.status==='rejected'&&/queue capacity/.test(String(r.reason))));
  assert.equal(tf.memory().numTensors,tensorCount);
  const weights=await readFile(join(dir,'weights.bin'));
  const changed=Buffer.from(weights);changed[0]^=1;
  await writeFile(join(dir,'weights.bin'),changed);
  await assert.rejects(infer(rows.slice(100),dir),/Artifact integrity/);
  await writeFile(join(dir,'weights.bin'),weights);
  const metadata=await readFile(join(dir,'metadata.json'),'utf8');
  const m=JSON.parse(metadata);m.feature_schema.version='incompatible/99';
  await writeFile(join(dir,'metadata.json'),JSON.stringify(m));
  await assert.rejects(infer(rows.slice(100),dir),/feature version/);
  await writeFile(join(dir,'metadata.json'),metadata);
  await assert.rejects(infer([],dir),/population size/);
  await assert.rejects(infer(rows.slice(100),join(dir,'missing')),/ENOENT/);
 } finally {
  clearInferenceCache();
  assert.equal(tf.memory().numTensors,initialTensors,'Training plus cached inference must release all owned tensors');
  if(prior===undefined)delete process.env.AI_API_KEY;else process.env.AI_API_KEY=prior;
  if(openai===undefined)delete process.env.OPENAI_API_KEY;else process.env.OPENAI_API_KEY=openai;
  if(dirname(resolve(dir))!==resolve(tmpdir()) || !basename(dir).startsWith('auditos-test-model-')) throw Error('Unexpected test directory');
  await rm(dir,{recursive:true,force:true});
 }
});

test('canonical dates, missing fields, finite features and reviewed dimensions',()=>{
 assert.throws(()=>validateRows([{...row(),date:'2026-02-30'}]),/date/);
 assert.throws(()=>validateRows([{...row(),debit:NaN}]),/debit/);
 assert.throws(()=>validateRows([{...row(),debit:-1}]),/debit/);
 assert.throws(()=>validateRows([row(),row()]),/Duplicate/);
 assert.throws(()=>validateRows([{...row(),account_name:''}],10000,true),/account_name/);
 const missing={...row(),description:undefined};
 assert.equal(validateRows([missing])[0].description,'');
 assert.equal(validateRows([{...row(),counterparty:null,manual:null}])[0].manual,undefined);
 assert.throws(()=>transform([[1]],{mean:[0],sd:[0]}),/scaler/);
 assert.throws(()=>transform([[1]],{mean:[NaN],sd:[1]}),/scaler/);
});

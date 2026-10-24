import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile,writeFile} from 'node:fs/promises';
import {join,dirname,basename} from 'node:path';
import {tmpdir} from 'node:os';
import * as tf from '@tensorflow/tfjs';
import {fitContext,transformContext,textVector,classificationMetrics} from '../src/contextual.js';
import {trainFoundation,inferFoundation,clearFoundationCache,type Task} from '../src/foundation.js';
import {syntheticPopulation} from '../src/fixtures.js';

test('train-only contextual preprocessing is batch invariant and supports Arabic/calendar',()=>{
 const rows=syntheticPopulation('journal-type'),train=rows.filter(r=>r.split==='train'),testRows=rows.filter(r=>r.split==='test'),p=fitContext(train,[0,1,2,3,4]);
 assert.throws(()=>fitContext(rows),/training data/);assert.ok(textVector('مصروفات الرواتب').some(v=>v!==0));
 const before=JSON.stringify(p),all=transformContext(testRows,p),single=transformContext(testRows.slice(0,2),p);
 assert.deepEqual(all[0],single[0]);assert.equal(JSON.stringify(p),before);assert.equal(all[0].values.length,47);
 assert.throws(()=>fitContext(train,[7]),/calendar/);
 const mixedAccountLabels=train.map((r,i)=>({...r,target:i%2?'Assets':'Expenses'}));assert.doesNotThrow(()=>fitContext(mixedAccountLabels));
 const metrics=classificationMetrics([0,1],[[.5,.5],[.1,.9]],2,.6);assert.equal(metrics.coverage,.5);assert.equal(metrics.per_class[0].recall,0);
});

test('four local pipelines train, reload, abstain, reject leakage and preserve tensors',async()=>{
 const start=tf.memory().numTensors;
 for(const task of ['journal-type','account-mapping','journal-anomaly','review-ranking'] as Task[]){
  const dir=await mkdtemp(join(tmpdir(),'auditos-foundation-'));
  try{
   const rows=syntheticPopulation(task),m=await trainFoundation(rows,{task,epochs:2,seed:2026},dir);
   assert.equal(m.synthetic,true);assert.ok(m.threshold>0);
   const input=rows.filter(r=>r.split==='test').slice(0,20),result=await inferFoundation(input,dir);
   assert.equal(result.execution_mode,'trained_model');assert.equal(result.production_validated,false);
   if(task==='journal-type'||task==='account-mapping'){
    const baseline=await inferFoundation(input,dir,'statistical_baseline');assert.equal(baseline.execution_mode,'statistical_baseline');
    assert.ok(baseline.predictions.every(p=>p.fraud_probability===false));
   }
   const tensors=tf.memory().numTensors;
   for(let n=0;n<5;n++)assert.deepEqual((await inferFoundation(input,dir)).predictions,result.predictions);
   const concurrent=await Promise.all(Array.from({length:4},()=>inferFoundation(input,dir)));
   assert.ok(concurrent.every(r=>JSON.stringify(r.predictions)===JSON.stringify(result.predictions)));
   assert.equal(tf.memory().numTensors,tensors);
   const weights=await readFile(join(dir,'weights.bin'));await writeFile(join(dir,'weights.bin'),Buffer.from('corrupt'));
   await assert.rejects(inferFoundation(input,dir),/integrity/);await writeFile(join(dir,'weights.bin'),weights);
   const leaked=rows.map(r=>({...r,related_group:'all'}));await assert.rejects(trainFoundation(leaked,{task,epochs:1},dir),/leakage/);
  }finally{clearFoundationCache();if(dirname(dir)!==tmpdir()||!basename(dir).startsWith('auditos-foundation-'))throw Error('Unsafe cleanup');await rm(dir,{recursive:true});}
 }
 assert.equal(tf.memory().numTensors,start);
});

/** Reproducible local synthetic experiment. Does not establish real-client accuracy. */
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {cpus,totalmem} from 'node:os';
import * as tf from '@tensorflow/tfjs';
import {cpuStatus} from './inference.js';
import {trainFoundation,inferFoundation,clearFoundationCache,type Task} from './foundation.js';
import {syntheticPopulation,sectors} from './fixtures.js';
const directory=resolve(process.argv[2]??'../.local-runtime/ml-foundation-benchmark');
const reportPath=resolve(process.argv[3]??'../docs/ml-foundation/benchmark.json');
await mkdir(directory,{recursive:true});await mkdir(resolve(reportPath,'..'),{recursive:true});
const cold=performance.now();
const child=spawnSync(process.execPath,['--input-type=module','-e',"import('./dist/src/inference.js').then(async m=>{await m.initializeCPU();console.log(JSON.stringify(m.cpuStatus));})"],{cwd:process.cwd(),encoding:'utf8',timeout:30000});
if(child.status!==0)throw Error('Cold CPU initialization failed');
const coldMs=performance.now()-cold,experiments=[];
for(const task of ['journal-type','account-mapping','journal-anomaly','review-ranking'] as Task[]){
 const rows=syntheticPopulation(task),dir=join(directory,task),rssBefore=process.memoryUsage().rss,tensorBefore=tf.memory().numTensors;
 const trained=await trainFoundation(rows,{task,epochs:12,seed:2026},dir),test=rows.filter(r=>r.split==='test');
 const coldInference=performance.now();await inferFoundation(test,dir);const coldInferenceMs=performance.now()-coldInference;
 const warm=[];for(let i=0;i<20;i++){const start=performance.now();await inferFoundation(test,dir);warm.push(performance.now()-start);}
 // The backend protocol serializes requests. Measure that policy explicitly, without promising parallel CPU throughput.
 const concurrentStart=performance.now();let serial=Promise.resolve();
 await Promise.all(Array.from({length:4},()=>{serial=serial.then(async()=>{await inferFoundation(test,dir);});return serial;}));
 const concurrentMs=performance.now()-concurrentStart;
 const retained=tf.memory().numTensors;clearFoundationCache();
 experiments.push({task,source:'synthetic_only',sectors,rows:rows.length,test_lines:test.length,reload_max_delta:trained.reload_max_delta,training:trained.resources,selection:trained.selection,evaluation:trained.evaluation,
  cold_model_load_and_batch_ms:coldInferenceMs,warm_batch_ms:{min:Math.min(...warm),mean:warm.reduce((a,b)=>a+b,0)/warm.length,max:Math.max(...warm),iterations:warm.length},
  serialized_four_request_ms:concurrentMs,rss_before:rssBefore,rss_after:process.memoryUsage().rss,tensors_before:tensorBefore,tensors_cached:retained,tensors_after_disposal:tf.memory().numTensors});
}
await writeFile(reportPath,JSON.stringify({measured_at:new Date().toISOString(),environment:{node:process.version,platform:process.platform,architecture:process.arch,tfjs:tf.version.tfjs,cpu:cpuStatus,cpu_model:cpus()[0]?.model,logical_cpus:cpus().length,total_memory_bytes:totalmem()},
 cold_process_cpu_initialization_ms:coldMs,experiments,limits:['Synthetic mechanics and controlled experiments only','Labels are deliberately easy; these scores do not establish real-client performance','No held-out-entity generalization claim','RSS includes allocator retention; TensorFlow.js reports CPU memory estimates as unreliable','Times include shared-machine load and filesystem integrity checks']},null,2));
console.log(JSON.stringify({report:reportPath,experiments:experiments.length,cold_ms:coldMs}));

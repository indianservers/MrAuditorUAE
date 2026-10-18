import {readFile,writeFile} from 'node:fs/promises';
import * as tf from '@tensorflow/tfjs';
import os from 'node:os';
import {features,transform,type Row} from './features.js';
import {load} from './engine.js';
const [datasetPath,artifactDir,output]=process.argv.slice(2);
const data=JSON.parse(await readFile(datasetPath,'utf8')) as {rows:Row[]};const meta=JSON.parse(await readFile(artifactDir+'/metadata.json','utf8'));
await tf.setBackend('cpu');const start=performance.now(),model=await load(artifactDir,meta.artifact_hashes),loadSeconds=(performance.now()-start)/1000;const results=[];
for(const n of [10000,100000,250000]){const rows=data.rows.slice(0,n);if(rows.length!==n)continue;const cpu=process.cpuUsage(),begin=performance.now(),raw=features(rows),featureSeconds=(performance.now()-begin)/1000;const prep=performance.now(),x=transform(raw,meta.scaler),preprocessSeconds=(performance.now()-prep)/1000;const inference=performance.now();let predictions=0;for(let i=0;i<x.length;i+=1024){tf.tidy(()=>{const batch=tf.tensor2d(x.slice(i,i+1024));const p=model.predict(batch) as tf.Tensor;p.dataSync();predictions+=batch.shape[0];});}results.push({records:n,feature_seconds:featureSeconds,preprocess_seconds:preprocessSeconds,inference_seconds:(performance.now()-inference)/1000,predictions,rss_bytes:process.memoryUsage().rss,cpu_microseconds:process.cpuUsage(cpu)});}
model.dispose();await writeFile(output,JSON.stringify({runtime:{node:process.version,tfjs:tf.version.tfjs,backend:tf.getBackend(),cpu:os.cpus()[0]?.model,logical_cpus:os.cpus().length,total_memory_bytes:os.totalmem(),platform:os.platform()},model_load_seconds:loadSeconds,results,million_records:'Not run: only 263224 source/fixture rows available; no invented throughput',scope:'Local sequential pure JavaScript CPU, dense inference excluding DB/network. Memory is whole-process RSS.'},null,2));

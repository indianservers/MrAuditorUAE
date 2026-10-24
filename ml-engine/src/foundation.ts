import * as tf from '@tensorflow/tfjs';
import {mkdir,readFile,writeFile,stat} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {initializeCPU,cpuStatus} from './inference.js';
import {accountTypes,journalTypes,fitContext,transformContext,textVector,classificationMetrics,observations,type ContextRow,type Preprocessor} from './contextual.js';
export type Task='journal-type'|'account-mapping'|'journal-anomaly'|'review-ranking';
type Config={task:Task;epochs?:number;batch_size?:number;seed?:number;working_days?:number[]};
type Artifact={version:'local-foundation/2';config:Config & {family:string};task:Task;preprocessor:Preprocessor;taxonomy:readonly string[];centroids:number[][];threshold:number;weights_hash:string;model_hash:string;reload_max_delta:number;synthetic:boolean;dataset_hash:string;selection:unknown;evaluation:unknown;resources:unknown;};
const digest=(b:string|Uint8Array)=>createHash('sha256').update(b).digest('hex');
const loadedModels=new Map<string,tf.LayersModel>();
let activeInference=0,waitingInference=0,inferenceQueue=Promise.resolve();
export function clearFoundationCache(){if(activeInference||waitingInference)throw Error('Cannot clear active inference');for(const m of loadedModels.values())m.dispose();loadedModels.clear();}
function samples(rows:ContextRow[],p:Preprocessor,task:Task){
 if(task!=='account-mapping')return transformContext(rows,p);
 observations(rows);
 const groups=new Map<string,ContextRow[]>();
 for(const r of rows){const key=r.client+'/'+r.account;groups.set(key,[...(groups.get(key)??[]),r]);}
 return [...groups].map(([id,lines])=>{
  const targets=[...new Set(lines.map(r=>r.target))];if(targets.length!==1)throw Error('Conflicting account labels');
  const debit=lines.reduce((s,r)=>s+r.debit,0),credit=lines.reduce((s,r)=>s+r.credit,0),total=debit+credit;
  return {id,line_ids:lines.map(r=>r.id),target:targets[0],label_origin:lines.every(r=>r.label_origin==='auditor_reviewed')?'auditor_reviewed':lines.every(r=>r.label_origin==='synthetic')?'synthetic':undefined,
   values:[...textVector(lines.map(r=>(r.account_name??'')+' '+r.description).join(' ')),total?debit/total:0,total?credit/total:0,Math.log1p(lines.length)]};
 });
}
function verifySplits(rows:ContextRow[]){
 const groups=new Map<string,string>(),ranges=new Map<string,number[]>();
 for(const r of rows){if(!r.split||!['train','validation','test'].includes(r.split))throw Error('Explicit chronological split required');
  for(const key of [r.client+'/'+r.journal,...(r.related_group?[r.client+'/connected/'+r.related_group]:[])]){
   if(groups.has(key)&&groups.get(key)!==r.split)throw Error('Connected journal leakage');groups.set(key,r.split);}
  const t=Date.parse(r.split_date??r.date),a=ranges.get(r.split)??[];
  if(!Number.isFinite(t)||t<Date.parse(r.date))throw Error('Invalid connected chronological anchor');
  a.push(t);ranges.set(r.split,a);
 }
 for(const [a,b] of [['train','validation'],['validation','test']]){
  const left=ranges.get(a)??[],right=ranges.get(b)??[];
  if(!left.length||!right.length||left.reduce((a,b)=>Math.max(a,b),-Infinity)>right.reduce((a,b)=>Math.min(a,b),Infinity))throw Error('Chronological partitions overlap or are empty');
 }
}
const probabilities=(model:tf.LayersModel,x:number[][])=>tf.tidy(()=>Array.from((model.predict(tf.tensor2d(x)) as tf.Tensor).dataSync()));
const errors=(x:number[][],pred:number[])=>x.map((r,i)=>r.reduce((s,v,j)=>s+(v-pred[i*r.length+j])**2,0)/r.length);
function rankingQuality(truth:number[],scores:number[]){
 const ranked=scores.map((s,i)=>({s,y:truth[i]})).sort((a,b)=>b.s-a.s),positive=truth.filter(y=>y===1).length;
 return [.01,.05,.1].map(fraction=>{const capacity=Math.max(1,Math.ceil(truth.length*fraction)),top=ranked.slice(0,capacity),relevant=top.filter(r=>r.y===1).length;
  return {fraction,capacity,precision:relevant/capacity,recall:positive?relevant/positive:null,false_positive_count:capacity-relevant};});
}
function baseline(train:number[][],labels:number[],x:number[][],classes:number){
 const centers=Array.from({length:classes},(_,c)=>{const members=train.filter((_,i)=>labels[i]===c);return train[0].map((_,j)=>members.reduce((s,r)=>s+r[j],0)/(members.length||1));});
 return x.map(row=>{const distance=centers.map(c=>c.reduce((s,v,j)=>s+(v-row[j])**2,0));const nearest=distance.indexOf(Math.min(...distance));return centers.map((_,i)=>+(i===nearest));});
}
export async function trainFoundation(rows:ContextRow[],config:Config,dir:string){
 const started=performance.now(),cpu=process.cpuUsage();await initializeCPU();verifySplits(rows);
 const task=config.task;if(!['journal-type','account-mapping','journal-anomaly','review-ranking'].includes(task))throw Error('Unknown foundation task');
 const synthetic=rows.every(r=>r.label_origin==='synthetic');
 if(!rows.every(r=>r.label_origin===(synthetic?'synthetic':'auditor_reviewed')))throw Error('Reliable homogeneous label provenance required');
 const train=rows.filter(r=>r.split==='train'),validation=rows.filter(r=>r.split==='validation'),test=rows.filter(r=>r.split==='test');
 const p=fitContext(train,config.working_days),taxonomy=task==='journal-type'?journalTypes:task==='account-mapping'?accountTypes:['normal','relevant_exception'];
 const parts=[train,validation,test].map(rows=>samples(rows,p,task));
 const ys=parts.map(part=>part.map(r=>{const label=taxonomy.indexOf(r.target as never);if(label<0)throw Error('Unseen or missing target label');return label;}));
 if(parts[0].length<50||parts[1].length<20||parts[2].length<20)throw Error('Insufficient independent observations');
 const counts=taxonomy.map((_,c)=>ys[0].filter(y=>y===c).length);
 const minimum=synthetic?5:task==='review-ranking'?50:20;
 if(task!=='journal-anomaly'&&counts.some(n=>n<minimum))throw Error('Insufficient reviewed examples per class; use an explicit baseline');
 if(task==='journal-anomaly'&&counts[0]<50)throw Error('Insufficient documented normal training population');
 const ae=task==='journal-anomaly',x=parts.map(part=>part.map(r=>r.values)),n=x[0][0].length;
 const model=tf.sequential({layers:[tf.layers.dense({inputShape:[n],units:ae?12:24,activation:'relu',kernelInitializer:tf.initializers.glorotUniform({seed:config.seed??2026})}),tf.layers.dense({units:ae?n:taxonomy.length,activation:ae?'linear':'softmax',kernelInitializer:tf.initializers.glorotUniform({seed:(config.seed??2026)+1})})]});
 const tensors:tf.Tensor[]=[];let best:tf.Tensor[]=[];
 try{
  model.compile({optimizer:tf.train.adam(.003),loss:ae?'meanSquaredError':'categoricalCrossentropy'});
  const make=(i:number)=>{const eligible=x[i].filter((_,j)=>!ae||ys[i][j]===0),tx=tf.tensor2d(eligible);tensors.push(tx);
   const ty=ae?tx:tf.tidy(()=>tf.oneHot(tf.tensor1d(ys[i],'int32'),taxonomy.length));if(ty!==tx)tensors.push(ty);return [tx,ty] as const;};
  const [tx,ty]=make(0),[vx,vy]=make(1);if(!vx.shape[0])throw Error('Normal validation examples required');
  let bestLoss=Infinity,stale=0;
  const history=await model.fit(tx,ty,{epochs:Math.max(1,Math.min(100,config.epochs??12)),batchSize:Math.max(8,Math.min(1024,config.batch_size??64)),shuffle:false,
   classWeight:ae?undefined:Object.fromEntries(counts.map((count,c)=>[c,ys[0].length/(taxonomy.length*count)])),validationData:[vx,vy],
   callbacks:{onEpochEnd:async(_,logs)=>{const loss=Number(logs?.val_loss);if(loss<bestLoss){best.forEach(t=>t.dispose());best=model.getWeights().map(t=>t.clone());bestLoss=loss;stale=0;}else if(++stale>=3)model.stopTraining=true;await tf.nextFrame();}}});
  if(best.length)model.setWeights(best);
  let threshold=.6;const valPred=probabilities(model,x[1]);
  if(ae){const normal=errors(x[1],valPred).filter((_,i)=>ys[1][i]===0).sort((a,b)=>a-b);threshold=Math.max(1e-8,normal[Math.floor((normal.length-1)*.95)]);}
  const valMatrix=ae?[]:Array.from({length:ys[1].length},(_,i)=>valPred.slice(i*taxonomy.length,(i+1)*taxonomy.length));
  const valModel=ae?rankingQuality(ys[1],errors(x[1],valPred))[2].precision:classificationMetrics(ys[1],valMatrix,taxonomy.length,threshold).macro_f1??0;
  const valBaseline=ae?rankingQuality(ys[1],x[1].map(r=>Math.max(Math.abs(r[2]),r[5],r[6])))[2].precision:classificationMetrics(ys[1],baseline(x[0],ys[0],x[1],taxonomy.length),taxonomy.length,threshold).macro_f1??0;
  const selection={based_on:'validation_only',metric:ae?'precision_at_10_percent_review_capacity':'macro_f1_including_abstentions',model_value:valModel,baseline_value:valBaseline,model_preferred:valModel>valBaseline,preferred_execution_mode:valModel>valBaseline?'trained_model':'statistical_baseline',production_approval:false};
  // The final test is read only after preprocessing, model selection and threshold are frozen.
  const pred=probabilities(model,x[2]);let evaluation:unknown;
  if(ae){const score=errors(x[2],pred),ranking=score.map((s,i)=>({s,y:ys[2][i]})).sort((a,b)=>b.s-a.s),capacity=Math.max(1,Math.ceil(ranking.length*.1)),selected=ranking.slice(0,capacity),positive=ys[2].filter(y=>y===1).length;
   const baselineScores=x[2].map(r=>Math.max(Math.abs(r[2]),r[5],r[6]));
   evaluation={review_capacity:capacity,precision_at_capacity:selected.filter(r=>r.y===1).length/capacity,recall_at_capacity:positive?selected.filter(r=>r.y===1).length/positive:null,false_positive_count:score.filter((s,i)=>s>=threshold&&ys[2][i]===0).length,
    baseline:'robust standardized amount and rarity',baseline_scores:baselineScores,test_scores:score,model_review_queue:rankingQuality(ys[2],score),baseline_review_queue:rankingQuality(ys[2],baselineScores),population_assumption:'Only explicitly normal-labelled training journals; known relevant exceptions excluded',stability_across_entities_and_periods:null};
  }else{const matrix=(v:number[])=>Array.from({length:v.length/taxonomy.length},(_,i)=>v.slice(i*taxonomy.length,(i+1)*taxonomy.length));
   const majority=counts.indexOf(Math.max(...counts));
   evaluation={model:classificationMetrics(ys[2],matrix(pred),taxonomy.length,threshold),statistical_nearest_centroid:classificationMetrics(ys[2],baseline(x[0],ys[0],x[2],taxonomy.length),taxonomy.length,threshold),
    majority_training_class:classificationMetrics(ys[2],ys[2].map(()=>taxonomy.map((_,i)=>+(i===majority))),taxonomy.length,threshold),
    ...(task==='review-ranking'?{review_queue:rankingQuality(ys[2],matrix(pred).map(p=>p[1]))}:{})};
  }
  await mkdir(dir,{recursive:true});let weightsHash='',modelHash='';
  await model.save(tf.io.withSaveHandler(async a=>{const weights=Buffer.from(a.weightData as ArrayBuffer),json=JSON.stringify({modelTopology:a.modelTopology,weightSpecs:a.weightSpecs});
   weightsHash=digest(weights);modelHash=digest(json);await writeFile(join(dir,'weights.bin'),weights);await writeFile(join(dir,'model.json'),json);return {modelArtifactsInfo:{dateSaved:new Date(),modelTopologyType:'JSON'}};}));
  const savedJSON=JSON.parse(await readFile(join(dir,'model.json'),'utf8')),savedWeights=await readFile(join(dir,'weights.bin'));
  const reloaded=await tf.loadLayersModel(tf.io.fromMemory({modelTopology:savedJSON.modelTopology,weightSpecs:savedJSON.weightSpecs,weightData:savedWeights.buffer.slice(savedWeights.byteOffset,savedWeights.byteOffset+savedWeights.byteLength)}));
  let reloadDelta=Infinity;
  try{const after=probabilities(reloaded,x[2]);reloadDelta=Math.max(...pred.map((v,i)=>Math.abs(v-after[i])));if(!Number.isFinite(reloadDelta)||reloadDelta>1e-6)throw Error('Model reload tolerance failed');}finally{reloaded.dispose();}
  const centroids=taxonomy.map((_,c)=>{const members=x[0].filter((_,i)=>ys[0][i]===c);return x[0][0].map((_,j)=>members.reduce((s,r)=>s+r[j],0)/(members.length||1));});
  const artifact:Artifact={version:'local-foundation/2',config:{...config,family:task},task,preprocessor:p,taxonomy,centroids,threshold,weights_hash:weightsHash,model_hash:modelHash,reload_max_delta:reloadDelta,synthetic,dataset_hash:digest(JSON.stringify(rows)),selection,evaluation,
   resources:{duration_ms:performance.now()-started,cpu_microseconds:process.cpuUsage(cpu),rss_bytes:process.memoryUsage().rss,backend:tf.getBackend(),node:process.version,tfjs:tf.version.tfjs,history:history.history}};
  await writeFile(join(dir,'metadata.json'),JSON.stringify(artifact));return artifact;
 }finally{tensors.forEach(t=>t.dispose());best.forEach(t=>t.dispose());model.optimizer?.dispose();model.dispose();}
}
async function inferFoundationRun(rows:ContextRow[],dir:string,mode:'trained_model'|'statistical_baseline'){
 await initializeCPU();if(rows.length>10000||!rows.length)throw Error('Inference batch limit');
 for(const [name,limit] of [['metadata.json',8*1024*1024],['model.json',8*1024*1024],['weights.bin',100*1024*1024]] as const){if((await stat(join(dir,name))).size>limit)throw Error('Artifact size limit');}
 const m=JSON.parse(await readFile(join(dir,'metadata.json'),'utf8')) as Artifact;
 if(m.version!=='local-foundation/2')throw Error('Unsupported model version');
 if(!Number.isFinite(m.threshold)||m.threshold<=0||m.threshold>1&&m.task!=='journal-anomaly')throw Error('Invalid model threshold');
 const expected=m.task==='journal-type'?journalTypes:m.task==='account-mapping'?accountTypes:m.task==='journal-anomaly'||m.task==='review-ranking'?['normal','relevant_exception']:null;
 if(!expected||JSON.stringify(m.taxonomy)!==JSON.stringify(expected))throw Error('Model taxonomy mismatch');
 const json=await readFile(join(dir,'model.json')),weights=await readFile(join(dir,'weights.bin'));
 if(digest(json)!==m.model_hash||digest(weights)!==m.weights_hash)throw Error('Artifact integrity');
 if(mode==='statistical_baseline'){
  if(!['journal-type','account-mapping'].includes(m.task))throw Error('Use explicit contextual review baseline for this task');
  const part=samples(rows,m.preprocessor,m.task);
  if(!Array.isArray(m.centroids)||m.centroids.length!==m.taxonomy.length||m.centroids.some(c=>c.length!==part[0].values.length||c.some(v=>!Number.isFinite(v))))throw Error('Invalid baseline artifact');
  return {execution_mode:'statistical_baseline',model_version:digest(JSON.stringify(m)),feature_version:m.preprocessor.version,synthetic_training:m.synthetic,production_validated:false,taxonomy:m.taxonomy,
   predictions:part.map(r=>{const distances=m.centroids.map(c=>c.reduce((s,v,j)=>s+(v-r.values[j])**2,0)),ordered=distances.map((distance,i)=>({distance,i})).sort((a,b)=>a.distance-b.distance),margin=(ordered[1].distance-ordered[0].distance)/(ordered[1].distance+1e-8),abstained=margin<.2;
    return {transaction_id:r.id,evidence_line_ids:r.line_ids,review_status:'UNREVIEWED',execution_mode:'statistical_baseline',score:distances,threshold:.2,label:abstained?null:m.taxonomy[ordered[0].i],abstained,financial_exposure:null,auditor_assigned_risk:null,final_conclusion:null,fraud_probability:false};}),
   limitations:['Train-fitted centroid distances and ambiguity margin; not probabilities','No real-client accuracy or legal treatment established']};
 }
 const a=JSON.parse(json.toString()),buffer=weights.buffer.slice(weights.byteOffset,weights.byteOffset+weights.byteLength),key=dir+digest(JSON.stringify(m));
 let model=loadedModels.get(key);
 if(!model){model=await tf.loadLayersModel(tf.io.fromMemory({modelTopology:a.modelTopology,weightSpecs:a.weightSpecs,weightData:buffer}));
  try{tf.tidy(()=>{(model!.predict(tf.zeros([1,model!.inputs[0].shape[1]!])) as tf.Tensor).dataSync();});}catch(error){model.dispose();throw error;}
  if(loadedModels.size>=2){const first=loadedModels.keys().next().value!;loadedModels.get(first)!.dispose();loadedModels.delete(first);}loadedModels.set(key,model);
 }
 try{const part=samples(rows,m.preprocessor,m.task),x=part.map(r=>r.values),pred=probabilities(model,x),ae=m.task==='journal-anomaly',scores=ae?errors(x,pred):[];
  if(pred.some(v=>!Number.isFinite(v)))throw Error('Non-finite inference output');
  return {execution_mode:'trained_model',backend:tf.getBackend(),cpu_runtime:cpuStatus,model_version:digest(JSON.stringify(m)),feature_version:m.preprocessor.version,synthetic_training:m.synthetic,production_validated:false,taxonomy:m.taxonomy,
   predictions:part.map((r,i)=>{const distribution=pred.slice(i*m.taxonomy.length,(i+1)*m.taxonomy.length),c=distribution.indexOf(Math.max(...distribution));return {transaction_id:r.id,evidence_line_ids:r.line_ids,review_status:'UNREVIEWED',execution_mode:'trained_model',score:ae?scores[i]:distribution,
    threshold:m.threshold,label:ae?null:distribution[c]>=m.threshold?m.taxonomy[c]:null,abstained:!ae&&distribution[c]<m.threshold,financial_exposure:null,auditor_assigned_risk:null,final_conclusion:null,fraud_probability:false};}),
   limitations:['Experimental local model; synthetic results do not establish real-client accuracy','Scores are uncalibrated review signals; no legal, tax, materiality or audit-opinion conclusions','No cross-entity generalization has been established']};
 }finally{/* Cached weights are disposed on eviction or worker shutdown. */}
}
export async function inferFoundation(rows:ContextRow[],dir:string,mode:'trained_model'|'statistical_baseline'='trained_model'){
 if(waitingInference>=8)throw Error('Inference queue capacity exceeded');waitingInference++;
 let release!:()=>void;const prior=inferenceQueue;inferenceQueue=new Promise<void>(resolve=>{release=resolve;});
 await prior;waitingInference--;activeInference++;
 try{return await inferFoundationRun(rows,dir,mode);}finally{activeInference--;release();}
}

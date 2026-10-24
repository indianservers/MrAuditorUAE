import * as tf from '@tensorflow/tfjs';
import {createHash} from 'node:crypto';
import {readFile, stat} from 'node:fs/promises';
import {join} from 'node:path';
import {createRequire} from 'node:module';
import {accountSchema, accountVector, features, schema, transform, validateRows, type Scaling, type Row} from './features.js';
import {drift} from './metrics.js';

type Hashes = {model_json: string; weights: string};
type Loader = (dir: string, hashes: Hashes) => Promise<tf.LayersModel>;
type Family = 'autoencoder'|'journal-classifier'|'risk-ranking'|'account-classifier';
type Metadata = {
  preprocessing_version?: string;
  config: {family: Family}; artifact_hashes: Hashes; feature_schema: typeof schema | typeof accountSchema;
  scaler: Scaling; calibration: {threshold: number}; baseline_sample: number[][]; synthetic: boolean;
};
let cpu: Promise<void> | undefined;
export const cpuStatus={requested:process.env.ML_CPU_BACKEND??'auto',backend:'not_initialized',native_verified:false,fallback_reason:null as string|null};
let active = 0;
let waiting = 0;
let queue: Promise<void> = Promise.resolve();
const cache = new Map<string, tf.LayersModel>();
const hash = (b: string | Uint8Array) => createHash('sha256').update(b).digest('hex');

export async function initializeCPU() {
  cpu ??= (async () => {
    if(!['auto','javascript','native'].includes(cpuStatus.requested))throw Error('Unsupported CPU backend setting');
    if(cpuStatus.requested!=='javascript'){
      try{
        createRequire(import.meta.url)('@tensorflow/tfjs-node');
        if(!await tf.setBackend('tensorflow'))throw Error('Native backend initialization failed');
        await tf.ready();tf.tidy(()=>{if(tf.scalar(2).square().dataSync()[0]!==4)throw Error('Native CPU self-test failed');});
        cpuStatus.backend=tf.getBackend();cpuStatus.native_verified=true;return;
      }catch{cpuStatus.fallback_reason='Native CPU binding unavailable or self-test failed; using verified JavaScript CPU';}
    }
    if (!await tf.setBackend('cpu')) throw Error('CPU backend unavailable');
    await tf.ready();
    if (tf.getBackend() !== 'cpu') throw Error('Unexpected TensorFlow backend');
    tf.tidy(()=>{if(tf.scalar(2).square().dataSync()[0]!==4)throw Error('CPU self-test failed');});
    cpuStatus.backend=tf.getBackend();
  })().catch(error => { cpu = undefined; throw error; });
  return cpu;
}

export function clearInferenceCache() {
  if (active || waiting) throw Error('Cannot clear models during inference');
  for (const model of cache.values()) model.dispose();
  cache.clear();
}

async function boundedFile(path: string, max: number) {
  if ((await stat(path)).size > max) throw Error('Artifact size limit');
  const data = await readFile(path);
  if (data.byteLength > max) throw Error('Artifact size limit');
  return data;
}

async function run(input: Row[], dir: string, load: Loader) {
  await initializeCPU();
  const metadataBytes = await boundedFile(join(dir, 'metadata.json'), 8 * 1024 * 1024);
  const m = JSON.parse(metadataBytes.toString()) as Metadata;
  const family = m.config?.family;
  if (!['autoencoder','journal-classifier','risk-ranking','account-classifier'].includes(family)) throw Error('Unknown model family');
  const account = family === 'account-classifier', ae = family === 'autoencoder';
  const expected = account ? accountSchema : schema;
  if (m.preprocessing_version !== undefined && m.preprocessing_version !== 'train-scaler-clipped/1') throw Error('Model preprocessing version mismatch');
  if (m.feature_schema?.version !== expected.version ||
      (account ? (m.feature_schema as typeof accountSchema).dimensions !== accountSchema.dimensions :
      JSON.stringify((m.feature_schema as typeof schema).names) !== JSON.stringify(schema.names))) throw Error('Model feature version/schema mismatch');
  const rows = validateRows(input, 10000, account);
  const raw = account ? rows.map(r => accountVector(r.account_name!)) : features(rows);
  const x = transform(raw, m.scaler);
  const n = account ? accountSchema.dimensions : schema.names.length;
  if (m.scaler.mean.length !== n) throw Error('Model preprocessing dimensions mismatch');
  if (!m.calibration || !Number.isFinite(m.calibration.threshold) || m.calibration.threshold < 0 ||
      (ae && m.calibration.threshold <= 0)) throw Error('Invalid model threshold');
  if (!Array.isArray(m.baseline_sample) || m.baseline_sample.length > 1000 ||
      m.baseline_sample.some(r => !Array.isArray(r) || r.length !== n || r.some(v => !Number.isFinite(v)))) throw Error('Invalid drift baseline');
  if (!m.artifact_hashes || !/^[a-f0-9]{64}$/.test(m.artifact_hashes.model_json) || !/^[a-f0-9]{64}$/.test(m.artifact_hashes.weights)) throw Error('Missing model hashes');
  // Recheck bytes on every use, including cached instances; a corrupt artifact must never be hidden by a cache hit.
  const [json, weights] = await Promise.all([
    boundedFile(join(dir,'model.json'), 8 * 1024 * 1024),
    boundedFile(join(dir,'weights.bin'), 100 * 1024 * 1024),
  ]);
  if (hash(json) !== m.artifact_hashes.model_json || hash(weights) !== m.artifact_hashes.weights) throw Error('Artifact integrity');
  const version = hash(metadataBytes);
  const key = dir + ':' + version;
  let model = cache.get(key);
  if (!model) {
    const loaded = await load(dir, m.artifact_hashes);
    if (loaded.inputs.length !== 1 || loaded.outputs.length !== 1 || loaded.inputs[0].shape[1] !== n ||
        loaded.outputs[0].shape[1] !== (ae ? n : account ? 5 : 1)) {
      loaded.dispose();
      throw Error('Incompatible model topology');
    }
    try { tf.tidy(()=>{(loaded.predict(tf.zeros([1,n])) as tf.Tensor).dataSync();}); }
    catch(error){loaded.dispose();throw error;}
    if (cache.size >= 2) {
      const oldest = cache.keys().next().value!;
      cache.get(oldest)!.dispose(); cache.delete(oldest);
    }
    cache.set(key, loaded); model = loaded;
  } else { cache.delete(key); cache.set(key, model); }
  const p = tf.tidy(() => Array.from((model!.predict(tf.tensor2d(x)) as tf.Tensor).dataSync()));
  if (p.some(v => !Number.isFinite(v))) throw Error('Non-finite inference output');
  const predictions = rows.map((r, i) => {
    const components = ae ? x[i].map((v,j) => (v-p[i*n+j])**2) : x[i].map(v=>Math.abs(v));
    const error = ae ? components.reduce((a,b)=>a+b,0)/n : null;
    const score = account ? p.slice(i*5,i*5+5) : ae ? error!/(error!+m.calibration.threshold) : p[i];
    return {
      transaction_id:r.id, review_status:'UNREVIEWED', execution_mode:'trained_model',
      signal_category: account ? 'category_suggestion' : ae ?
        (error! >= m.calibration.threshold ? 'above_calibrated_threshold':'below_calibrated_threshold') :
        (Number(score)>=m.calibration.threshold?'exception_review_signal':'below_decision_threshold'),
      score, reconstruction_error:error, threshold:m.calibration.threshold,
      feature_deviations:components.map((v,j)=>({feature:account?'token_bucket_'+j:schema.names[j],value:v})).sort((a,b)=>b.value-a.value).slice(0,5),
      explanation_method:ae?'reconstruction components':'absolute standardized input deviation; not causal attribution',
      deterministic_rules:{round_thousands:account?null:raw[i][7]===1,year_end:account?null:raw[i][6]===1},
      missing_optional_fields:['description','counterparty','manual'].filter(k=>(input[i] as unknown as Record<string,unknown>)[k]==null),
      fraud_conclusion:false,
    };
  });
  return {
    execution_mode:'trained_model', backend:tf.getBackend(), cpu_runtime:cpuStatus, model_family:family, model_version:version,
    artifact_hashes:m.artifact_hashes, feature_version:expected.version, preprocessing_version:'train-scaler-clipped/1',
    legacy_preprocessing_assumption:m.preprocessing_version===undefined,
    predictions, drift:drift(m.baseline_sample,x), calibrated_probability:false, production_validated:false,
    synthetic_training:m.synthetic,
    task_semantics:family==='journal-classifier'?'binary_exception_review_signal':family==='account-classifier'?'five_account_category_suggestions':family,
    score_meaning:account?'Uncalibrated category scores':ae?'Monotonic reconstruction-error review signal':'Uncalibrated binary review score',
    limitations:['Experimental; synthetic validation does not establish real-client accuracy','Scores are not fraud probabilities','Suggestions do not approve accounting classifications or determine tax treatment','History features depend on the explicitly supplied batch; partition boundaries change historical context'],
  };
}

export async function inference(rows: Row[], dir: string, load: Loader) {
  if (waiting >= 8) throw Error('Inference queue capacity exceeded');
  waiting++;
  let release!: () => void;
  const prior = queue;
  queue = new Promise<void>(resolve => {release=resolve;});
  await prior;
  waiting--; active++;
  try {return await run(rows,dir,load);}
  finally {active--; release();}
}

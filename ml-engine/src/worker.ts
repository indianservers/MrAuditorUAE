import {readFile,writeFile,appendFile,rename} from 'node:fs/promises';
import {train,infer} from './engine.js';
import {trainFoundation,inferFoundation,clearFoundationCache} from './foundation.js';
import {createInterface} from 'node:readline';
import {clearInferenceCache} from './inference.js';
async function execute(requestPath:string,responsePath:string){
const request=JSON.parse(await readFile(requestPath,'utf8'));
// Entrypoint accepts server-created paths only; no public model upload or executable code input.
try {
 const v2=request.config?.pipeline_version==='local-foundation/2'||(request.operation==='infer'&&JSON.parse(await readFile(request.artifact_dir+'/metadata.json','utf8')).version==='local-foundation/2');
 if(!v2&&request.config?.execution_mode==='statistical_baseline')throw Error('Legacy model does not support this baseline');
 const result=request.operation==='train'?(v2?await trainFoundation(JSON.parse(await readFile(request.dataset,'utf8')).rows,request.config,request.artifact_dir):await train(JSON.parse(await readFile(request.dataset,'utf8')),request.config,request.artifact_dir,async row=>{await appendFile(responsePath+'.progress',JSON.stringify(row)+'\n');})):request.operation==='infer'?(v2?await inferFoundation(request.rows,request.artifact_dir,request.config?.execution_mode):await infer(request.rows,request.artifact_dir)):(()=>{throw Error('Unsupported operation');})();
 await writeFile(responsePath+'.staging',JSON.stringify(result));
 await rename(responsePath+'.staging',responsePath);
} catch(error) {
 const message=error instanceof Error?error.message:'';
 const error_category=/artifact|model|preprocessing|ENOENT|EACCES/i.test(message)?'ML_ARTIFACT_INVALID':/input|row|accounting|currency|description|counterparty|date|batch|split|label/i.test(message)?'ML_INPUT_INVALID':'ML_INFERENCE_FAILED';
 await writeFile(responsePath+'.staging',JSON.stringify({execution_mode:'unavailable',error_category,output:null}));
 await rename(responsePath+'.staging',responsePath);
 if(process.argv[2]!=='--serve')process.exitCode=1;
}
}
if(process.argv[2]==='--serve'){
 // Trusted parent sends file paths; requests are serialized and models remain reusable.
 const lines=createInterface({input:process.stdin});let pending=Promise.resolve();
 lines.on('line',line=>{pending=pending.then(async()=>{const r=JSON.parse(line);await execute(r.request,r.response);}).catch(()=>{process.exitCode=1;lines.close();});});
 lines.on('close',()=>{void pending.finally(()=>{clearInferenceCache();clearFoundationCache();});});
}else{
 const [requestPath,responsePath]=process.argv.slice(2);if(!requestPath||!responsePath)throw Error('Worker paths required');
 await execute(requestPath,responsePath);
}

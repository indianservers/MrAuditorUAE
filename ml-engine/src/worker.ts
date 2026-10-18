import {readFile,writeFile,appendFile} from 'node:fs/promises';
import {train,infer} from './engine.js';
const [requestPath,responsePath]=process.argv.slice(2);if(!requestPath||!responsePath)throw Error('Worker paths required');
const request=JSON.parse(await readFile(requestPath,'utf8'));
// Entrypoint accepts server-created paths only; no public model upload or executable code input.
const result=request.operation==='train'?await train(JSON.parse(await readFile(request.dataset,'utf8')),request.config,request.artifact_dir,async row=>{await appendFile(responsePath+'.progress',JSON.stringify(row)+'\n');}):request.operation==='infer'?await infer(request.rows,request.artifact_dir):(()=>{throw Error('Unsupported operation');})();
await writeFile(responsePath,JSON.stringify(result));

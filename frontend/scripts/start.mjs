import {cpSync,existsSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
const {values}=parseArgs({options:{port:{type:'string'},'api-origin':{type:'string'},'web-origin':{type:'string'}}});
const server=new URL('../.next/standalone/server.js',import.meta.url);
if(!existsSync(server))throw new Error('Build the standalone server with npm run build first.');
for(const [from,to] of [['../.next/static','../.next/standalone/.next/static'],['../public','../.next/standalone/public']]){
 const source=new URL(from,import.meta.url);if(existsSync(source))cpSync(source,new URL(to,import.meta.url),{recursive:true});
}
const child=spawn(process.execPath,[fileURLToPath(server)],{stdio:'inherit',env:{...process.env,HOSTNAME:process.env.BIND_HOST||'127.0.0.1',PORT:values.port||process.env.PORT||'3000',...(values['api-origin']?{AUDITOS_API_ORIGIN:values['api-origin']}:{}),...(values['web-origin']?{AUDITOS_WEB_ORIGIN:values['web-origin']}: {})}});
child.on('exit',code=>process.exit(code??1));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill(signal));
